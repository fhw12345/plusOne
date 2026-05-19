"""Auth endpoints — magic-link request + exchange.

Two routes:

  POST /api/auth/request-link {email}
       -> create or fetch User, issue MagicLinkToken, send email
       -> 204 No Content (do NOT reveal whether the email is registered)

  POST /api/auth/exchange {token}
       -> validate + consume token, return JWT
       -> 200 {access_token, token_type, expires_in_minutes}
       -> 400 if token is invalid / expired / consumed
"""

from __future__ import annotations

from typing import Annotated

from email_validator import EmailNotValidError, validate_email
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from plus_one.config import settings
from plus_one.core.auth.deps import CurrentUser  # noqa: TC001 - FastAPI dep used at runtime
from plus_one.core.auth.email import get_dev_last_token, get_email_sender
from plus_one.core.auth.jwt import create_access_token
from plus_one.core.auth.tokens import (
    MagicLinkAlreadyConsumedError,
    MagicLinkExpiredError,
    MagicLinkInvalidError,
    consume_magic_link,
    issue_magic_link,
)
from plus_one.core.db.models import User
from plus_one.core.db.session import get_request_session

router = APIRouter(prefix="/api/auth", tags=["auth"])


# === Schemas ============================================================


def _normalize_email_for_signup(value: str) -> str:
    """Validate an email and return its normalized form.

    Wraps ``email_validator`` with ``test_environment=True`` so reserved TLDs
    like ``.test`` (RFC 2606) are accepted — the e2e harness uses
    ``@plusone.test`` addresses and the default :class:`EmailStr` rejects
    them as a reserved name. ``check_deliverability=False`` keeps the
    validator pure-syntax (no DNS lookup, no MX probe) which is the right
    default for an account-creation endpoint anyway.
    """
    try:
        result = validate_email(
            value,
            check_deliverability=False,
            test_environment=True,
        )
    except EmailNotValidError as exc:
        raise ValueError(str(exc)) from exc
    return result.normalized


class RequestLinkBody(BaseModel):
    email: str
    # Where the user came from — frontend tells us so the email link
    # can deep-link them back. Optional for now (not used in v1).
    return_to: str | None = Field(default=None, max_length=500)

    @field_validator("email", mode="before")
    @classmethod
    def _validate_email(cls, v: object) -> str:
        if not isinstance(v, str):
            raise ValueError("email must be a string")
        return _normalize_email_for_signup(v)


class ExchangeBody(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int


class MeResponse(BaseModel):
    """Current-user identity payload returned by ``GET /api/auth/me``."""

    id: str
    email: str


class DevLastLinkResponse(BaseModel):
    """Dev-only payload for ``GET /api/auth/dev/last-link``.

    Locked to ``{"token": str}`` by the e2e contract — do not widen.
    """

    token: str


# === Endpoints ==========================================================


@router.post(
    "/request-link",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Request a magic-link email",
    description=(
        "Always returns 204 regardless of whether the email exists, "
        "so the endpoint cannot be used to enumerate registered users."
    ),
)
async def request_link(
    body: RequestLinkBody,
    session: Annotated[AsyncSession, Depends(get_request_session)],
) -> None:
    # Find or create the user. Magic-link is the only auth path so the
    # request-link endpoint *is* the registration endpoint.
    result = await session.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(email=body.email, is_active=True)
        session.add(user)
        await session.flush()

    token = await issue_magic_link(session, user)

    # Build the link the email will contain. The frontend route
    # /auth/exchange?token=... will POST to /api/auth/exchange under
    # the hood. For v1 we just embed the raw token.
    link = f"{settings.frontend_base_url.rstrip('/')}/auth/exchange?token={token.token}"
    sender = get_email_sender()
    try:
        await sender.send_magic_link(to=body.email, link=link)
    except NotImplementedError as exc:
        # Default sender raises until SMTP is wired. Translate to a
        # stable HTTP error so the caller sees 503 (service degraded)
        # rather than an opaque 500. Set ALLOW_CONSOLE_EMAIL_SENDER=true
        # in dev or wire SMTP to fix.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="email_sender_not_configured",
        ) from exc


@router.post(
    "/exchange",
    response_model=TokenResponse,
    summary="Exchange a magic-link token for a JWT",
    description=(
        "Returns the JWT in both an httpOnly cookie (for browser SPAs) "
        "AND the response body (for non-browser clients like CLI / mobile). "
        "Browser callers should ignore the body and rely on the cookie."
    ),
)
async def exchange(
    body: ExchangeBody,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_request_session)],
) -> TokenResponse:
    try:
        user = await consume_magic_link(session, body.token)
    except MagicLinkInvalidError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token"
        ) from exc
    except MagicLinkExpiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Token expired"
        ) from exc
    except MagicLinkAlreadyConsumedError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Token already used"
        ) from exc

    access_token = create_access_token(user.id)

    # httpOnly + Secure + SameSite=Lax: not readable from JS (XSS-safe),
    # only sent over HTTPS in prod (auth_cookie_secure=True default), and
    # immune to CSRF for cross-site top-level POSTs. Frontend SPAs use
    # this; non-browser clients (CLI / mobile) use the body field.
    #
    # Cookie scope notes (intentional choices):
    #   - path="/" explicit so a future API mount under /api doesn't
    #     silently scope the cookie wrong
    #   - no `domain` — leaving it unset gives a host-only cookie, the
    #     safest scope. Don't add `domain=...` without a real reason
    #     (subdomain SSO is the only legitimate one).
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=access_token,
        max_age=settings.jwt_ttl_minutes * 60,
        path="/",
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=settings.auth_cookie_samesite,
    )
    return TokenResponse(
        access_token=access_token,
        expires_in_minutes=settings.jwt_ttl_minutes,
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Clear the auth cookie",
    description=(
        "Browser SPAs call this to sign out cleanly — the JWT is "
        "deleted from the client cookie store. Non-browser clients "
        "(CLI / mobile) just discard their stored token."
    ),
)
async def logout(response: Response) -> None:
    response.delete_cookie(
        key=settings.auth_cookie_name,
        path="/",
    )


@router.get(
    "/me",
    response_model=MeResponse,
    summary="Get current authenticated user",
    description=(
        "Returns the identity associated with the Bearer token in the "
        "``Authorization`` header. Returns 401 if no/invalid token."
    ),
)
async def me(user: CurrentUser) -> MeResponse:
    return MeResponse(id=str(user.id), email=user.email)


@router.get(
    "/dev/last-link",
    response_model=DevLastLinkResponse,
    summary="[dev] Read the most-recent magic-link token for an email",
    description=(
        "Dev/test only. Returns 404 unless ``APP_ENV=development`` AND the "
        "console email sender has captured a link for the given address. "
        "The e2e harness uses this to drive the magic-link happy path "
        "without parsing logs."
    ),
)
async def dev_last_link(email: str) -> DevLastLinkResponse:
    # Env guard at *request time* — same binary serves dev and prod.
    if settings.app_env != "development":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found",
        )
    token = get_dev_last_token(email)
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No magic-link issued for this email",
        )
    return DevLastLinkResponse(token=token)
