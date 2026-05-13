"""Authentication: magic-link issuance + JWT session.

Flow:
  1. POST /auth/request-link {email} ->
     - Create User if not exists
     - Issue MagicLinkToken (single-use, short-lived)
     - Email the link (or log it in dev)

  2. User clicks link -> POST /auth/exchange {token} ->
     - Verify token unconsumed + unexpired
     - Mark consumed, mint JWT, return to client

  3. Subsequent requests carry JWT in Authorization header
     -> current_user dependency validates + loads User
"""

from plus_one.core.auth.deps import CurrentUser, current_user
from plus_one.core.auth.jwt import (
    JWTPayload,
    create_access_token,
    decode_access_token,
)
from plus_one.core.auth.tokens import (
    MagicLinkAlreadyConsumedError,
    MagicLinkExpiredError,
    MagicLinkInvalidError,
    consume_magic_link,
    issue_magic_link,
)

__all__ = [
    "CurrentUser",
    "JWTPayload",
    "MagicLinkAlreadyConsumedError",
    "MagicLinkExpiredError",
    "MagicLinkInvalidError",
    "consume_magic_link",
    "create_access_token",
    "current_user",
    "decode_access_token",
    "issue_magic_link",
]
