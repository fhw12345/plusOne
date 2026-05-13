"""Smoke tests for session/engine factory wiring.

Does NOT connect — just verifies the factory builds and yields the
expected types.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from plus_one.core.db.session import async_engine, async_session_factory


@pytest.mark.unit
def test_engine_is_async_engine() -> None:
    assert isinstance(async_engine, AsyncEngine)


@pytest.mark.unit
def test_session_factory_yields_async_session() -> None:
    assert isinstance(async_session_factory, async_sessionmaker)
    session = async_session_factory()
    try:
        assert isinstance(session, AsyncSession)
    finally:
        # The session was never used; close synchronously by discarding.
        # (In a real test we'd `await session.close()`.)
        pass
