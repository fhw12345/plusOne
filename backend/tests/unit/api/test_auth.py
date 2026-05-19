"""Auth endpoint tests — covers the SMTP-not-configured 503 path.

DB interactions still need integration tests; these are unit-level
scenarios that exercise the HTTP error-translation layer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from plus_one.api.auth import router as auth_router
from plus_one.config import settings
from plus_one.core.db.session import get_request_session

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


class _StubSession:
    """Minimal AsyncSession surface used by /auth/request-link."""

    def __init__(self) -> None:
        self.added: list[object] = []

    async def execute(self, *args: object, **kwargs: object) -> _StubResult:
        del args, kwargs
        return _StubResult()

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        return None


class _StubResult:
    def scalar_one_or_none(self) -> None:
        return None


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(auth_router)

    async def fake_session() -> AsyncIterator[_StubSession]:
        yield _StubSession()

    app.dependency_overrides[get_request_session] = fake_session
    return app


@pytest.mark.unit
def test_request_link_returns_503_when_email_sender_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reviewer B3: default sender raises NotImplementedError; the HTTP
    layer must translate that to 503 with a stable error code rather
    than leaking a 500."""
    monkeypatch.setattr(settings, "allow_console_email_sender", False)
    client = TestClient(_make_app())
    resp = client.post("/api/auth/request-link", json={"email": "x@example.com"})
    assert resp.status_code == 503
    assert resp.json()["detail"] == "email_sender_not_configured"


@pytest.mark.unit
def test_request_link_returns_204_with_console_sender_optin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "allow_console_email_sender", True)
    client = TestClient(_make_app())
    resp = client.post("/api/auth/request-link", json={"email": "x@example.com"})
    assert resp.status_code == 204


@pytest.mark.unit
def test_dev_last_link_returns_404_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Env-guard: the dev endpoint must 404 when app_env != development."""
    monkeypatch.setattr(settings, "app_env", "production")
    client = TestClient(_make_app())
    resp = client.get("/api/auth/dev/last-link", params={"email": "x@example.com"})
    assert resp.status_code == 404


@pytest.mark.unit
def test_dev_last_link_returns_404_when_no_link_issued(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dev env, but no link captured yet for this email → 404."""
    from plus_one.core.auth import email as email_mod

    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(email_mod, "_DEV_LAST_LINKS", {})
    client = TestClient(_make_app())
    resp = client.get(
        "/api/auth/dev/last-link",
        params={"email": "nobody@example.com"},
    )
    assert resp.status_code == 404


@pytest.mark.unit
def test_dev_last_link_returns_token_after_console_send(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Console sender populates the map; dev endpoint returns the token."""
    from plus_one.core.auth import email as email_mod

    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(email_mod, "_DEV_LAST_LINKS", {})

    sender = email_mod._ConsoleEmailSender()
    import asyncio

    asyncio.run(
        sender.send_magic_link(
            to="captured@example.com",
            link="http://localhost:3000/auth/exchange?token=abcdef0123456789",
        )
    )

    client = TestClient(_make_app())
    resp = client.get(
        "/api/auth/dev/last-link",
        params={"email": "captured@example.com"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"token": "abcdef0123456789"}


@pytest.mark.unit
def test_me_returns_401_without_token() -> None:
    """`/api/auth/me` must 401 when no Authorization header is present."""
    client = TestClient(_make_app())
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401
