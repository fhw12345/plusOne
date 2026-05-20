"""Integration-ish tests for the Companions API.

Stub-session pattern matches tests/integration/test_trips_sse_auth.py and
tests/integration/test_profile_api.py. Live-DB CRUD round-trips are
guarded by alembic upgrade/downgrade in CI plus the per-PR smoke curl.

The stub session implements the minimum surface the four CRUD endpoints
use: an in-memory companion store keyed by id with helpers that interpret
each SQL pattern (count, name-collision, fetch-by-id). It's deliberately
not a generic SQL executor — readers see one mapped pattern per assertion.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from plus_one.api.companions import router as companions_router
from plus_one.core.auth.jwt import create_access_token
from plus_one.core.db.models import Companion, User
from plus_one.core.db.session import get_request_session

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.sql import Select


class _ScalarResult:
    def __init__(self, value: Any) -> None:
        self._value = value

    def scalar_one(self) -> Any:
        return self._value

    def scalar_one_or_none(self) -> Any:
        return self._value


class _ScalarsList:
    def __init__(self, items: list[Any]) -> None:
        self._items = items

    def all(self) -> list[Any]:
        return self._items


class _ListResult:
    def __init__(self, items: list[Any]) -> None:
        self._items = items

    def scalars(self) -> _ScalarsList:
        return _ScalarsList(self._items)


class _StubSession:
    """In-memory companion store the four endpoints can drive against.

    Interprets the SQL statements the endpoints issue:
      - `SELECT count(...) WHERE user_id = ...` -> count for this user
      - `SELECT id WHERE user_id == .. AND lower(name) == ..` -> collision check
      - `SELECT * WHERE user_id == .. ORDER BY created_at ASC` -> list
      - `session.get(Companion, id)` -> single fetch
    """

    def __init__(self, user: User) -> None:
        self._user = user
        self.companions: dict[uuid.UUID, Companion] = {}
        self.deleted: list[uuid.UUID] = []
        # Test-side knob to simulate concurrent-write IntegrityError on flush.
        self.flush_raises: Exception | None = None

    # === Mutation API the endpoints call ===

    def add(self, obj: Any) -> None:
        if isinstance(obj, Companion):
            from datetime import UTC, datetime

            if obj.id is None:
                obj.id = uuid.uuid4()
            now = datetime.now(UTC)
            if getattr(obj, "created_at", None) is None:
                obj.created_at = now
            if getattr(obj, "updated_at", None) is None:
                obj.updated_at = now
            self.companions[obj.id] = obj

    async def delete(self, obj: Any) -> None:
        if isinstance(obj, Companion):
            self.companions.pop(obj.id, None)
            self.deleted.append(obj.id)

    async def flush(self) -> None:
        if self.flush_raises is not None:
            exc = self.flush_raises
            self.flush_raises = None
            raise exc

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None

    async def get(self, model: type[Any], pk: uuid.UUID) -> Any:
        if model is User:
            return self._user
        if model is Companion:
            return self.companions.get(pk)
        return None

    async def execute(self, stmt: Select[Any]) -> Any:
        text = str(stmt.compile(compile_kwargs={"literal_binds": False}))
        owned = [c for c in self.companions.values() if c.user_id == self._user.id]
        if "count(" in text.lower():
            return _ScalarResult(len(owned))
        if "lower(" in text.lower():
            # Name-collision check. Pull the bound name + optional exclude id.
            params = stmt.compile().params
            name = params.get("lower_1") or params.get("param_1")
            # Fallback: scan all positional binds for a string.
            if name is None:
                for v in params.values():
                    if isinstance(v, str):
                        name = v
                        break
            exclude_id = params.get("id_1")
            matches = [
                c
                for c in owned
                if c.name.lower() == (name or "").lower()
                and (exclude_id is None or c.id != exclude_id)
            ]
            return _ScalarResult(matches[0].id if matches else None)
        # Otherwise, list query — order by created_at ASC.
        ordered = sorted(owned, key=lambda c: c.created_at)
        return _ListResult(ordered)


def _make_user() -> User:
    user = User(email="comp@example.com", is_active=True)
    user.id = uuid.uuid4()
    return user


def _make_app(session: _StubSession) -> FastAPI:
    app = FastAPI()
    app.include_router(companions_router)

    async def fake_session() -> AsyncIterator[_StubSession]:
        yield session

    app.dependency_overrides[get_request_session] = fake_session
    return app


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


@pytest.mark.integration
def test_list_empty() -> None:
    user = _make_user()
    client = TestClient(_make_app(_StubSession(user)))
    resp = client.get("/api/companions", headers=_auth(user))
    assert resp.status_code == 200
    assert resp.json() == {"companions": []}


@pytest.mark.integration
def test_post_creates_companion() -> None:
    user = _make_user()
    session = _StubSession(user)
    client = TestClient(_make_app(session))

    resp = client.post(
        "/api/companions",
        headers=_auth(user),
        json={
            "name": "Anna",
            "explicit_preferences": {"loves": ["matcha"], "hates": []},
            "constraints": {"dietary": ["vegetarian"]},
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Anna"
    assert body["explicit_preferences"]["loves"] == ["matcha"]
    assert body["constraints"]["dietary"] == ["vegetarian"]
    assert len(session.companions) == 1


@pytest.mark.integration
def test_post_duplicate_name_case_insensitive_returns_409() -> None:
    user = _make_user()
    session = _StubSession(user)
    client = TestClient(_make_app(session))

    client.post("/api/companions", headers=_auth(user), json={"name": "Anna"})
    resp = client.post("/api/companions", headers=_auth(user), json={"name": "ANNA"})
    assert resp.status_code == 409
    assert resp.json()["detail"] == "companion_name_taken"


@pytest.mark.integration
def test_post_at_cap_returns_409() -> None:
    user = _make_user()
    session = _StubSession(user)
    # Seed 20 directly.
    from datetime import UTC, datetime

    for i in range(20):
        c = Companion(
            user_id=user.id,
            name=f"c{i}",
            explicit_preferences={},
            constraints={},
        )
        c.id = uuid.uuid4()
        c.created_at = datetime.now(UTC)
        c.updated_at = datetime.now(UTC)
        session.companions[c.id] = c

    client = TestClient(_make_app(session))
    resp = client.post("/api/companions", headers=_auth(user), json={"name": "Bob"})
    assert resp.status_code == 409
    assert resp.json()["detail"] == "companion_limit_reached"


@pytest.mark.integration
def test_put_updates_companion() -> None:
    user = _make_user()
    session = _StubSession(user)
    client = TestClient(_make_app(session))
    created = client.post(
        "/api/companions", headers=_auth(user), json={"name": "Anna"}
    ).json()
    cid = created["id"]

    resp = client.put(
        f"/api/companions/{cid}",
        headers=_auth(user),
        json={
            "name": "Anna",
            "explicit_preferences": {"loves": ["sushi"], "hates": []},
            "constraints": {},
        },
    )
    assert resp.status_code == 200
    assert resp.json()["explicit_preferences"]["loves"] == ["sushi"]


@pytest.mark.integration
def test_put_nonexistent_returns_404() -> None:
    user = _make_user()
    session = _StubSession(user)
    client = TestClient(_make_app(session))
    resp = client.put(
        f"/api/companions/{uuid.uuid4()}",
        headers=_auth(user),
        json={"name": "X", "explicit_preferences": {"loves": [], "hates": []}, "constraints": {}},
    )
    assert resp.status_code == 404


@pytest.mark.integration
def test_get_put_delete_cross_user_returns_404() -> None:
    """User B cannot see/modify/delete user A's companion. All return 404."""
    user_a = _make_user()
    user_b = _make_user()
    session = _StubSession(user_b)  # session pretends user_b is current
    # Seed a companion owned by user_a in the shared store.
    from datetime import UTC, datetime

    c = Companion(user_id=user_a.id, name="A", explicit_preferences={}, constraints={})
    c.id = uuid.uuid4()
    c.created_at = datetime.now(UTC)
    c.updated_at = datetime.now(UTC)
    session.companions[c.id] = c

    client = TestClient(_make_app(session))
    # PUT
    put_resp = client.put(
        f"/api/companions/{c.id}",
        headers=_auth(user_b),
        json={"name": "B", "explicit_preferences": {"loves": [], "hates": []}, "constraints": {}},
    )
    assert put_resp.status_code == 404
    # DELETE
    del_resp = client.delete(f"/api/companions/{c.id}", headers=_auth(user_b))
    assert del_resp.status_code == 404


