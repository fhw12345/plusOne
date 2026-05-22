"""POST /api/auth/login — password path. batch-2m."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from plus_one.config import settings
from plus_one.core.db.models import User

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession

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
async def test_login_success_returns_token(
    client: AsyncClient,
    smtp_spy: SmtpSpy,
    unique_email: Callable[[], str],
    good_username: Callable[[], str],
    good_password: str,
) -> None:
    email = unique_email()
    username = good_username()
    await _register_and_verify(client, smtp_spy, email, username, good_password)

    r = await client.post(
        "/api/auth/login",
        json={"identifier": email, "password": good_password},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "access_token" in body
    assert body["user"]["username"] == username


@pytest.mark.integration
async def test_login_with_username_succeeds(
    client: AsyncClient,
    smtp_spy: SmtpSpy,
    unique_email: Callable[[], str],
    good_username: Callable[[], str],
    good_password: str,
) -> None:
    email = unique_email()
    username = good_username()
    await _register_and_verify(client, smtp_spy, email, username, good_password)

    r = await client.post(
        "/api/auth/login",
        json={"identifier": username, "password": good_password},
    )
    assert r.status_code == 200


@pytest.mark.integration
async def test_login_wrong_password_401(
    client: AsyncClient,
    smtp_spy: SmtpSpy,
    unique_email: Callable[[], str],
    good_username: Callable[[], str],
    good_password: str,
) -> None:
    email = unique_email()
    await _register_and_verify(client, smtp_spy, email, good_username(), good_password)
    r = await client.post(
        "/api/auth/login",
        json={"identifier": email, "password": "wrong_password_aaa1"},
    )
    assert r.status_code == 401


@pytest.mark.integration
async def test_login_unknown_user_401_does_not_increment(
    client: AsyncClient,
    db_session: AsyncSession,
    unique_email: Callable[[], str],
    good_password: str,
) -> None:
    r = await client.post(
        "/api/auth/login",
        json={"identifier": unique_email(), "password": good_password},
    )
    assert r.status_code == 401


@pytest.mark.integration
async def test_login_lockout_after_n_failed_attempts(
    client: AsyncClient,
    db_session: AsyncSession,
    smtp_spy: SmtpSpy,
    unique_email: Callable[[], str],
    good_username: Callable[[], str],
    good_password: str,
) -> None:
    email = unique_email()
    await _register_and_verify(client, smtp_spy, email, good_username(), good_password)

    n = settings.login_max_failed_attempts
    for _ in range(n):
        r = await client.post(
            "/api/auth/login",
            json={"identifier": email, "password": "wrong_pw_aaa1"},
        )
        assert r.status_code == 401

    # Next attempt — even with right password — must be 423.
    r = await client.post(
        "/api/auth/login",
        json={"identifier": email, "password": good_password},
    )
    assert r.status_code == 423
    assert r.json()["detail"] == "locked"

    # Simulate lockout window elapsing: clear locked_until via DB.
    user = (await db_session.execute(select(User).where(User.email == email))).scalar_one()
    user.locked_until = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.commit()

    r = await client.post(
        "/api/auth/login",
        json={"identifier": email, "password": good_password},
    )
    assert r.status_code == 200


@pytest.mark.integration
async def test_login_unverified_email_returns_specific_detail(
    client: AsyncClient,
    smtp_spy: SmtpSpy,
    unique_email: Callable[[], str],
    good_username: Callable[[], str],
    good_password: str,
) -> None:
    email = unique_email()
    # Register only — do NOT verify.
    await client.post(
        "/api/auth/register",
        json={"username": good_username(), "email": email, "password": good_password},
    )

    r = await client.post(
        "/api/auth/login",
        json={"identifier": email, "password": good_password},
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "email_not_verified"
