"""Integration tests for the DB-backed tool cache.

Requires real Postgres because:
  * ``ON CONFLICT`` upsert is Postgres-specific.
  * ``JSONB`` payload column is Postgres-specific.

Uses per-test engines + monkeypatches ``session_scope`` in ``_cache_db``
to side-step the cross-event-loop reuse issue with the module-level
async engine (other integration tests use the same workaround — see
``test_share.py``).

Verifies round-trip, TTL expiry, and upsert semantics.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from plus_one.config import settings
from plus_one.core.db.models import ToolCache
from plus_one.core.tools import _cache_db
from plus_one.core.tools._cache_db import _hash_key, get_cached, put_cached


@pytest_asyncio.fixture
async def _db_engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=2,
        max_overflow=2,
    )
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def _patched_session_scope(
    monkeypatch: pytest.MonkeyPatch, _db_engine: AsyncEngine
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    factory = async_sessionmaker(bind=_db_engine, expire_on_commit=False, autoflush=False)

    @asynccontextmanager
    async def fake_session_scope() -> AsyncIterator[AsyncSession]:
        session = factory()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    monkeypatch.setattr(_cache_db, "session_scope", fake_session_scope)
    yield factory


@pytest_asyncio.fixture
async def isolated_source(
    _patched_session_scope: async_sessionmaker[AsyncSession],
) -> AsyncIterator[str]:
    """Yield a unique source name and clean it up afterwards."""
    source = f"_test_{uuid.uuid4().hex[:8]}"
    _cache_db._TTL_BY_SOURCE[source] = timedelta(hours=1)
    try:
        yield source
    finally:
        session = _patched_session_scope()
        try:
            await session.execute(delete(ToolCache).where(ToolCache.source == source))
            await session.commit()
        finally:
            await session.close()
        _cache_db._TTL_BY_SOURCE.pop(source, None)


@pytest.mark.integration
async def test_put_then_get_round_trip(isolated_source: str) -> None:
    payload = [{"id": "a", "title": "hello"}, {"id": "b", "title": "world"}]
    await put_cached(isolated_source, "k1", payload)

    got = await get_cached(isolated_source, "k1")
    assert got == payload


@pytest.mark.integration
async def test_get_returns_none_when_absent(isolated_source: str) -> None:
    assert await get_cached(isolated_source, "missing") is None


@pytest.mark.integration
async def test_expired_row_returns_none(
    isolated_source: str,
    _patched_session_scope: async_sessionmaker[AsyncSession],
) -> None:
    """Manually back-date a row past its TTL and verify ``get_cached``
    returns ``None``."""
    await put_cached(isolated_source, "stale", [{"id": "x"}])

    session = _patched_session_scope()
    try:
        row = await session.get(ToolCache, (isolated_source, _hash_key("stale")))
        assert row is not None
        row.fetched_at = datetime.now(UTC) - timedelta(days=10)
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()
    finally:
        await session.close()

    assert await get_cached(isolated_source, "stale") is None


@pytest.mark.integration
async def test_put_upserts(
    isolated_source: str,
    _patched_session_scope: async_sessionmaker[AsyncSession],
) -> None:
    """Second ``put_cached`` for the same key updates the row in place."""
    await put_cached(isolated_source, "k1", [{"v": 1}])
    await put_cached(isolated_source, "k1", [{"v": 2}])
    got = await get_cached(isolated_source, "k1")
    assert got == [{"v": 2}]

    session = _patched_session_scope()
    try:
        count = await session.scalar(
            select(func.count())
            .select_from(ToolCache)
            .where(ToolCache.source == isolated_source)
        )
        assert count == 1
    finally:
        await session.close()


@pytest.mark.integration
async def test_put_refreshes_expiry(
    isolated_source: str,
    _patched_session_scope: async_sessionmaker[AsyncSession],
) -> None:
    """A re-put pushes ``expires_at`` forward relative to the new write."""
    await put_cached(isolated_source, "k1", [{"v": 1}])
    session = _patched_session_scope()
    try:
        row = await session.get(ToolCache, (isolated_source, _hash_key("k1")))
        assert row is not None
        first_expiry = row.expires_at
    finally:
        await session.close()

    await put_cached(isolated_source, "k1", [{"v": 2}])
    session = _patched_session_scope()
    try:
        row = await session.get(ToolCache, (isolated_source, _hash_key("k1")))
        assert row is not None
        assert row.expires_at >= first_expiry
    finally:
        await session.close()
