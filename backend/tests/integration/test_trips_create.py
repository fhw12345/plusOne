"""Integration tests for ``POST /api/trips`` + ``GET /api/trips/{id}`` —
batch-2o structured hints (date_start, date_end, budget_amount,
budget_currency).

The BackgroundTask path normally schedules ``run_trip`` which would open
its own session and try to talk to real agents. We monkeypatch
``BackgroundTasks.add_task`` to a no-op so the test stays focused on the
HTTP boundary: body validation, DB persistence, and TripDetail echo.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from plus_one.api.trips import router as trips_router
from plus_one.config import settings
from plus_one.core.auth.jwt import create_access_token
from plus_one.core.db.models import Trip, User
from plus_one.core.db.session import get_request_session

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


async def _persist_user(session: AsyncSession) -> User:
    user = User(
        email=f"create-{uuid.uuid4().hex[:8]}@example.com",
        username="u_" + uuid.uuid4().hex[:10],
        password_hash="x",
        is_active=True,
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
async def client(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[AsyncClient]:
    # Neutralise the BackgroundTask so the runner doesn't spin up. We only
    # care about the synchronous request/response + DB row in these tests.
    from fastapi import BackgroundTasks

    def _noop_add_task(self: BackgroundTasks, *_a: Any, **_kw: Any) -> None:
        return None

    monkeypatch.setattr(BackgroundTasks, "add_task", _noop_add_task)

    # batch-2t: stub the synchronous clarifier so these tests don't reach
    # the LLM. Tests that want to exercise the clarifier path set their
    # own monkeypatch via the dedicated test_clarifier_api module.
    async def _noop_clarifier(**_kw: Any) -> list[dict[str, str]]:
        return []

    from plus_one.api import trips as trips_mod

    monkeypatch.setattr(trips_mod, "run_clarifier", _noop_clarifier)

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


# === Happy path — all four fields ========================================


@pytest.mark.integration
async def test_create_trip_persists_all_structured_fields(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _persist_user(db_session)
    body = {
        "destination": "tokyo",
        "date_start": "2026-10-12T00:00:00Z",
        "date_end": "2026-10-19T00:00:00Z",
        "budget_amount": 2500,
        "budget_currency": "USD",
    }
    resp = await client.post("/api/trips", json=body, headers=_auth(user))
    assert resp.status_code == 201, resp.text
    trip_id = uuid.UUID(resp.json()["trip_id"])

    trip = await db_session.get(Trip, trip_id)
    assert trip is not None
    assert trip.destination == "tokyo"
    assert trip.date_start is not None
    assert trip.date_end is not None
    assert trip.date_start.year == 2026
    assert trip.date_start.month == 10
    assert trip.budget_amount == 2500
    assert trip.budget_currency == "USD"


# === Back-compat — omit all four ==========================================


@pytest.mark.integration
async def test_create_trip_omits_all_structured_fields(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _persist_user(db_session)
    resp = await client.post(
        "/api/trips", json={"destination": "kyoto"}, headers=_auth(user)
    )
    assert resp.status_code == 201
    trip = await db_session.get(Trip, uuid.UUID(resp.json()["trip_id"]))
    assert trip is not None
    assert trip.date_start is None
    assert trip.date_end is None
    assert trip.budget_amount is None
    assert trip.budget_currency is None


# === Partial — dates only =================================================


@pytest.mark.integration
async def test_create_trip_dates_only(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _persist_user(db_session)
    resp = await client.post(
        "/api/trips",
        json={
            "destination": "osaka",
            "date_start": "2026-11-01T00:00:00Z",
            "date_end": "2026-11-05T00:00:00Z",
        },
        headers=_auth(user),
    )
    assert resp.status_code == 201
    trip = await db_session.get(Trip, uuid.UUID(resp.json()["trip_id"]))
    assert trip is not None
    assert trip.date_start is not None
    assert trip.date_end is not None
    assert trip.budget_amount is None
    assert trip.budget_currency is None


# === Partial — budget only ================================================


@pytest.mark.integration
async def test_create_trip_budget_only(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _persist_user(db_session)
    resp = await client.post(
        "/api/trips",
        json={"destination": "fukuoka", "budget_amount": 1000, "budget_currency": "JPY"},
        headers=_auth(user),
    )
    assert resp.status_code == 201
    trip = await db_session.get(Trip, uuid.UUID(resp.json()["trip_id"]))
    assert trip is not None
    assert trip.budget_amount == 1000
    assert trip.budget_currency == "JPY"
    assert trip.date_start is None
    assert trip.date_end is None


# === Validation: end before start =========================================


@pytest.mark.integration
async def test_create_trip_end_before_start_returns_422(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _persist_user(db_session)
    resp = await client.post(
        "/api/trips",
        json={
            "destination": "tokyo",
            "date_start": "2026-11-05T00:00:00Z",
            "date_end": "2026-11-02T00:00:00Z",
        },
        headers=_auth(user),
    )
    assert resp.status_code == 422
    assert "date_end must be on or after date_start" in resp.text


# === Validation: unknown currency =========================================


@pytest.mark.integration
async def test_create_trip_unknown_currency_returns_422(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _persist_user(db_session)
    resp = await client.post(
        "/api/trips",
        json={"destination": "tokyo", "budget_amount": 100, "budget_currency": "ZZZ"},
        headers=_auth(user),
    )
    assert resp.status_code == 422


# === Validation: negative budget ==========================================


@pytest.mark.integration
async def test_create_trip_negative_budget_returns_422(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _persist_user(db_session)
    resp = await client.post(
        "/api/trips",
        json={"destination": "tokyo", "budget_amount": -1},
        headers=_auth(user),
    )
    assert resp.status_code == 422


# === Validation: non-integer budget =======================================


@pytest.mark.integration
async def test_create_trip_non_integer_budget_returns_422(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _persist_user(db_session)
    resp = await client.post(
        "/api/trips",
        json={"destination": "tokyo", "budget_amount": 2.5},
        headers=_auth(user),
    )
    assert resp.status_code == 422


# === Detail echo: roundtrip ===============================================


@pytest.mark.integration
async def test_trip_detail_echoes_structured_fields(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _persist_user(db_session)
    create = await client.post(
        "/api/trips",
        json={
            "destination": "tokyo",
            "date_start": "2026-10-12T00:00:00Z",
            "date_end": "2026-10-19T00:00:00Z",
            "budget_amount": 2500,
            "budget_currency": "USD",
        },
        headers=_auth(user),
    )
    assert create.status_code == 201
    trip_id = create.json()["trip_id"]

    detail = await client.get(f"/api/trips/{trip_id}", headers=_auth(user))
    assert detail.status_code == 200
    body = detail.json()
    assert body["budget_amount"] == 2500
    assert body["budget_currency"] == "USD"
    assert body["date_start"].startswith("2026-10-12")
    assert body["date_end"].startswith("2026-10-19")


# === Detail echo: legacy trip returns nulls ===============================


@pytest.mark.integration
async def test_trip_detail_returns_null_for_legacy_trip(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _persist_user(db_session)
    trip = Trip(
        user_id=user.id, destination="legacy-city", free_text=None, status="pending"
    )
    # Avoid the lazy ``selectin`` load fired by the detail handler's
    # ``trip.companions`` access — assigning an empty list pre-populates
    # the relationship so the sync attribute read inside the request
    # doesn't try to spawn a greenlet from the test's session context.
    trip.companions = []
    db_session.add(trip)
    await db_session.flush()

    detail = await client.get(f"/api/trips/{trip.id}", headers=_auth(user))
    assert detail.status_code == 200
    body = detail.json()
    assert body["date_start"] is None
    assert body["date_end"] is None
    assert body["budget_amount"] is None
    assert body["budget_currency"] is None
