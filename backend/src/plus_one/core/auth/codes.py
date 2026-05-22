"""Email-code issuance + verification (batch-2m).

Codes are 6-digit random strings (length configurable via
``settings.email_code_length``). Stored as Argon2id hashes in
``email_codes``. Single-use: enforced by a partial unique index on
``(email, purpose) WHERE consumed_at IS NULL`` plus an explicit
``UPDATE ... SET consumed_at`` of any prior active row inside
:func:`save_code`.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Literal

from sqlalchemy import select, update

from plus_one.config import settings
from plus_one.core.auth.passwords import _HASHER
from plus_one.core.db.models import EmailCode

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


CodePurpose = Literal["verify_email", "login"]


class CodeError(ValueError):
    """Base — code missing / wrong / expired / consumed."""


class CodeNotFoundError(CodeError):
    """No active code row for (email, purpose)."""


class CodeMismatchError(CodeError):
    """Active code row exists but the supplied code didn't verify."""


class CodeExpiredError(CodeError):
    """Active row exists but ``expires_at < now()``."""


def generate_code() -> str:
    """Return an N-digit cryptographically random numeric code.

    Length is :data:`settings.email_code_length` (default 6). Uses
    :func:`secrets.randbelow` so no modulo bias from ``random``.
    """
    n = settings.email_code_length
    upper = 10**n
    val = secrets.randbelow(upper)
    return f"{val:0{n}d}"


def hash_code(code: str) -> str:
    """Argon2id-hash a code (same hasher instance as passwords)."""
    return _HASHER.hash(code)


async def save_code(
    session: AsyncSession,
    *,
    email: str,
    purpose: CodePurpose,
    code: str,
    ttl_minutes: int | None = None,
) -> EmailCode:
    """Persist a fresh code, invalidating any prior active row first.

    Concurrency note: the partial unique index on
    ``(email, purpose) WHERE consumed_at IS NULL`` will reject a second
    INSERT if a prior active row is still live. The :func:`update` call
    consumes it inside the same transaction so the new INSERT lands
    cleanly.
    """
    now = datetime.now(UTC)
    expires_at = now + timedelta(
        minutes=ttl_minutes if ttl_minutes is not None else settings.email_code_ttl_minutes
    )
    # Invalidate any prior active row for this (email, purpose).
    await session.execute(
        update(EmailCode)
        .where(
            EmailCode.email == email,
            EmailCode.purpose == purpose,
            EmailCode.consumed_at.is_(None),
        )
        .values(consumed_at=now)
    )
    row = EmailCode(
        email=email,
        code_hash=hash_code(code),
        purpose=purpose,
        expires_at=expires_at,
    )
    session.add(row)
    await session.flush()
    return row


async def verify_code(
    session: AsyncSession,
    *,
    email: str,
    purpose: CodePurpose,
    code: str,
) -> EmailCode:
    """Find + verify the active code for (email, purpose).

    Raises:
        CodeNotFoundError: no active row.
        CodeExpiredError: active row past ``expires_at``.
        CodeMismatchError: row exists but code doesn't match.

    Returns the matched EmailCode row on success — caller MUST call
    :func:`consume_code` to mark it used.
    """
    result = await session.execute(
        select(EmailCode).where(
            EmailCode.email == email,
            EmailCode.purpose == purpose,
            EmailCode.consumed_at.is_(None),
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise CodeNotFoundError("no active code")

    now = datetime.now(UTC)
    if row.expires_at < now:
        raise CodeExpiredError("code expired")

    # Argon2 verify — constant-time on success path; mismatch raises.
    from argon2.exceptions import VerifyMismatchError  # noqa: PLC0415

    try:
        _HASHER.verify(row.code_hash, code)
    except VerifyMismatchError as exc:
        raise CodeMismatchError("code did not match") from exc
    except Exception as exc:  # pragma: no cover - corrupt hash defence
        raise CodeMismatchError("code did not match") from exc

    return row


async def consume_code(session: AsyncSession, row: EmailCode) -> None:
    """Mark ``row`` as consumed (sets ``consumed_at = now()``)."""
    row.consumed_at = datetime.now(UTC)
    await session.flush()
