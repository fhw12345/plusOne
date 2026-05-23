"""Auth endpoints — username + password + 6-digit code login (batch-2m).

Replaces the magic-link surface. Routes:

  POST /api/auth/register         — create account, send verify code
  POST /api/auth/verify           — confirm verify code, mint JWT
  POST /api/auth/login            — username/email + password -> JWT
  POST /api/auth/request-code     — email-code login: send a code (1/60s)
  POST /api/auth/login-with-code  — consume a code -> JWT
  POST /api/auth/logout           — clear session cookie
  GET  /api/auth/me               — current user identity (+ is_admin)

``request-code`` has one branch worth noting: if the user exists but
``email_verified_at IS NULL`` the route sends a ``verify_email`` code
(re-issue path for the /verify page's resend link). Verified users get a
``login`` code. Unknown email -> no-op, still 204 (no enumeration).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from plus_one.api.schemas.auth import (
    LoginBody,
    LoginWithCodeBody,
    RegisterBody,
    RegisterResponse,
    RequestCodeBody,
    TokenResponse,
    UserMeResponse,
    UserPayload,
    VerifyBody,
)
from plus_one.config import settings
from plus_one.core.auth.codes import (
    CodeError,
    CodeExpiredError,
    consume_code,
    generate_code,
    save_code,
    verify_code,
)
from plus_one.core.auth.deps import CurrentUser  # noqa: TC001 - FastAPI dep used at runtime
from plus_one.core.auth.jwt import create_access_token
from plus_one.core.auth.lockout import is_locked, record_failed_attempt, reset_attempts
from plus_one.core.auth.passwords import hash_password, verify_password
from plus_one.core.auth.rate_limit import MinIntervalLimiter
from plus_one.core.auth.smtp import EmailSendError, send_code_email
from plus_one.core.db.models import User
from plus_one.core.db.session import get_request_session

router = APIRouter(prefix="/api/auth", tags=["auth"])

logger = logging.getLogger(__name__)


# Module-singleton: 1 send per 60s per email.
_REQUEST_CODE_LIMITER = MinIntervalLimiter(min_interval_seconds=60.0)


# Dev-only cache of (email -> latest plaintext code), populated only when
# settings.allow_console_email_sender is True. DB stores Argon2id hashes,
# so e2e cannot recover the code without this side channel.
_DEV_LAST_CODE: dict[str, str] = {}


def get_request_code_limiter() -> MinIntervalLimiter:
    """Indirection so tests can swap the limiter via dependency override
    (or import + .reset() this one directly)."""
    return _REQUEST_CODE_LIMITER


async def _send_code_or_503(email: str, code: str) -> None:
    """Send the code email; translate SMTP errors to HTTP 503."""
    if settings.allow_console_email_sender:
        _DEV_LAST_CODE[email] = code
    try:
        await send_code_email(to=email, code=code)
    except EmailSendError as exc:
        logger.warning("send_code_email_failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="email_sender_unavailable",
        ) from exc


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        max_age=settings.jwt_ttl_minutes * 60,
        path="/",
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=settings.auth_cookie_samesite,
    )


def _to_token_response(user: User, response: Response) -> TokenResponse:
    token = create_access_token(user.id)
    _set_session_cookie(response, token)
    return TokenResponse(
        access_token=token,
        expires_in_minutes=settings.jwt_ttl_minutes,
        user=UserPayload(
            id=user.id,
            email=user.email,
            username=user.username,
            is_admin=user.is_admin,
        ),
    )


# === register =============================================================


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account + send the verification code",
)
async def register(
    body: RegisterBody,
    session: Annotated[AsyncSession, Depends(get_request_session)],
) -> RegisterResponse:
    # Uniqueness — split into two queries so we can report which collided.
    existing_email = await session.execute(select(User).where(User.email == body.email))
    if existing_email.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="email_taken")
    existing_username = await session.execute(select(User).where(User.username == body.username))
    if existing_username.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="username_taken")

    user = User(
        email=body.email,
        username=body.username,
        password_hash=hash_password(body.password),
        is_admin=False,
        is_active=True,
        email_verified_at=None,
    )
    session.add(user)
    await session.flush()

    code = generate_code()
    await save_code(session, email=body.email, purpose="verify_email", code=code)

    await _send_code_or_503(body.email, code)

    return RegisterResponse(user_id=user.id, email=body.email)


# === verify ===============================================================


@router.post(
    "/verify",
    response_model=TokenResponse,
    summary="Confirm a verify_email code and sign in",
)
async def verify(
    body: VerifyBody,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_request_session)],
) -> TokenResponse:
    try:
        code_row = await verify_code(
            session, email=body.email, purpose="verify_email", code=body.code
        )
    except CodeExpiredError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="code_expired") from exc
    except CodeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="code_invalid") from exc

    await consume_code(session, code_row)

    user_result = await session.execute(select(User).where(User.email == body.email))
    user = user_result.scalar_one_or_none()
    if user is None:
        # Code matched but no user — corruption; treat as invalid.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="code_invalid")
    user.email_verified_at = datetime.now(UTC)
    user.last_login_at = datetime.now(UTC)
    reset_attempts(user)

    return _to_token_response(user, response)


# === login (password) =====================================================


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Username/email + password login",
)
async def login(
    body: LoginBody,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_request_session)],
) -> TokenResponse:
    identifier = body.identifier.strip().lower()
    result = await session.execute(
        select(User).where(or_(User.email == identifier, User.username == identifier))
    )
    user = result.scalar_one_or_none()

    if user is None:
        # No counter increment for unknown identifiers — otherwise an
        # attacker could lock anyone out by guessing their name.
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_credentials")

    if is_locked(user):
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail="locked")

    if not verify_password(user.password_hash, body.password):
        record_failed_attempt(user)
        await session.flush()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_credentials")

    if user.email_verified_at is None:
        # Password is right but the email's never been confirmed — the
        # frontend routes to /verify when it sees this detail string.
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="email_not_verified")

    reset_attempts(user)
    user.last_login_at = datetime.now(UTC)
    return _to_token_response(user, response)


# === request-code =========================================================


@router.post(
    "/request-code",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Send a 6-digit email code (verify if unverified, login otherwise)",
)
async def request_code(
    body: RequestCodeBody,
    session: Annotated[AsyncSession, Depends(get_request_session)],
    limiter: Annotated[MinIntervalLimiter, Depends(get_request_code_limiter)],
) -> None:
    """Always 204. Purpose-branching per PRD §6:

      * existing + verified -> ``login`` code
      * existing + unverified -> ``verify_email`` code (re-issue path)
      * missing -> no-op (no enumeration)

    Rate-limit: 1 send per 60s per email — excess attempts still 204.
    """
    if not await limiter.allow(body.email):
        logger.warning("request_code_rate_limited email=%s", body.email)
        return

    result = await session.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if user is None:
        return

    purpose: Literal["verify_email", "login"] = (
        "login" if user.email_verified_at is not None else "verify_email"
    )
    code = generate_code()
    await save_code(session, email=body.email, purpose=purpose, code=code)
    await _send_code_or_503(body.email, code)


# === login-with-code ======================================================


@router.post(
    "/login-with-code",
    response_model=TokenResponse,
    summary="Sign in by consuming a ``login`` code",
)
async def login_with_code(
    body: LoginWithCodeBody,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_request_session)],
) -> TokenResponse:
    user_result = await session.execute(select(User).where(User.email == body.email))
    user = user_result.scalar_one_or_none()
    if user is None or user.email_verified_at is None:
        # Don't tell the caller which one — generic 401.
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_credentials")

    try:
        code_row = await verify_code(session, email=body.email, purpose="login", code=body.code)
    except CodeExpiredError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="code_expired") from exc
    except CodeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="code_invalid") from exc

    await consume_code(session, code_row)
    reset_attempts(user)
    user.last_login_at = datetime.now(UTC)
    return _to_token_response(user, response)


# === logout ===============================================================


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Clear the auth cookie",
)
async def logout(response: Response) -> None:
    response.delete_cookie(key=settings.auth_cookie_name, path="/")


# === me ===================================================================


@router.get(
    "/me",
    response_model=UserMeResponse,
    summary="Get current authenticated user (incl. is_admin)",
)
async def me(user: CurrentUser) -> UserMeResponse:
    return UserMeResponse(
        id=user.id,
        email=user.email,
        username=user.username,
        is_admin=user.is_admin,
    )


# === dev-only =============================================================
#
# Returns the most recent plaintext code issued for an email, when console
# email sender is on. DB stores Argon2id hashes, so e2e cannot recover the
# code from the DB; this side channel is populated in _send_code_or_503
# only when settings.allow_console_email_sender is True. In any other
# environment the endpoint returns 404 so the surface area stays zero.


@router.get(
    "/dev/last-code",
    summary="(dev/CI only) Read the most recent plaintext verify/login code",
)
async def dev_last_code(email: str) -> dict[str, str]:
    if not settings.allow_console_email_sender:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    code = _DEV_LAST_CODE.get(email)
    if not code:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no_code_for_email")
    return {"code": code}
