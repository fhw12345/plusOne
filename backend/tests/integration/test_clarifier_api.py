"""Integration tests for batch-2t clarifier API.

Covers:

- POST /api/trips returns ``status=clarifying`` + ``clarifier_questions``
  when the (monkeypatched) clarifier emits 1+ questions.
- POST /api/trips returns ``status=running`` + empty list on the
  pass-through path (clarifier returned 0).
- POST /api/trips/{id}/clarify happy path, 409 on re-submit, 422 on
  mismatched answer ids / empty text.
- POST /api/trips/{id}/clarify/skip happy path + 409 on already-running.
- Foreign-user calling /clarify returns 404.
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


async def _persist_user(session: AsyncSession) -> User:
    user = User(
        email=f"clarify-{uuid.uuid4().hex[:8]}@example.com",
        username="c_" + uuid.uuid4().hex[:10],
        password_hash="x",
        is_active=True,
    )
    session.add(user)
    await session.flush()
    return user


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


@pytest_asyncio.fixture
async def client_factory(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> Any:
    """Returns a callable: ``await make_client(clarifier_questions=[...])``.

    Pre-installs the BackgroundTasks no-op, then wires the clarifier to
    return whatever the test wants. Letting each test pick the response
    keeps the fixture minimal.
    """
    from fastapi import BackgroundTasks

    background_calls: list[tuple[Any, tuple[Any, ...], dict[str, Any]]] = []

    def _capturing_add_task(
        self: BackgroundTasks, func: Any, *args: Any, **kwargs: Any
    ) -> None:
        background_calls.append((func, args, kwargs))

    monkeypatch.setattr(BackgroundTasks, "add_task", _capturing_add_task)

    async def make_client(clarifier_questions: list[dict[str, str]]) -> AsyncClient:
        async def _stub_clarifier(**_kw: Any) -> list[dict[str, str]]:
            return clarifier_questions

        from plus_one.api import trips as trips_mod

        monkeypatch.setattr(trips_mod, "run_clarifier", _stub_clarifier)

        app = FastAPI()
        app.include_router(trips_router)

        async def fake_get_session() -> AsyncIterator[AsyncSession]:
            yield db_session

        app.dependency_overrides[get_request_session] = fake_get_session
        transport = ASGITransport(app=app)
        return AsyncClient(transport=transport, base_url="http://test")

    make_client.background_calls = background_calls  # type: ignore[attr-defined]
    return make_client


# === POST /api/trips ======================================================


@pytest.mark.integration
async def test_create_trip_pass_through_when_clarifier_empty(
    client_factory: Any, db_session: AsyncSession
) -> None:
    user = await _persist_user(db_session)
    async with await client_factory([]) as client:
        resp = await client.post(
            "/api/trips", json={"destination": "kyoto"}, headers=_auth(user)
        )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "running"
    assert body["clarifier_questions"] == []
    trip = await db_session.get(Trip, uuid.UUID(body["trip_id"]))
    assert trip is not None
    assert trip.status == "running"
    assert trip.clarifier_questions is None
    # run_trip was scheduled.
    assert len(client_factory.background_calls) == 1


@pytest.mark.integration
async def test_create_trip_clarifying_when_questions_returned(
    client_factory: Any, db_session: AsyncSession
) -> None:
    user = await _persist_user(db_session)
    questions = [
        {"id": "q1", "text": "fixed dates or flexible?"},
        {"id": "q2", "text": "okay with bus / metro / both?"},
    ]
    async with await client_factory(questions) as client:
        resp = await client.post(
            "/api/trips",
            json={"destination": "kyoto", "free_text": "quiet temples"},
            headers=_auth(user),
        )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "clarifying"
    assert body["clarifier_questions"] == questions
    trip = await db_session.get(Trip, uuid.UUID(body["trip_id"]))
    assert trip is not None
    assert trip.status == "clarifying"
    assert trip.clarifier_questions == questions
    # run_trip MUST NOT be scheduled in the clarifying path.
    assert client_factory.background_calls == []


# === POST /api/trips/{id}/clarify ========================================


@pytest.mark.integration
async def test_clarify_happy_path_flips_to_running(
    client_factory: Any, db_session: AsyncSession
) -> None:
    user = await _persist_user(db_session)
    questions = [{"id": "q1", "text": "fixed dates or flexible?"}]
    async with await client_factory(questions) as client:
        create = await client.post(
            "/api/trips", json={"destination": "kyoto"}, headers=_auth(user)
        )
        trip_id = create.json()["trip_id"]
        client_factory.background_calls.clear()
        resp = await client.post(
            f"/api/trips/{trip_id}/clarify",
            json={"answers": [{"id": "q1", "text": "fixed: may 4-7"}]},
            headers=_auth(user),
        )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"status": "running"}
    # Refresh from DB.
    db_session.expire_all()
    trip = await db_session.get(Trip, uuid.UUID(trip_id))
    assert trip is not None
    assert trip.status == "running"
    assert trip.clarifier_answers == [{"id": "q1", "text": "fixed: may 4-7"}]
    assert len(client_factory.background_calls) == 1


@pytest.mark.integration
async def test_clarify_second_call_returns_409(
    client_factory: Any, db_session: AsyncSession
) -> None:
    user = await _persist_user(db_session)
    async with await client_factory(
        [{"id": "q1", "text": "fixed dates or flexible?"}]
    ) as client:
        create = await client.post(
            "/api/trips", json={"destination": "kyoto"}, headers=_auth(user)
        )
        trip_id = create.json()["trip_id"]
        first = await client.post(
            f"/api/trips/{trip_id}/clarify",
            json={"answers": [{"id": "q1", "text": "fixed"}]},
            headers=_auth(user),
        )
        assert first.status_code == 200
        second = await client.post(
            f"/api/trips/{trip_id}/clarify",
            json={"answers": [{"id": "q1", "text": "fixed"}]},
            headers=_auth(user),
        )
    assert second.status_code == 409
    assert second.json()["detail"] == "trip_not_clarifying"


@pytest.mark.integration
async def test_clarify_mismatched_ids_returns_422(
    client_factory: Any, db_session: AsyncSession
) -> None:
    user = await _persist_user(db_session)
    async with await client_factory(
        [{"id": "q1", "text": "fixed dates or flexible?"}]
    ) as client:
        create = await client.post(
            "/api/trips", json={"destination": "kyoto"}, headers=_auth(user)
        )
        trip_id = create.json()["trip_id"]
        resp = await client.post(
            f"/api/trips/{trip_id}/clarify",
            json={"answers": [{"id": "qZ", "text": "huh?"}]},
            headers=_auth(user),
        )
    assert resp.status_code == 422


@pytest.mark.integration
async def test_clarify_empty_text_returns_422(
    client_factory: Any, db_session: AsyncSession
) -> None:
    user = await _persist_user(db_session)
    async with await client_factory(
        [{"id": "q1", "text": "fixed dates or flexible?"}]
    ) as client:
        create = await client.post(
            "/api/trips", json={"destination": "kyoto"}, headers=_auth(user)
        )
        trip_id = create.json()["trip_id"]
        resp = await client.post(
            f"/api/trips/{trip_id}/clarify",
            json={"answers": [{"id": "q1", "text": "   "}]},
            headers=_auth(user),
        )
    # Pydantic strips & enforces min_length=1 — the body shape itself fails.
    # We accept 422 either from FastAPI body validation or our own raise.
    assert resp.status_code == 422


@pytest.mark.integration
async def test_clarify_foreign_user_returns_404(
    client_factory: Any, db_session: AsyncSession
) -> None:
    owner = await _persist_user(db_session)
    attacker = await _persist_user(db_session)
    async with await client_factory(
        [{"id": "q1", "text": "fixed dates or flexible?"}]
    ) as client:
        create = await client.post(
            "/api/trips", json={"destination": "kyoto"}, headers=_auth(owner)
        )
        trip_id = create.json()["trip_id"]
        resp = await client.post(
            f"/api/trips/{trip_id}/clarify",
            json={"answers": [{"id": "q1", "text": "fixed"}]},
            headers=_auth(attacker),
        )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "trip_not_found"


# === POST /api/trips/{id}/clarify/skip ===================================


@pytest.mark.integration
async def test_skip_happy_path(
    client_factory: Any, db_session: AsyncSession
) -> None:
    user = await _persist_user(db_session)
    async with await client_factory(
        [{"id": "q1", "text": "fixed dates or flexible?"}]
    ) as client:
        create = await client.post(
            "/api/trips", json={"destination": "kyoto"}, headers=_auth(user)
        )
        trip_id = create.json()["trip_id"]
        client_factory.background_calls.clear()
        resp = await client.post(
            f"/api/trips/{trip_id}/clarify/skip", headers=_auth(user)
        )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"status": "running"}
    db_session.expire_all()
    trip = await db_session.get(Trip, uuid.UUID(trip_id))
    assert trip is not None
    assert trip.status == "running"
    assert trip.clarifier_answers is None
    assert len(client_factory.background_calls) == 1


@pytest.mark.integration
async def test_skip_already_running_returns_409(
    client_factory: Any, db_session: AsyncSession
) -> None:
    user = await _persist_user(db_session)
    async with await client_factory([]) as client:
        # No questions: trip is created directly in ``running``.
        create = await client.post(
            "/api/trips", json={"destination": "kyoto"}, headers=_auth(user)
        )
        trip_id = create.json()["trip_id"]
        resp = await client.post(
            f"/api/trips/{trip_id}/clarify/skip", headers=_auth(user)
        )
    assert resp.status_code == 409
    assert resp.json()["detail"] == "trip_not_clarifying"
