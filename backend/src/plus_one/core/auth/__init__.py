"""Authentication: password + email-code login + admin guard (batch-2m).

Replaced magic-link in batch-2m. Flow:

  1. POST /auth/register {username, email, password} ->
     - Insert User (email_verified_at NULL)
     - Issue verify_email code, SMTP send

  2. POST /auth/verify {email, code} ->
     - Verify + consume code, set email_verified_at, return JWT

  3. POST /auth/login {identifier, password} -> JWT
     POST /auth/request-code + /auth/login-with-code — code login

  4. Subsequent requests carry JWT in Authorization header
     -> current_user dependency validates + loads User
"""

from plus_one.core.auth.admin import RequireAdmin
from plus_one.core.auth.deps import CurrentUser, current_user
from plus_one.core.auth.jwt import (
    JWTPayload,
    create_access_token,
    decode_access_token,
)
from plus_one.core.auth.passwords import hash_password, verify_password

__all__ = [
    "CurrentUser",
    "JWTPayload",
    "RequireAdmin",
    "create_access_token",
    "current_user",
    "decode_access_token",
    "hash_password",
    "verify_password",
]
