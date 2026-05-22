"""Integration tests for ``GET /api/trips`` — keyset pagination + cross-user isolation.

Unlike ``test_trips_sse_auth.py`` (stub-session), these exercise the real
SQL — tuple comparison, ``ORDER BY``, and the correlated subquery for
``latest_report_id`` all need a live Postgres. Test isolation is per-test:
each test creates its own users + trips with unique emails so concurrent
runs don't collide.
"""

from __future__ import annotations

import base64
import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from plus_one.api.trips import router as trips_router
from plus_one.config import settings
from plus_one.core.auth.jwt import create_access_token
from plus_one.core.db.models import Report, Trip, User
from plus_one.core.db.session import get_request_session

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


def _b64url_no_pad(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


async def _persist_user(session: AsyncSession, email: str | None = None) -> User:
    user = User(
        email=email or f"list-{uuid.uuid4().hex[:8]}@example.com",
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
    created_at: datetime | None = None,
    status: str = "pending",
) -> Trip:
    trip = Trip(
        user_id=user_id,
        destination=destination,
        free_text=None,
        status=status,
    )
    if created_at is not None:
        trip.created_at = created_at
    session.add(trip)
    await session.flush()
    return trip


async def _persist_report(
    session: AsyncSession,
    trip_id: uuid.UUID,
    *,
    created_at: datetime | None = None,
) -> Report:
    report = Report(trip_id=trip_id, content={}, trace=[])
    if created_at is not None:
        report.created_at = created_at
    session.add(report)
    await session.flush()
    return report


@pytest_asyncio.fixture
async def db_engine() -> AsyncIterator[AsyncEngine]:
    """Per-test engine bound to the running event loop.

    The module-level ``async_engine`` is created at import time and
    pytest-asyncio swaps event loops between tests, which corrupts
    asyncpg's connection state on teardown ("Event loop is closed").
    A fresh engine per test sidesteps that without monkeypatching globals.
    """
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
    """One session per test. Rolls back at teardown to keep the table clean."""
    factory = async_sessionmaker(bind=db_engine, expire_on_commit=False, autoflush=False)
    session = factory()
    try:
        yield session
    finally:
        await session.rollback()
        await session.close()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """ASGI test client that re-uses the per-test session so setup data is
    visible to the request handler (which uses the same session)."""
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


# === 1: requires_auth =====================================================


@pytest.mark.integration
async def test_list_trips_requires_auth(client: AsyncClient) -> None:
    resp = await client.get("/api/trips")
    assert resp.status_code == 401


# === 2: empty user ========================================================


@pytest.mark.integration
async def test_list_trips_empty_user(client: AsyncClient, db_session: AsyncSession) -> None:
    user = await _persist_user(db_session)
    resp = await client.get("/api/trips", headers=_auth(user))
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"trips": [], "next_cursor": None}


# === 3: single page =======================================================


@pytest.mark.integration
async def test_list_trips_single_page(client: AsyncClient, db_session: AsyncSession) -> None:
    user = await _persist_user(db_session)
    base = datetime.now(UTC)
    await _persist_trip(db_session, user.id, "Osaka", created_at=base - timedelta(minutes=2))
    await _persist_trip(db_session, user.id, "Kyoto", created_at=base - timedelta(minutes=1))
    await _persist_trip(db_session, user.id, "Tokyo", created_at=base)

    resp = await client.get("/api/trips", headers=_auth(user))
    assert resp.status_code == 200
    body = resp.json()
    assert body["next_cursor"] is None
    assert [t["destination"] for t in body["trips"]] == ["Tokyo", "Kyoto", "Osaka"]
    first = body["trips"][0]
    assert set(first.keys()) == {
        "trip_id",
        "destination",
        "status",
        "created_at",
        "latest_report_id",
        "has_report",
    }
    assert first["latest_report_id"] is None
    assert first["has_report"] is False


# === 4: paginates with cursor ============================================


