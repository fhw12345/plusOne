"""Integration-ish tests for the Profile API.

Uses a stub AsyncSession (same pattern as tests/integration/test_trips_sse_auth.py)
to exercise the FastAPI wiring + Pydantic validation without a live Postgres.
The DB-backed paths (real INSERT/UPDATE round-trip) are guarded by the
alembic upgrade/downgrade round-trip in CI plus the per-PR smoke curl.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from plus_one.api.profile import router as profile_router
from plus_one.core.auth.jwt import create_access_token
from plus_one.core.db.models import Profile, User
from plus_one.core.db.session import get_request_session

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


class _StubResult:
    def __init__(self, value: Any = None) -> None:
        self._value = value

    def scalar_one_or_none(self) -> Any:
        return self._value


class _StubSession:
    """Minimal AsyncSession surface for the profile endpoints.

    Holds a single ``Profile`` row keyed by ``user_id``. ``execute`` returns
    it for ``SELECT ... WHERE user_id == :uid``; ``get(User, ...)`` returns
    the fixed user for the auth dependency.
    """

    def __init__(self, user: User, profile: Profile | None = None) -> None:
        self._user = user
        self.profile = profile
        self.added: list[object] = []

    async def get(self, model: type[Any], pk: uuid.UUID) -> Any:
        del pk
        if model is User:
            return self._user
        return None

    async def execute(self, _stmt: object) -> _StubResult:
        return _StubResult(self.profile)

    def add(self, obj: object) -> None:
        if isinstance(obj, Profile):
            # Mimic the FK assignment that flush would normally trigger.
            self.profile = obj
        self.added.append(obj)

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


def _make_user() -> User:
    user = User(email="profile@example.com", is_active=True)
    user.id = uuid.uuid4()
    return user


def _make_app(session: _StubSession) -> FastAPI:
    app = FastAPI()
    app.include_router(profile_router)

    async def fake_session() -> AsyncIterator[_StubSession]:
        yield session

    app.dependency_overrides[get_request_session] = fake_session
    return app


def _auth_headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


@pytest.mark.integration
def test_get_profile_with_no_row_returns_all_defaults() -> None:
    """Lazy: no row, GET returns all-default response WITHOUT creating a row."""
    user = _make_user()
    session = _StubSession(user, profile=None)
    client = TestClient(_make_app(session))

    resp = client.get("/api/profile", headers=_auth_headers(user))
    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "demographics": {"age_range": None, "language": None},
        "travel_style": {"budget_sensitivity": None, "pace": None, "comfort": None},
        "explicit_preferences": {"loves": [], "hates": []},
        "visited_cities": [],
    }
    assert session.added == []  # NO row created


@pytest.mark.integration
def test_get_profile_no_auth_returns_401() -> None:
    user = _make_user()
    client = TestClient(_make_app(_StubSession(user)))
    assert client.get("/api/profile").status_code == 401


@pytest.mark.integration
def test_put_profile_creates_row_on_first_call() -> None:
    user = _make_user()
    session = _StubSession(user, profile=None)
    client = TestClient(_make_app(session))

    body = {
        "demographics": {"age_range": "30-40"},
        "travel_style": {"pace": "relaxed"},
        "explicit_preferences": {"loves": ["ramen"], "hates": ["queues"]},
        "visited_cities": [{"city": "Tokyo", "year": 2024, "rating": 5}],
    }
    resp = client.put("/api/profile", headers=_auth_headers(user), json=body)
    assert resp.status_code == 200
    out = resp.json()
    assert out["explicit_preferences"] == {"loves": ["ramen"], "hates": ["queues"]}
    assert out["visited_cities"][0]["city"] == "Tokyo"
    # A Profile row was added (lazy create).
    assert any(isinstance(o, Profile) for o in session.added)


@pytest.mark.integration
def test_put_profile_updates_in_place_when_row_exists() -> None:
    user = _make_user()
    existing = Profile(
        user_id=user.id,
        demographics={},
        travel_style={},
        explicit_preferences={"loves": ["old"], "hates": []},
        visited_cities=[],
        implicit_preferences=[],
    )
    session = _StubSession(user, profile=existing)
    client = TestClient(_make_app(session))

    body = {
        "demographics": {},
        "travel_style": {},
        "explicit_preferences": {"loves": ["new"], "hates": []},
        "visited_cities": [],
    }
    resp = client.put("/api/profile", headers=_auth_headers(user), json=body)
    assert resp.status_code == 200
    # Same row, updated in place — no new row added.
    assert not any(isinstance(o, Profile) and o is not existing for o in session.added)
    assert existing.explicit_preferences == {"loves": ["new"], "hates": []}


@pytest.mark.integration
def test_put_profile_rejects_oversized_loves_list() -> None:
    user = _make_user()
    session = _StubSession(user, profile=None)
    client = TestClient(_make_app(session))

    body = {
        "demographics": {},
        "travel_style": {},
        "explicit_preferences": {"loves": [f"x{i}" for i in range(51)], "hates": []},
        "visited_cities": [],
    }
    resp = client.put("/api/profile", headers=_auth_headers(user), json=body)
    assert resp.status_code == 422


@pytest.mark.integration
def test_put_profile_rejects_oversized_visited_cities() -> None:
    user = _make_user()
    session = _StubSession(user, profile=None)
    client = TestClient(_make_app(session))

    body = {
        "demographics": {},
        "travel_style": {},
        "explicit_preferences": {"loves": [], "hates": []},
        "visited_cities": [{"city": f"c{i}", "year": 2024} for i in range(101)],
    }
    resp = client.put("/api/profile", headers=_auth_headers(user), json=body)
    assert resp.status_code == 422


@pytest.mark.integration
def test_put_profile_rejects_unknown_demographics_key() -> None:
    user = _make_user()
    session = _StubSession(user, profile=None)
    client = TestClient(_make_app(session))

    body = {
        "demographics": {"unknown_key": "x"},
        "travel_style": {},
        "explicit_preferences": {"loves": [], "hates": []},
        "visited_cities": [],
    }
    resp = client.put("/api/profile", headers=_auth_headers(user), json=body)
    assert resp.status_code == 422


@pytest.mark.integration
def test_put_profile_rejects_implicit_preferences_in_body() -> None:
    """Client must not write implicit_preferences — extra-forbid on body."""
    user = _make_user()
    session = _StubSession(user, profile=None)
    client = TestClient(_make_app(session))

    body = {
        "demographics": {},
        "travel_style": {},
        "explicit_preferences": {"loves": [], "hates": []},
        "visited_cities": [],
        "implicit_preferences": [{"sneaky": "yes"}],
    }
    resp = client.put("/api/profile", headers=_auth_headers(user), json=body)
    assert resp.status_code == 422
