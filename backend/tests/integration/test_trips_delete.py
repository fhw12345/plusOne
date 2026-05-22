"""Integration tests for DELETE /api/trips/{id} — cascade + status guard.

Same live-DB pattern as ``test_trips_list.py`` / ``test_share.py``.
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

from plus_one.api.trips import router as trips_router
from plus_one.config import settings
from plus_one.core.auth.jwt import create_access_token
from plus_one.core.db.models import Report, SharedTrip, Trip, User
from plus_one.core.db.session import get_request_session

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


async def _persist_user(session: AsyncSession) -> User:
    user = User(
        email=f"del-{uuid.uuid4().hex[:8]}@example.com",
        username="u_" + uuid.uuid4().hex[:10],
        password_hash="x",
        is_active=True,
    )
    session.add(user)
    await session.flush()
    return user


async def _persist_trip(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    status: str = "complete",
) -> Trip:
    trip = Trip(
        user_id=user_id,
        destination="x",
        free_text=None,
        status=status,
    )
    session.add(trip)
    await session.flush()
    return trip


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
    app.include_router(trips_router)

    async def fake_get_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_request_session] = fake_get_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


# === Cascade =============================================================


@pytest.mark.integration
async def test_delete_trip_owner_cascade_removes_reports_and_shares(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _persist_user(db_session)
    trip = await _persist_trip(db_session, user.id)
    r1 = Report(trip_id=trip.id, content={}, trace=[])
    r2 = Report(trip_id=trip.id, content={}, trace=[])
    db_session.add_all([r1, r2])
    s = SharedTrip(
        token=f"del-{uuid.uuid4().hex}",
        trip_id=trip.id,
        created_by=user.id,
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    db_session.add(s)
    await db_session.commit()

    resp = await client.delete(f"/api/trips/{trip.id}", headers=_auth(user))
    assert resp.status_code == 204

    assert await db_session.get(Trip, trip.id) is None
    reports_left = (
        (await db_session.execute(select(Report).where(Report.trip_id == trip.id))).scalars().all()
    )
    assert reports_left == []
    shares_left = (
        (await db_session.execute(select(SharedTrip).where(SharedTrip.trip_id == trip.id)))
        .scalars()
        .all()
    )
    assert shares_left == []


@pytest.mark.integration
async def test_delete_trip_forbidden_for_non_owner(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    owner = await _persist_user(db_session)
    attacker = await _persist_user(db_session)
    trip = await _persist_trip(db_session, owner.id)
    await db_session.commit()

    resp = await client.delete(f"/api/trips/{trip.id}", headers=_auth(attacker))
    assert resp.status_code == 404
    assert await db_session.get(Trip, trip.id) is not None


@pytest.mark.integration
async def test_delete_trip_404_for_unknown_id(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _persist_user(db_session)
    await db_session.commit()

    resp = await client.delete(f"/api/trips/{uuid.uuid4()}", headers=_auth(user))
    assert resp.status_code == 404


@pytest.mark.integration
async def test_delete_trip_409_when_running(client: AsyncClient, db_session: AsyncSession) -> None:
    user = await _persist_user(db_session)
    trip = await _persist_trip(db_session, user.id, status="running")
    await db_session.commit()

    resp = await client.delete(f"/api/trips/{trip.id}", headers=_auth(user))
    assert resp.status_code == 409
    assert resp.json()["detail"] == "trip_running"
    assert await db_session.get(Trip, trip.id) is not None


@pytest.mark.integration
async def test_delete_trip_409_does_not_partially_delete(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _persist_user(db_session)
    trip = await _persist_trip(db_session, user.id, status="running")
    db_session.add(Report(trip_id=trip.id, content={}, trace=[]))
    db_session.add(
        SharedTrip(
            token=f"partial-{uuid.uuid4().hex}",
            trip_id=trip.id,
            created_by=user.id,
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
    )
    await db_session.commit()

    resp = await client.delete(f"/api/trips/{trip.id}", headers=_auth(user))
    assert resp.status_code == 409

    reports_left = (
        (await db_session.execute(select(Report).where(Report.trip_id == trip.id))).scalars().all()
    )
    shares_left = (
        (await db_session.execute(select(SharedTrip).where(SharedTrip.trip_id == trip.id)))
        .scalars()
        .all()
    )
    assert len(reports_left) == 1
    assert len(shares_left) == 1
