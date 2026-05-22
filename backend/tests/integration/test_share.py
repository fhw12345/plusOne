"""Integration tests for share endpoints — POST/DELETE /api/trips/{id}/share
and the unauthed GET /api/shared/{token}.

Uses the live-DB pattern from ``test_trips_list.py``: a per-test
``AsyncEngine`` against the local Postgres, a session injected via
``dependency_overrides`` so the test setup is visible to the request
handler. Each test creates its own users + trips with unique emails so
concurrent runs don't collide.
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

from plus_one.api.shared import router as shared_router
from plus_one.api.trips import router as trips_router
from plus_one.config import settings
from plus_one.core.auth.jwt import create_access_token
from plus_one.core.db.models import Report, SharedTrip, Trip, User
from plus_one.core.db.session import get_request_session

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


async def _persist_user(session: AsyncSession, email: str | None = None) -> User:
    user = User(
        email=email or f"share-{uuid.uuid4().hex[:8]}@example.com",
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
    destination: str,
    *,
    status: str = "complete",
) -> Trip:
    trip = Trip(
        user_id=user_id,
        destination=destination,
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
    app.include_router(shared_router)

    async def fake_get_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_request_session] = fake_get_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


# === Create share ========================================================


@pytest.mark.integration
async def test_create_share_returns_token_and_url(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _persist_user(db_session)
    trip = await _persist_trip(db_session, user.id, "Tokyo")
    await db_session.commit()

    resp = await client.post(f"/api/trips/{trip.id}/share", headers=_auth(user))
    assert resp.status_code == 201
    body = resp.json()
    assert set(body.keys()) == {"token", "share_url", "expires_at"}
    assert isinstance(body["token"], str)
    assert len(body["token"]) >= 30
    assert body["share_url"].endswith(body["token"])
    assert "/share/" in body["share_url"]

    rows = (
        (await db_session.execute(select(SharedTrip).where(SharedTrip.trip_id == trip.id)))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].token == body["token"]
    assert rows[0].created_by == user.id


@pytest.mark.integration
async def test_create_share_forbidden_for_non_owner(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    owner = await _persist_user(db_session)
    attacker = await _persist_user(db_session)
    trip = await _persist_trip(db_session, owner.id, "Kyoto")
    await db_session.commit()

    resp = await client.post(f"/api/trips/{trip.id}/share", headers=_auth(attacker))
    assert resp.status_code == 404
    assert resp.json()["detail"] == "trip_not_found"


@pytest.mark.integration
async def test_create_share_404_for_unknown_trip(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _persist_user(db_session)
    await db_session.commit()

    resp = await client.post(f"/api/trips/{uuid.uuid4()}/share", headers=_auth(user))
    assert resp.status_code == 404


# === Get shared (unauthed) ==============================================


@pytest.mark.integration
async def test_get_shared_anonymous_returns_payload_without_pii(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _persist_user(db_session)
    trip = await _persist_trip(db_session, user.id, "Osaka")
    report = Report(
        trip_id=trip.id,
        content={"items": [{"name": "ramen-ya"}]},
        trace=[{"event": "x"}],
        input_tokens=100,
        output_tokens=50,
    )
    db_session.add(report)
    await db_session.flush()

    mint = await client.post(f"/api/trips/{trip.id}/share", headers=_auth(user))
    token = mint.json()["token"]

    # No auth header — must succeed.
    resp = await client.get(f"/api/shared/{token}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["destination"] == "Osaka"
    assert body["status"] == "complete"
    assert body["shared"] is True
    assert "expires_at" in body
    assert body["content"] == {"items": [{"name": "ramen-ya"}]}
    # Strip-checks: none of the PII / observability fields leak.
    for forbidden in ("user_id", "created_by", "trace", "input_tokens", "output_tokens"):
        assert forbidden not in body, f"public payload leaked {forbidden}"


@pytest.mark.integration
async def test_get_shared_404_for_unknown_token(client: AsyncClient) -> None:
    resp = await client.get("/api/shared/totally-not-a-real-token-xyz123")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "share_not_found_or_expired"


@pytest.mark.integration
async def test_get_shared_404_for_expired_token(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _persist_user(db_session)
    trip = await _persist_trip(db_session, user.id, "Nara")
    share = SharedTrip(
        token=f"expired-{uuid.uuid4().hex}",
        trip_id=trip.id,
        created_by=user.id,
        expires_at=datetime.now(UTC) - timedelta(days=1),
    )
    db_session.add(share)
    await db_session.commit()

    resp = await client.get(f"/api/shared/{share.token}")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "share_not_found_or_expired"


# === Revoke ==============================================================


@pytest.mark.integration
async def test_revoke_share_removes_row_and_breaks_link(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _persist_user(db_session)
    trip = await _persist_trip(db_session, user.id, "Sapporo")
    await db_session.commit()

    mint = await client.post(f"/api/trips/{trip.id}/share", headers=_auth(user))
    token = mint.json()["token"]

    revoke = await client.delete(f"/api/trips/{trip.id}/share/{token}", headers=_auth(user))
    assert revoke.status_code == 204

    get_after = await client.get(f"/api/shared/{token}")
    assert get_after.status_code == 404

    rows = (
        (await db_session.execute(select(SharedTrip).where(SharedTrip.trip_id == trip.id)))
        .scalars()
        .all()
    )
    assert rows == []


@pytest.mark.integration
async def test_revoke_share_forbidden_for_non_owner(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    owner = await _persist_user(db_session)
    attacker = await _persist_user(db_session)
    trip = await _persist_trip(db_session, owner.id, "Hakone")
    await db_session.commit()

    mint = await client.post(f"/api/trips/{trip.id}/share", headers=_auth(owner))
    token = mint.json()["token"]

    revoke = await client.delete(f"/api/trips/{trip.id}/share/{token}", headers=_auth(attacker))
    assert revoke.status_code == 404

    rows = (
        (await db_session.execute(select(SharedTrip).where(SharedTrip.token == token)))
        .scalars()
        .all()
    )
    assert len(rows) == 1


@pytest.mark.integration
async def test_revoke_share_404_when_trip_id_mismatches_token(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _persist_user(db_session)
    trip_a = await _persist_trip(db_session, user.id, "Trip-A")
    trip_b = await _persist_trip(db_session, user.id, "Trip-B")
    await db_session.commit()

    mint = await client.post(f"/api/trips/{trip_a.id}/share", headers=_auth(user))
    token = mint.json()["token"]

    # Use trip_b's id in the path with trip_a's token.
    revoke = await client.delete(f"/api/trips/{trip_b.id}/share/{token}", headers=_auth(user))
    assert revoke.status_code == 404
