"""Integration tests for GET /api/me/export (batch-2s).

Live-DB pattern matching ``test_trips_delete.py``.
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from plus_one.api.me import router as me_router
from plus_one.config import settings
from plus_one.core.auth.jwt import create_access_token
from plus_one.core.db.models import (
    Companion,
    Feedback,
    Profile,
    Report,
    SharedTrip,
    Trip,
    User,
    trip_companions,
)
from plus_one.core.db.session import get_request_session

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


async def _persist_user(session: AsyncSession, *, is_admin: bool = False) -> User:
    user = User(
        email=f"exp-{uuid.uuid4().hex[:8]}@example.com",
        username="u_" + uuid.uuid4().hex[:10],
        password_hash="x",
        is_active=True,
        is_admin=is_admin,
    )
    session.add(user)
    await session.flush()
    return user


@pytest_asyncio.fixture
async def db_engine() -> AsyncIterator[AsyncEngine]:
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
async def db_session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    factory = async_sessionmaker(bind=db_engine, expire_on_commit=False, autoflush=False)
    session = factory()
    try:
        yield session
    finally:
        await session.rollback()
        await session.close()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    app.include_router(me_router)

    async def fake_get_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_request_session] = fake_get_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


async def _seed_full_user(db_session: AsyncSession) -> tuple[User, Trip, Companion]:
    user = await _persist_user(db_session)
    profile = Profile(
        user_id=user.id,
        demographics={"age_range": "30-39"},
        travel_style={"pace": "easy"},
        explicit_preferences={"loves": ["ramen"], "hates": []},
        visited_cities=[{"city": "Tokyo", "year": 2024}],
        implicit_preferences=[],
    )
    companion = Companion(
        user_id=user.id,
        name="Wei-" + uuid.uuid4().hex[:6],
        explicit_preferences={"loves": ["coffee"], "hates": []},
        constraints={},
    )
    db_session.add_all([profile, companion])
    await db_session.flush()

    trip = Trip(user_id=user.id, destination="Tokyo", status="complete")
    db_session.add(trip)
    await db_session.flush()
    await db_session.execute(
        trip_companions.insert().values(trip_id=trip.id, companion_id=companion.id)
    )

    db_session.add(
        Report(trip_id=trip.id, content={"tl_dr": "x"}, trace=[], input_tokens=10, output_tokens=5)
    )
    db_session.add(
        Feedback(
            trip_id=trip.id,
            card_id="card-1",
            for_companion_id=companion.id,
            signal="thumb_up",
            text="loved it",
        )
    )
    db_session.add(
        SharedTrip(
            token=f"sh-{uuid.uuid4().hex}",
            trip_id=trip.id,
            created_by=user.id,
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
    )
    await db_session.commit()
    return user, trip, companion


# === Tests ================================================================


@pytest.mark.integration
async def test_export_returns_owned_data(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user, trip, companion = await _seed_full_user(db_session)

    resp = await client.get("/api/me/export", headers=_auth(user))
    assert resp.status_code == 200
    body = json.loads(resp.content)
    assert body["user"]["id"] == str(user.id)
    assert body["user"]["email"] == user.email
    assert body["profile"]["demographics"] == {"age_range": "30-39"}
    assert len(body["companions"]) == 1
    assert body["companions"][0]["id"] == str(companion.id)
    assert len(body["trips"]) == 1
    assert body["trips"][0]["id"] == str(trip.id)
    assert body["trips"][0]["companion_ids"] == [str(companion.id)]
    assert len(body["trips"][0]["reports"]) == 1
    assert len(body["feedback"]) == 1
    assert body["feedback"][0]["trip_id"] == str(trip.id)


@pytest.mark.integration
async def test_export_excludes_other_users_data(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_a, _trip_a, _companion_a = await _seed_full_user(db_session)
    user_b, trip_b, companion_b = await _seed_full_user(db_session)

    resp = await client.get("/api/me/export", headers=_auth(user_a))
    assert resp.status_code == 200
    text = resp.content.decode("utf-8")
    assert str(user_b.id) not in text
    assert str(trip_b.id) not in text
    assert str(companion_b.id) not in text


@pytest.mark.integration
async def test_export_filename_header(client: AsyncClient, db_session: AsyncSession) -> None:
    user = await _persist_user(db_session)
    await db_session.commit()

    resp = await client.get("/api/me/export", headers=_auth(user))
    assert resp.status_code == 200
    disposition = resp.headers["content-disposition"]
    pattern = (
        r'attachment; filename="plus-one-export-'
        r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}-'
        r'\d{4}-\d{2}-\d{2}\.json"'
    )
    assert re.fullmatch(pattern, disposition), disposition
    assert resp.headers["content-type"].startswith("application/json")
    assert resp.headers.get("cache-control") == "no-store"


@pytest.mark.integration
async def test_export_excludes_password_hash(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _persist_user(db_session)
    await db_session.commit()

    resp = await client.get("/api/me/export", headers=_auth(user))
    assert resp.status_code == 200
    text = resp.content.decode("utf-8")
    assert "password_hash" not in text
    assert "failed_login_attempts" not in text
    assert "locked_until" not in text


@pytest.mark.integration
async def test_export_requires_auth(client: AsyncClient) -> None:
    resp = await client.get("/api/me/export")
    assert resp.status_code == 401
