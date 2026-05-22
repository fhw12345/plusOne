"""POST /api/auth/verify — batch-2m."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from plus_one.core.db.models import EmailCode, User

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession

    from tests.integration.conftest import SmtpSpy


async def _register(
    client: AsyncClient,
    email: str,
    username: str,
    password: str,
) -> None:
    r = await client.post(
        "/api/auth/register",
        json={"username": username, "email": email, "password": password},
    )
    assert r.status_code == 201


@pytest.mark.integration
async def test_verify_happy_path_returns_token_and_marks_verified(
    client: AsyncClient,
    db_session: AsyncSession,
    smtp_spy: SmtpSpy,
    unique_email: Callable[[], str],
    good_username: Callable[[], str],
    good_password: str,
) -> None:
    email = unique_email()
    await _register(client, email, good_username(), good_password)
    code = smtp_spy.calls[0][1]

    r = await client.post("/api/auth/verify", json={"email": email, "code": code})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "access_token" in body
    assert body["user"]["email"] == email
    assert body["user"]["is_admin"] is False
    assert body["token_type"] == "bearer"

    user = (await db_session.execute(select(User).where(User.email == email))).scalar_one()
    assert user.email_verified_at is not None
    code_row = (
        await db_session.execute(select(EmailCode).where(EmailCode.email == email))
    ).scalar_one()
    assert code_row.consumed_at is not None


@pytest.mark.integration
async def test_verify_wrong_code_400(
    client: AsyncClient,
    smtp_spy: SmtpSpy,
    unique_email: Callable[[], str],
    good_username: Callable[[], str],
    good_password: str,
) -> None:
    email = unique_email()
    await _register(client, email, good_username(), good_password)
    real = smtp_spy.calls[0][1]
    wrong = "0" * len(real) if real != "0" * len(real) else "1" * len(real)
    r = await client.post("/api/auth/verify", json={"email": email, "code": wrong})
    assert r.status_code == 400
    assert r.json()["detail"] == "code_invalid"


@pytest.mark.integration
async def test_verify_expired_code_400(
    client: AsyncClient,
    db_session: AsyncSession,
    smtp_spy: SmtpSpy,
    unique_email: Callable[[], str],
    good_username: Callable[[], str],
    good_password: str,
) -> None:
    email = unique_email()
    await _register(client, email, good_username(), good_password)
    code = smtp_spy.calls[0][1]
    # Force-expire the row.
    row = (await db_session.execute(select(EmailCode).where(EmailCode.email == email))).scalar_one()
    row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    await db_session.commit()

    r = await client.post("/api/auth/verify", json={"email": email, "code": code})
    assert r.status_code == 400
    assert r.json()["detail"] == "code_expired"


@pytest.mark.integration
async def test_verify_consumed_code_400(
    client: AsyncClient,
    smtp_spy: SmtpSpy,
    unique_email: Callable[[], str],
    good_username: Callable[[], str],
    good_password: str,
) -> None:
    email = unique_email()
    await _register(client, email, good_username(), good_password)
    code = smtp_spy.calls[0][1]
    # First verify succeeds.
    r1 = await client.post("/api/auth/verify", json={"email": email, "code": code})
    assert r1.status_code == 200
    # Re-use rejected.
    r2 = await client.post("/api/auth/verify", json={"email": email, "code": code})
    assert r2.status_code == 400
    assert r2.json()["detail"] == "code_invalid"