@pytest.mark.integration
async def test_list_trips_paginates_with_cursor(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _persist_user(db_session)
    base = datetime.now(UTC)
    for i in range(25):
        await _persist_trip(
            db_session,
            user.id,
            f"city-{i:02d}",
            created_at=base - timedelta(seconds=i),
        )

    expected_order = [f"city-{i:02d}" for i in range(25)]
    seen: list[str] = []

    page1 = (await client.get("/api/trips?limit=10", headers=_auth(user))).json()
    assert len(page1["trips"]) == 10
    assert page1["next_cursor"] is not None
    seen.extend(t["destination"] for t in page1["trips"])

    page2 = (
        await client.get(f"/api/trips?limit=10&cursor={page1['next_cursor']}", headers=_auth(user))
    ).json()
    assert len(page2["trips"]) == 10
    assert page2["next_cursor"] is not None
    seen.extend(t["destination"] for t in page2["trips"])

    page3 = (
        await client.get(f"/api/trips?limit=10&cursor={page2['next_cursor']}", headers=_auth(user))
    ).json()
    assert len(page3["trips"]) == 5
    assert page3["next_cursor"] is None
    seen.extend(t["destination"] for t in page3["trips"])

    assert seen == expected_order
    assert len(set(seen)) == 25


# === 5: default limit 20 ==================================================


@pytest.mark.integration
async def test_list_trips_default_limit_20(client: AsyncClient, db_session: AsyncSession) -> None:
    user = await _persist_user(db_session)
    base = datetime.now(UTC)
    for i in range(25):
        await _persist_trip(
            db_session, user.id, f"c-{i:02d}", created_at=base - timedelta(seconds=i)
        )

    resp = await client.get("/api/trips", headers=_auth(user))
    body = resp.json()
    assert len(body["trips"]) == 20
    assert body["next_cursor"] is not None


# === 6: limit clamped =====================================================


@pytest.mark.integration
async def test_list_trips_limit_clamped(client: AsyncClient, db_session: AsyncSession) -> None:
    user = await _persist_user(db_session)
    await _persist_trip(db_session, user.id, "Tokyo")

    assert (await client.get("/api/trips?limit=0", headers=_auth(user))).status_code == 422
    assert (await client.get("/api/trips?limit=101", headers=_auth(user))).status_code == 422
    resp = await client.get("/api/trips?limit=100", headers=_auth(user))
    assert resp.status_code == 200
    assert len(resp.json()["trips"]) == 1


# === 7: invalid cursor ====================================================


@pytest.mark.integration
async def test_list_trips_invalid_cursor(client: AsyncClient, db_session: AsyncSession) -> None:
    user = await _persist_user(db_session)
    headers = _auth(user)

    r1 = await client.get("/api/trips?cursor=not-base64!!!", headers=headers)
    assert r1.status_code == 400
    assert r1.json()["detail"] == "invalid_cursor"

    bad_payload = _b64url_no_pad(b"this is not json")
    r2 = await client.get(f"/api/trips?cursor={bad_payload}", headers=headers)
    assert r2.status_code == 400
    assert r2.json()["detail"] == "invalid_cursor"

    wrong_shape = _b64url_no_pad(json.dumps({"created_at": "2026-01-01T00:00:00+00:00"}).encode())
    r3 = await client.get(f"/api/trips?cursor={wrong_shape}", headers=headers)
    assert r3.status_code == 400
    assert r3.json()["detail"] == "invalid_cursor"


# === 8: isolates users — load-bearing security test ======================


@pytest.mark.integration
async def test_list_trips_isolates_users(client: AsyncClient, db_session: AsyncSession) -> None:
    user_a = await _persist_user(db_session)
    user_b = await _persist_user(db_session)

    a_trips = [await _persist_trip(db_session, user_a.id, f"A-{i}") for i in range(3)]
    b_trips = [await _persist_trip(db_session, user_b.id, f"B-{i}") for i in range(2)]

    resp_a = (await client.get("/api/trips", headers=_auth(user_a))).json()
    a_ids = {t["trip_id"] for t in resp_a["trips"]}
    assert a_ids == {str(t.id) for t in a_trips}
    assert all(t["destination"].startswith("A-") for t in resp_a["trips"])

    resp_b = (await client.get("/api/trips", headers=_auth(user_b))).json()
    b_ids = {t["trip_id"] for t in resp_b["trips"]}
    assert b_ids == {str(t.id) for t in b_trips}
    assert all(t["destination"].startswith("B-") for t in resp_b["trips"])

    assert a_ids.isdisjoint(b_ids)


# === 9: has_report flag ===================================================


@pytest.mark.integration
async def test_list_trips_has_report_flag(client: AsyncClient, db_session: AsyncSession) -> None:
    user = await _persist_user(db_session)
    base = datetime.now(UTC)

    await _persist_trip(db_session, user.id, "none", created_at=base)
    trip_one = await _persist_trip(
        db_session, user.id, "one", created_at=base - timedelta(seconds=1)
    )
    r_one = await _persist_report(db_session, trip_one.id)

    trip_two = await _persist_trip(
        db_session, user.id, "two", created_at=base - timedelta(seconds=2)
    )
    await _persist_report(db_session, trip_two.id, created_at=base - timedelta(minutes=5))
    r_new = await _persist_report(db_session, trip_two.id, created_at=base - timedelta(minutes=1))

    body = (await client.get("/api/trips", headers=_auth(user))).json()
    by_dest = {t["destination"]: t for t in body["trips"]}

    assert by_dest["none"]["has_report"] is False
    assert by_dest["none"]["latest_report_id"] is None
    assert by_dest["one"]["has_report"] is True
    assert by_dest["one"]["latest_report_id"] == str(r_one.id)
    assert by_dest["two"]["has_report"] is True
    assert by_dest["two"]["latest_report_id"] == str(r_new.id)


# === 10: orders by created_at desc ========================================


@pytest.mark.integration
async def test_list_trips_orders_by_created_at_desc(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _persist_user(db_session)
    base = datetime.now(UTC)
    timestamps = [base - timedelta(minutes=offset) for offset in (3, 0, 5, 2, 4)]
    for i, ts in enumerate(timestamps):
        await _persist_trip(db_session, user.id, f"t-{i}", created_at=ts)

    body = (await client.get("/api/trips", headers=_auth(user))).json()
    created_strs = [t["created_at"] for t in body["trips"]]
    parsed = [datetime.fromisoformat(s) for s in created_strs]
    for earlier, later in zip(parsed[1:], parsed[:-1], strict=True):
        assert earlier < later
