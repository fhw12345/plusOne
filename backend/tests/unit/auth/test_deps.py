"""Tests for the current_user FastAPI dependency.

We don't spin up Postgres for unit tests; instead we override the
``get_request_session`` dependency with an in-memory stub session that
returns a predetermined User (or None).
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Annotated, Any

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from plus_one.core.auth.deps import current_user
from plus_one.core.auth.jwt import create_access_token
from plus_one.core.db.models import User
from plus_one.core.db.session import get_request_session

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


class _StubSession:
    """Fakes the bits of AsyncSession that current_user touches (just .get)."""

    def __init__(self, user: User | None) -> None:
        self._user = user

    async def get(self, model: type[Any], pk: uuid.UUID) -> User | None:
        del model, pk
        return self._user


def _make_app(stub_user: User | None) -> FastAPI:
    app = FastAPI()

    async def fake_session() -> AsyncIterator[_StubSession]:
        yield _StubSession(stub_user)

    app.dependency_overrides[get_request_session] = fake_session

    @app.get("/me")
    async def me(user: Annotated[User, Depends(current_user)]) -> dict[str, str]:
        return {"id": str(user.id), "email": user.email}

    return app


def _make_user() -> User:
    user = User(email="x@example.com", is_active=True)
    user.id = uuid.uuid4()
    return user


@pytest.mark.unit
def test_no_authorization_header_returns_401() -> None:
    app = _make_app(_make_user())
    client = TestClient(app)
    resp = client.get("/me")
    assert resp.status_code == 401
    assert resp.headers.get("www-authenticate", "").lower().startswith("bearer")


@pytest.mark.unit
def test_malformed_authorization_header_returns_401() -> None:
    """Non-bearer scheme MUST be rejected with 401, not 403.

    Reviewer F3: previously the test accepted either 401 or 403 to dodge
    a behavior question. The contract is 401 with a WWW-Authenticate:
    Bearer header so callers know how to retry.
    """
    app = _make_app(_make_user())
    client = TestClient(app)
    resp = client.get("/me", headers={"Authorization": "Basic abc"})
    assert resp.status_code == 401
    assert resp.headers.get("www-authenticate", "").lower().startswith("bearer")


@pytest.mark.unit
def test_invalid_jwt_returns_401() -> None:
    app = _make_app(_make_user())
    client = TestClient(app)
    resp = client.get("/me", headers={"Authorization": "Bearer not.a.real.jwt"})
    assert resp.status_code == 401


@pytest.mark.unit
def test_valid_jwt_but_user_missing_returns_401() -> None:
    user = _make_user()
    token = create_access_token(user.id)
    app = _make_app(stub_user=None)
    client = TestClient(app)
    resp = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


@pytest.mark.unit
def test_valid_jwt_inactive_user_returns_401() -> None:
    user = _make_user()
    user.is_active = False
    token = create_access_token(user.id)
    app = _make_app(stub_user=user)
    client = TestClient(app)
    resp = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


@pytest.mark.unit
def test_valid_jwt_active_user_succeeds() -> None:
    user = _make_user()
    token = create_access_token(user.id)
    app = _make_app(stub_user=user)
    client = TestClient(app)
    resp = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json() == {"id": str(user.id), "email": user.email}
