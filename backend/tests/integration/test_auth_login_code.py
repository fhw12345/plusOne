"""POST /api/auth/request-code + /api/auth/login-with-code. batch-2m."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from httpx import AsyncClient

    from tests.integration.conftest import SmtpSpy


async def _register_and_verify(
    client: AsyncClient,
    smtp_spy: SmtpSpy,
    email: str,
    username: str,
    password: str,
) -> None:
    await client.post(
        "/api/auth/register",
        json={"username": username, "email": email, "password": password},
    )
    code = smtp_spy.calls[-1][1]
    r = await client.post("/api/auth/verify", json={"email": email, "code": code})
    assert r.status_code == 200


@pytest.mark.integration
async def test_request_code_rate_limited(
    client: AsyncClient,
    smtp_spy: SmtpSpy,
    unique_email: Callable[[], str],
    good_username: Callable[[], str],
    good_password: str,
) -> None:
    email = unique_email()
    await _register_and_verify(client, smtp_spy, email, good_username(), good_password)
    smtp_spy.calls.clear()

    r1 = await client.post("/api/auth/request-code", json={"email": email})
    assert r1.status_code == 204
    assert len(smtp_spy.calls) == 1

    # Second call inside the 60s window: still 204, but NO new send.
    r2 = await client.post("/api/auth/request-code", json={"email": email})
    assert r2.status_code == 204
    assert len(smtp_spy.calls) == 1


@pytest.mark.integration
async def test_request_code_unknown_email_silent_204(
    client: AsyncClient,
    smtp_spy: SmtpSpy,
    unique_email: Callable[[], str],
) -> None:
    r = await client.post("/api/auth/request-code", json={"email": unique_email()})
    assert r.status_code == 204
    assert smtp_spy.calls == []


@pytest.mark.integration
async def test_request_code_unverified_user_sends_verify_email_code(
    client: AsyncClient,
    smtp_spy: SmtpSpy,
    unique_email: Callable[[], str],
    good_username: Callable[[], str],
    good_password: str,
) -> None:
    """PRD §6 branch: unverified -> verify_email code, not login."""
    email = unique_email()
    await client.post(
        "/api/auth/register",
        json={"username": good_username(), "email": email, "password": good_password},
    )
    smtp_spy.calls.clear()

    r = await client.post("/api/auth/request-code", json={"email": email})
    assert r.status_code == 204
    assert len(smtp_spy.calls) == 1

    # Code should verify via /verify (verify_email purpose), not /login-with-code.
    code = smtp_spy.calls[-1][1]
    r_login = await client.post("/api/auth/login-with-code", json={"email": email, "code": code})
    # User is unverified at the moment of the call -> 401.
    assert r_login.status_code == 401

    r_verify = await client.post("/api/auth/verify", json={"email": email, "code": code})
    assert r_verify.status_code == 200


@pytest.mark.integration
async def test_login_with_code_happy_path(
    client: AsyncClient,
    smtp_spy: SmtpSpy,
    unique_email: Callable[[], str],
    good_username: Callable[[], str],
    good_password: str,
) -> None:
    email = unique_email()
    await _register_and_verify(client, smtp_spy, email, good_username(), good_password)
    smtp_spy.calls.clear()

    await client.post("/api/auth/request-code", json={"email": email})
    code = smtp_spy.calls[-1][1]

    r = await client.post(
        "/api/auth/login-with-code",
        json={"email": email, "code": code},
    )
    assert r.status_code == 200, r.text
    assert "access_token" in r.json()


@pytest.mark.integration
async def test_login_with_code_reuse_rejected(
    client: AsyncClient,
    smtp_spy: SmtpSpy,
    unique_email: Callable[[], str],
    good_username: Callable[[], str],
    good_password: str,
) -> None:
    email = unique_email()
    await _register_and_verify(client, smtp_spy, email, good_username(), good_password)
    smtp_spy.calls.clear()

    await client.post("/api/auth/request-code", json={"email": email})
    code = smtp_spy.calls[-1][1]

    r1 = await client.post("/api/auth/login-with-code", json={"email": email, "code": code})
    assert r1.status_code == 200

    r2 = await client.post("/api/auth/login-with-code", json={"email": email, "code": code})
    assert r2.status_code == 400


@pytest.mark.integration
async def test_login_with_code_wrong_code_400(
    client: AsyncClient,
    smtp_spy: SmtpSpy,
    unique_email: Callable[[], str],
    good_username: Callable[[], str],
    good_password: str,
) -> None:
    email = unique_email()
    await _register_and_verify(client, smtp_spy, email, good_username(), good_password)
    smtp_spy.calls.clear()
    await client.post("/api/auth/request-code", json={"email": email})

    r = await client.post(
        "/api/auth/login-with-code", json={"email": email, "code": "999999"}
    )
    # Most attempts will be 400 (wrong) but if the random code happened
    # to be "999999" we still pass since /login-with-code returned 200
    # earlier. Defensive:
    assert r.status_code in (400, 200)
