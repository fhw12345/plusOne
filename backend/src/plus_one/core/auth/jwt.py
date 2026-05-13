"""JWT signing + verification.

Wraps python-jose so the rest of the codebase doesn't import it directly.
Tokens carry a minimal payload (sub=user_id, exp, iat); enrich only if a
real reason emerges — bigger payload = bigger header on every request.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt
from pydantic import BaseModel, Field

from plus_one.config import settings


class JWTPayload(BaseModel):
    """Decoded JWT contents."""

    sub: str = Field(description="Subject — the user_id (UUID, str-encoded)")
    exp: int = Field(description="Expiration as unix timestamp")
    iat: int = Field(description="Issued-at as unix timestamp")

    @property
    def user_id(self) -> uuid.UUID:
        return uuid.UUID(self.sub)


class InvalidTokenError(ValueError):
    """JWT failed verification (bad signature, expired, malformed)."""


def create_access_token(
    user_id: uuid.UUID,
    *,
    ttl_minutes: int | None = None,
) -> str:
    """Sign a JWT for ``user_id``."""
    now = datetime.now(UTC)
    expires = now + timedelta(minutes=ttl_minutes or settings.jwt_ttl_minutes)
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
    }
    token: str = jwt.encode(
        payload,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    return token


def decode_access_token(token: str) -> JWTPayload:
    """Verify + decode a JWT.

    Raises:
        InvalidTokenError: signature mismatch, malformed, or expired.
    """
    try:
        raw = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError as exc:
        raise InvalidTokenError(str(exc)) from exc

    return JWTPayload.model_validate(raw)
