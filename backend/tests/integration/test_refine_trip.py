"""Integration tests for POST /api/trips/{id}/refine (batch-2u).

Uses the same live-DB pattern as test_share.py / test_trips_delete.py.
Patches ``run_refine`` so we don't kick off a real LLM call — we just
verify the API contract (status codes, response shape, side effects on
the trip row + the spawned BackgroundTask).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

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


async def _persist_user(session: AsyncSession) -> User:
    user = User(
        email=f"refine-{uuid.uuid4().hex[:8]}@example.com",
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
        destination="kyoto",
        free_text=None,
        status=status,
    )
    session.add(trip)
    await session.flush()
    return trip


async def _persist_report(
    session: AsyncSession,
    trip_id: uuid.UUID,
    *,
    content: dict | None = None,
) -> Report:
    report = Report(
        trip_id=trip_id,
        content=content or {"items": [{"candidate": {"name": "Kiyomizu"}}]},
        trace=[],
    )
    session.add(report)
    await session.flush()
    return report


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
    # Stub run_refine so the BackgroundTask doesn't fire a real LLM call.
    fake_run_refine = AsyncMock(return_value=None)
    monkeypatch.setattr("plus_one.api.trips.run_refine", fake_run_refine)

    app = FastAPI()
    app.include_router(trips_router)

    async def fake_get_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_request_session] = fake_get_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Stash the mock on the client so tests can assert it.
        ac.fake_run_refine = fake_run_refine  # type: ignore[attr-defined]
        yield ac


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


# === Happy path ==========================================================


@pytest.mark.integration
async def test_refine_returns_202_with_new_report_id(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _persist_user(db_session)
    trip = await _persist_trip(db_session, user.id)
    await _persist_report(db_session, trip.id)
    await db_session.commit()

    resp = await client.post(
        f"/api/trips/{trip.id}/refine",
        headers=_auth(user),
        json={"hint": "swap kiyomizu for arashiyama"},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert set(body.keys()) == {"report_id", "status"}
    assert body["status"] == "running"
    # report_id is a fresh uuid pre-allocated by the API.
    uuid.UUID(body["report_id"])

    # Trip status flipped back to running so a subsequent refine 409s.
    await db_session.refresh(trip)
    assert trip.status == "running"

    # BackgroundTask was scheduled with the pre-allocated id.
    fake = client.fake_run_refine  # type: ignore[attr-defined]
    fake.assert_called_once()
    call_args = fake.call_args
    assert str(call_args.args[0]) == str(trip.id)
    assert str(call_args.args[4]) == body["report_id"]


@pytest.mark.integration
async def test_refine_strips_whitespace_from_hint(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _persist_user(db_session)
    trip = await _persist_trip(db_session, user.id)
    await _persist_report(db_session, trip.id)
    await db_session.commit()

    resp = await client.post(
        f"/api/trips/{trip.id}/refine",
        headers=_auth(user),
        json={"hint": "  more izakayas  \n"},
    )
    assert resp.status_code == 202
    fake = client.fake_run_refine  # type: ignore[attr-defined]
    # hint arg is positional index 2.
    assert fake.call_args.args[2] == "more izakayas"


# === Permission ==========================================================


@pytest.mark.integration
async def test_refine_404_for_non_owner(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    owner = await _persist_user(db_session)
    attacker = await _persist_user(db_session)
    trip = await _persist_trip(db_session, owner.id)
    await _persist_report(db_session, trip.id)
    await db_session.commit()

    resp = await client.post(
        f"/api/trips/{trip.id}/refine",
        headers=_auth(attacker),
        json={"hint": "swap something"},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "trip_not_found"


@pytest.mark.integration
async def test_refine_404_for_unknown_trip(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _persist_user(db_session)
    await db_session.commit()

    resp = await client.post(
        f"/api/trips/{uuid.uuid4()}/refine",
        headers=_auth(user),
        json={"hint": "anything"},
    )
    assert resp.status_code == 404


@pytest.mark.integration
async def test_refine_401_without_token(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _persist_user(db_session)
    trip = await _persist_trip(db_session, user.id)
    await _persist_report(db_session, trip.id)
    await db_session.commit()

    resp = await client.post(
        f"/api/trips/{trip.id}/refine",
        json={"hint": "swap"},
    )
    assert resp.status_code == 401


# === Status guards =======================================================


@pytest.mark.integration
async def test_refine_409_when_trip_running(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _persist_user(db_session)
    trip = await _persist_trip(db_session, user.id, status="running")
    await db_session.commit()

    resp = await client.post(
        f"/api/trips/{trip.id}/refine",
        headers=_auth(user),
        json={"hint": "swap"},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"] == "trip_busy"


@pytest.mark.integration
async def test_refine_409_when_trip_pending(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _persist_user(db_session)
    trip = await _persist_trip(db_session, user.id, status="pending")
    await db_session.commit()

    resp = await client.post(
        f"/api/trips/{trip.id}/refine",
        headers=_auth(user),
        json={"hint": "swap"},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"] == "trip_busy"


@pytest.mark.integration
async def test_refine_409_when_trip_aborted(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _persist_user(db_session)
    trip = await _persist_trip(db_session, user.id, status="aborted")
    await db_session.commit()

    resp = await client.post(
        f"/api/trips/{trip.id}/refine",
        headers=_auth(user),
        json={"hint": "swap"},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"] == "trip_not_complete"


@pytest.mark.integration
async def test_refine_409_when_trip_complete_but_no_report(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _persist_user(db_session)
    trip = await _persist_trip(db_session, user.id, status="complete")
    await db_session.commit()  # no report row

    resp = await client.post(
        f"/api/trips/{trip.id}/refine",
        headers=_auth(user),
        json={"hint": "swap"},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"] == "trip_not_complete"


# === Validation ==========================================================


@pytest.mark.integration
async def test_refine_422_empty_hint(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _persist_user(db_session)
    trip = await _persist_trip(db_session, user.id)
    await _persist_report(db_session, trip.id)
    await db_session.commit()

    resp = await client.post(
        f"/api/trips/{trip.id}/refine",
        headers=_auth(user),
        json={"hint": ""},
    )
    assert resp.status_code == 422


@pytest.mark.integration
async def test_refine_422_whitespace_only_hint(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _persist_user(db_session)
    trip = await _persist_trip(db_session, user.id)
    await _persist_report(db_session, trip.id)
    await db_session.commit()

    resp = await client.post(
        f"/api/trips/{trip.id}/refine",
        headers=_auth(user),
        json={"hint": "    \n\t  "},
    )
    assert resp.status_code == 422


@pytest.mark.integration
async def test_refine_422_long_hint(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _persist_user(db_session)
    trip = await _persist_trip(db_session, user.id)
    await _persist_report(db_session, trip.id)
    await db_session.commit()

    resp = await client.post(
        f"/api/trips/{trip.id}/refine",
        headers=_auth(user),
        json={"hint": "a" * 501},
    )
    assert resp.status_code == 422


# === GET /reports list ===================================================


@pytest.mark.integration
async def test_list_reports_returns_chronological_with_metadata(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _persist_user(db_session)
    trip = await _persist_trip(db_session, user.id)
    original = await _persist_report(
        db_session, trip.id, content={"items": [{"name": "a"}]}
    )
    await db_session.flush()
    refine_r = await _persist_report(
        db_session,
        trip.id,
        content={
            "items": [{"name": "b"}],
            "refine": {
                "previous_report_id": str(original.id),
                "hint": "swap a for b",
            },
        },
    )
    await db_session.commit()

    resp = await client.get(f"/api/trips/{trip.id}/reports", headers=_auth(user))
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["reports"]) == 2
    first, second = body["reports"]
    assert first["report_id"] == str(original.id)
    assert first["is_original"] is True
    assert first["hint"] is None
    assert first["previous_report_id"] is None
    assert second["report_id"] == str(refine_r.id)
    assert second["is_original"] is False
    assert second["hint"] == "swap a for b"
    assert second["previous_report_id"] == str(original.id)


@pytest.mark.integration
async def test_list_reports_404_for_non_owner(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    owner = await _persist_user(db_session)
    attacker = await _persist_user(db_session)
    trip = await _persist_trip(db_session, owner.id)
    await db_session.commit()

    resp = await client.get(f"/api/trips/{trip.id}/reports", headers=_auth(attacker))
    assert resp.status_code == 404


# === GET /reports/{report_id} ============================================


@pytest.mark.integration
async def test_get_report_returns_payload(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _persist_user(db_session)
    trip = await _persist_trip(db_session, user.id)
    report = await _persist_report(
        db_session, trip.id, content={"items": [{"name": "x"}]}
    )
    await db_session.commit()

    resp = await client.get(
        f"/api/trips/{trip.id}/reports/{report.id}", headers=_auth(user)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["report_id"] == str(report.id)
    assert body["trip_id"] == str(trip.id)
    assert body["is_original"] is True
    assert body["content"] == {"items": [{"name": "x"}]}


@pytest.mark.integration
async def test_get_report_404_when_report_belongs_to_other_trip(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _persist_user(db_session)
    trip_a = await _persist_trip(db_session, user.id)
    trip_b = await _persist_trip(db_session, user.id)
    report_a = await _persist_report(db_session, trip_a.id)
    await db_session.commit()

    resp = await client.get(
        f"/api/trips/{trip_b.id}/reports/{report_a.id}", headers=_auth(user)
    )
    assert resp.status_code == 404
