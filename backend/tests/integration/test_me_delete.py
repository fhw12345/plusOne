"""Integration tests for DELETE /api/me (batch-2s).

Verifies hard-delete cascades cover every user-scoped child table, the
``email_codes`` explicit-delete handles the no-FK case, and the admin
guard blocks self-deletion.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from plus_one.api.me import router as me_router
from plus_one.config import settings
from plus_one.core.auth.jwt import create_access_token
from plus_one.core.db.models import (
    Companion,
    EmailCode,
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
        email=f"del-{uuid.uuid4().hex[:8]}@example.com",
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


# === Tests ================================================================


@pytest.mark.integration
async def test_delete_removes_user_and_cascades(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _persist_user(db_session)
    profile = Profile(
        user_id=user.id,
        demographics={},
        travel_style={},
        explicit_preferences={"loves": [], "hates": []},
        visited_cities=[],
        implicit_preferences=[],
    )
    companion = Companion(
        user_id=user.id,
        name="c-" + uuid.uuid4().hex[:6],
        explicit_preferences={"loves": [], "hates": []},
        constraints={},
    )
    db_session.add_all([profile, companion])
    await db_session.flush()
    trip = Trip(user_id=user.id, destination="x", status="complete")
    db_session.add(trip)
    await db_session.flush()
    await db_session.execute(
        trip_companions.insert().values(trip_id=trip.id, companion_id=companion.id)
    )
    report = Report(trip_id=trip.id, content={}, trace=[])
    fb = Feedback(
        trip_id=trip.id,
        card_id="c1",
        for_companion_id=companion.id,
        signal="thumb_up",
    )
    share = SharedTrip(
        token=f"sh-{uuid.uuid4().hex}",
        trip_id=trip.id,
        created_by=user.id,
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    db_session.add_all([report, fb, share])
    await db_session.commit()

    # Capture IDs while the ORM state is still fresh — after expire_all the
    # python objects would lazy-reload, but the rows are gone.
    user_id = user.id
    trip_id = trip.id

    # Seed another user whose data must survive.
    other = await _persist_user(db_session)
    other_trip = Trip(user_id=other.id, destination="y", status="complete")
    db_session.add(other_trip)
    await db_session.commit()
    other_id = other.id
    other_trip_id = other_trip.id

    resp = await client.delete("/api/me", headers=_auth(user))
    assert resp.status_code == 204

    # The current SQLAlchemy session has the deleted rows in its identity
    # map; expire so SELECTs hit the DB afresh.
    db_session.expire_all()

    assert await db_session.get(User, user_id) is None
    assert (
        await db_session.execute(select(Profile).where(Profile.user_id == user_id))
    ).scalar_one_or_none() is None
    assert (
        await db_session.execute(select(Companion).where(Companion.user_id == user_id))
    ).scalars().all() == []
    assert (
        await db_session.execute(select(Trip).where(Trip.user_id == user_id))
    ).scalars().all() == []
    assert (
        await db_session.execute(select(Report).where(Report.trip_id == trip_id))
    ).scalars().all() == []
    assert (
        await db_session.execute(select(Feedback).where(Feedback.trip_id == trip_id))
    ).scalars().all() == []
    assert (
        await db_session.execute(select(SharedTrip).where(SharedTrip.trip_id == trip_id))
    ).scalars().all() == []

    # Other user's data untouched.
    assert await db_session.get(User, other_id) is not None
    assert await db_session.get(Trip, other_trip_id) is not None


@pytest.mark.integration
async def test_delete_clears_email_codes(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _persist_user(db_session)
    code = EmailCode(
        email=user.email,
        code_hash="hash",
        purpose="login",
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )
    db_session.add(code)
    await db_session.commit()
    user_email = user.email

    resp = await client.delete("/api/me", headers=_auth(user))
    assert resp.status_code == 204

    db_session.expire_all()
    remaining = (
        await db_session.execute(select(EmailCode).where(EmailCode.email == user_email))
    ).scalars().all()
    assert remaining == []


@pytest.mark.integration
async def test_delete_admin_blocked(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await _persist_user(db_session, is_admin=True)
    await db_session.commit()
    admin_id = admin.id

    resp = await client.delete("/api/me", headers=_auth(admin))
    assert resp.status_code == 409
    assert resp.json()["detail"] == "admin_cannot_self_delete"

    db_session.expire_all()
    assert await db_session.get(User, admin_id) is not None


@pytest.mark.integration
async def test_delete_requires_auth(client: AsyncClient) -> None:
    resp = await client.delete("/api/me")
    assert resp.status_code == 401
