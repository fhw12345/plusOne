"""POST /api/auth/register — batch-2m."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from plus_one.core.auth.passwords import verify_password
from plus_one.core.db.models import EmailCode, User

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession

    from tests.integration.conftest import SmtpSpy


@pytest.mark.integration
async def test_register_happy_path_201_and_sends_code(
    client: AsyncClient,
    db_session: AsyncSession,
    smtp_spy: SmtpSpy,
    unique_email: Callable[[], str],
    good_username: Callable[[], str],
    good_password: str,
) -> None:
    email = unique_email()
    username = good_username()
    resp = await client.post(
        "/api/auth/register",
        json={"username": username, "email": email, "password": good_password},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["email"] == email
    assert "user_id" in body

    # User row exists, unverified, with Argon2id hash.
    user = (
        await db_session.execute(select(User).where(User.email == email))
    ).scalar_one()
    assert user.username == username
    assert user.email_verified_at is None
    assert user.is_admin is False
    assert user.password_hash.startswith("$argon2id$")
    assert verify_password(user.password_hash, good_password)

    # Verify code row exists.
    code = (
        await db_session.execute(
            select(EmailCode).where(EmailCode.email == email, EmailCode.purpose == "verify_email")
        )
    ).scalar_one()
    assert code.consumed_at is None

    # SMTP fired exactly once, to that email.
    assert len(smtp_spy.calls) == 1
    assert smtp_spy.calls[0][0] == email
    # The raw code matches the hash on the row.
    assert verify_password(code.code_hash, smtp_spy.calls[0][1])


@pytest.mark.integration
async def test_register_duplicate_email_409(
    client: AsyncClient,
    db_session: AsyncSession,
    smtp_spy: SmtpSpy,
    unique_email: Callable[[], str],
    good_username: Callable[[], str],
    good_password: str,
) -> None:
    del db_session  # autocommit handled by handlers via session reuse
    email = unique_email()
    payload = {"username": good_username(), "email": email, "password": good_password}
    r1 = await client.post("/api/auth/register", json=payload)
    assert r1.status_code == 201

    # Different username, same email -> 409 email_taken.
    r2 = await client.post(
        "/api/auth/register",
        json={"username": good_username(), "email": email, "password": good_password},
    )
    assert r2.status_code == 409
    assert r2.json()["detail"] == "email_taken"
    # No second email send.
    assert len(smtp_spy.calls) == 1


@pytest.mark.integration
async def test_register_duplicate_username_409(
    client: AsyncClient,
    smtp_spy: SmtpSpy,
    unique_email: Callable[[], str],
    good_username: Callable[[], str],
    good_password: str,
) -> None:
    username = good_username()
    r1 = await client.post(
        "/api/auth/register",
        json={"username": username, "email": unique_email(), "password": good_password},
    )
    assert r1.status_code == 201

    r2 = await client.post(
        "/api/auth/register",
        json={"username": username, "email": unique_email(), "password": good_password},
    )
    assert r2.status_code == 409
    assert r2.json()["detail"] == "username_taken"
    assert len(smtp_spy.calls) == 1


@pytest.mark.integration
async def test_register_weak_password_422(
    client: AsyncClient,
    unique_email: Callable[[], str],
    good_username: Callable[[], str],
) -> None:
    # Too short.
    r = await client.post(
        "/api/auth/register",
        json={"username": good_username(), "email": unique_email(), "password": "short"},
    )
    assert r.status_code == 422


@pytest.mark.integration
async def test_register_password_no_digit_422(
    client: AsyncClient,
    unique_email: Callable[[], str],
    good_username: Callable[[], str],
) -> None:
    r = await client.post(
        "/api/auth/register",
        json={
            "username": good_username(),
            "email": unique_email(),
            "password": "noDigitsHere!",
        },
    )
    assert r.status_code == 422


@pytest.mark.integration
async def test_register_bad_username_422(
    client: AsyncClient, unique_email: Callable[[], str], good_password: str
) -> None:
    r = await client.post(
        "/api/auth/register",
        json={"username": "Bad-Name!", "email": unique_email(), "password": good_password},
    )
    assert r.status_code == 422


@pytest.mark.integration
async def test_register_bad_email_422(
    client: AsyncClient, good_username: Callable[[], str], good_password: str
) -> None:
    r = await client.post(
        "/api/auth/register",
        json={"username": good_username(), "email": "not-an-email", "password": good_password},
    )
    assert r.status_code == 422
