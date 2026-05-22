"""SSE auth integration test — exercises the ``current_user_or_sse`` dep
end-to-end through the real FastAPI ``stream_trip`` endpoint.

Scope: auth path only (header vs query token resolution through the real
endpoint). Queue/runner behavior is covered by the Batch 2e tests — this
file deliberately stubs the session and does not exercise ``trip_runner``.

Uses a stub ``AsyncSession`` (same pattern as ``tests/unit/auth/test_deps.py``)
so the test runs without a live Postgres. The integration value is wiring
``HTTPBearer`` + ``access_token`` query param + the actual endpoint
together; the underlying DB is incidental.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from plus_one.api.trips import router as trips_router
from plus_one.core.auth.jwt import create_access_token
from plus_one.core.db.models import Trip, User
from plus_one.core.db.session import get_request_session
from plus_one.services import trip_runner

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


class _StubSession:
    """Returns a fixed User for any .get(User, ...), and a fixed Trip for
    .get(Trip, ...). Everything else is a no-op."""

    def __init__(self, user: User, trip: Trip) -> None:
        self._user = user
        self._trip = trip

    async def get(self, model: type[Any], pk: uuid.UUID) -> Any:
        del pk
        if model is User:
            return self._user
        if model is Trip:
            return self._trip
        return None


def _make_user_and_trip() -> tuple[User, Trip]:
    user = User(email="sse@example.com", username="u_" + uuid.uuid4().hex[:10], password_hash="x", is_active=True)
    user.id = uuid.uuid4()
    trip = Trip(user_id=user.id, destination="Tokyo", free_text=None, status="running")
    trip.id = uuid.uuid4()
    return user, trip


def _make_app(user: User, trip: Trip) -> FastAPI:
    app = FastAPI()
    app.include_router(trips_router)

    async def fake_session() -> AsyncIterator[_StubSession]:
        yield _StubSession(user, trip)

    app.dependency_overrides[get_request_session] = fake_session
    return app


def _seed_one_event_then_eof(trip_id: uuid.UUID) -> None:
    """Register the per-trip queue and prime a single event + EOF so the
    SSE generator yields one frame and exits cleanly within the test."""
    trip_runner.register(trip_id)
    queue = trip_runner._queues[trip_id]
    queue.put_nowait({"name": "started", "trip_id": str(trip_id)})
    queue.put_nowait(trip_runner._EOF)


@pytest.mark.integration
def test_stream_requires_auth() -> None:
    user, trip = _make_user_and_trip()
    app = _make_app(user, trip)
    client = TestClient(app)

    resp = client.get(f"/api/trips/{trip.id}/stream")
    assert resp.status_code == 401


@pytest.mark.integration
def test_stream_accepts_header_token() -> None:
    user, trip = _make_user_and_trip()
    token = create_access_token(user.id)
    _seed_one_event_then_eof(trip.id)

    app = _make_app(user, trip)
    client = TestClient(app)

    with client.stream(
        "GET",
        f"/api/trips/{trip.id}/stream",
        headers={"Authorization": f"Bearer {token}"},
    ) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        body = b"".join(resp.iter_bytes())
        assert b"event: started" in body


@pytest.mark.integration
def test_stream_accepts_query_token() -> None:
    user, trip = _make_user_and_trip()
    token = create_access_token(user.id)
    _seed_one_event_then_eof(trip.id)

    app = _make_app(user, trip)
    client = TestClient(app)

    with client.stream(
        "GET",
        f"/api/trips/{trip.id}/stream",
        params={"access_token": token},
    ) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        body = b"".join(resp.iter_bytes())
        assert b"event: started" in body


@pytest.mark.integration
def test_stream_header_takes_precedence_over_query() -> None:
    """If both are present, the header is the source of truth — the query
    param fallback only kicks in when no Bearer header is set."""
    user, trip = _make_user_and_trip()
    valid_header_token = create_access_token(user.id)
    # A syntactically-valid-looking but unsigned-by-us garbage token. If the
    # endpoint preferred the query param, this request would 401 on decode.
    _seed_one_event_then_eof(trip.id)

    app = _make_app(user, trip)
    client = TestClient(app)

    with client.stream(
        "GET",
        f"/api/trips/{trip.id}/stream",
        headers={"Authorization": f"Bearer {valid_header_token}"},
        params={"access_token": "not-a-real-jwt"},
    ) as resp:
        assert resp.status_code == 200
        body = b"".join(resp.iter_bytes())
        assert b"event: started" in body