@pytest.mark.integration
def test_delete_companion() -> None:
    user = _make_user()
    session = _StubSession(user)
    client = TestClient(_make_app(session))
    cid = client.post("/api/companions", headers=_auth(user), json={"name": "X"}).json()["id"]

    resp = client.delete(f"/api/companions/{cid}", headers=_auth(user))
    assert resp.status_code == 204
    assert cid in [str(d) for d in session.deleted]


@pytest.mark.integration
def test_post_validation_empty_name() -> None:
    user = _make_user()
    session = _StubSession(user)
    client = TestClient(_make_app(session))
    resp = client.post("/api/companions", headers=_auth(user), json={"name": ""})
    assert resp.status_code == 422


@pytest.mark.integration
def test_post_validation_name_too_long() -> None:
    user = _make_user()
    session = _StubSession(user)
    client = TestClient(_make_app(session))
    resp = client.post(
        "/api/companions", headers=_auth(user), json={"name": "x" * 101}
    )
    assert resp.status_code == 422


@pytest.mark.integration
def test_post_validation_unknown_constraint_key() -> None:
    user = _make_user()
    session = _StubSession(user)
    client = TestClient(_make_app(session))
    resp = client.post(
        "/api/companions",
        headers=_auth(user),
        json={"name": "X", "constraints": {"unknown": True}},
    )
    assert resp.status_code == 422


@pytest.mark.integration
def test_no_auth_returns_401_on_each_verb() -> None:
    user = _make_user()
    client = TestClient(_make_app(_StubSession(user)))
    cid = uuid.uuid4()
    assert client.get("/api/companions").status_code == 401
    assert client.post("/api/companions", json={"name": "X"}).status_code == 401
    assert (
        client.put(
            f"/api/companions/{cid}",
            json={"name": "X", "explicit_preferences": {"loves": [], "hates": []}, "constraints": {}},
        ).status_code
        == 401
    )
    assert client.delete(f"/api/companions/{cid}").status_code == 401
