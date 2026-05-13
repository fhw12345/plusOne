"""Magic-link token issuance + consumption.

Tokens are random URL-safe strings persisted in ``magic_link_tokens``
with ``issued_at`` / ``expires_at`` / ``consumed_at``. The schema's
partial unique on ``(user_id) WHERE consumed_at IS NULL`` (PR #3,
reviewer F4) prevents stockpiling — issuing a new token while one is
still live would violate the constraint, so we proactively invalidate
any prior live token in the same transaction before inserting.

Cleanup of expired tokens is left to a periodic task (deferred — out
of scope for this batch). The expires_at index added in PR #3 makes
``DELETE WHERE expires_at < now()`` cheap.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select, update

from plus_one.config import settings
from plus_one.core.db.models import MagicLinkToken, User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


# Magic-link tokens are short-lived: long enough for a user to switch
# from email client to browser, short enough to limit interception.
_TOKEN_BYTES = 32
_TOKEN_TTL_MINUTES = 15


class MagicLinkInvalidError(ValueError):
    """Token doesn't exist."""


class MagicLinkExpiredError(ValueError):
    """Token exists but expires_at has passed."""


class MagicLinkAlreadyConsumedError(ValueError):
    """Token exists but consumed_at is set."""


def _generate_token() -> str:
    return secrets.token_urlsafe(_TOKEN_BYTES)


async def issue_magic_link(
    session: AsyncSession,
    user: User,
    *,
    ttl_minutes: int | None = None,
) -> MagicLinkToken:
    """Issue a fresh magic-link token for ``user``.

    Invalidates any existing unconsumed token for the user first
    (otherwise the partial-unique index would reject the insert and
    the user would be locked out until the live token expired).
    """
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=ttl_minutes or _TOKEN_TTL_MINUTES)

    # Mark any existing unconsumed token as consumed so the partial
    # unique on (user_id) WHERE consumed_at IS NULL stays satisfied
    # when we insert the new row in this same transaction.
    await session.execute(
        update(MagicLinkToken)
        .where(MagicLinkToken.user_id == user.id, MagicLinkToken.consumed_at.is_(None))
        .values(consumed_at=now)
    )

    token = MagicLinkToken(
        token=_generate_token(),
        user_id=user.id,
        issued_at=now,
        expires_at=expires_at,
    )
    session.add(token)
    await session.flush()  # surface the row so caller can read .token before commit
    return token


async def consume_magic_link(
    session: AsyncSession,
    raw_token: str,
) -> User:
    """Validate + consume a magic-link token, returning the linked user.

    Raises:
        MagicLinkInvalidError: token doesn't exist (or wrong shape).
        MagicLinkExpiredError: token exists but past expires_at.
        MagicLinkAlreadyConsumedError: token exists but consumed_at is set.

    On success: marks consumed_at, sets user.last_login_at, returns user.
    """
    # Avoid timing-side-channel: always do the lookup, even if the input
    # looks malformed.
    result = await session.execute(select(MagicLinkToken).where(MagicLinkToken.token == raw_token))
    token = result.scalar_one_or_none()
    if token is None:
        raise MagicLinkInvalidError("token not found")

    now = datetime.now(UTC)
    if token.consumed_at is not None:
        raise MagicLinkAlreadyConsumedError("token already used")
    if token.expires_at < now:
        raise MagicLinkExpiredError("token expired")

    token.consumed_at = now

    # Load + stamp user.last_login_at
    user = await session.get(User, token.user_id)
    if user is None:
        # FK should make this impossible, but defend anyway.
        raise MagicLinkInvalidError("token references missing user")
    user.last_login_at = now
    return user


# Re-export so callers don't need both the issue helper AND a settings dive.
DEFAULT_TOKEN_TTL_MINUTES = _TOKEN_TTL_MINUTES
DEFAULT_JWT_TTL_MINUTES = settings.jwt_ttl_minutes
