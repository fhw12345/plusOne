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

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from plus_one.config import settings
from plus_one.core.auth.email import get_email_sender
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


class RequestLinkBody(BaseModel):
    email: EmailStr
    # Where the user came from — frontend tells us so the email link
    # can deep-link them back. Optional for now (not used in v1).
    return_to: str | None = Field(default=None, max_length=500)


class ExchangeBody(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int


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
    await sender.send_magic_link(to=body.email, link=link)


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
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=access_token,
        max_age=settings.jwt_ttl_minutes * 60,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=settings.auth_cookie_samesite,  # type: ignore[arg-type]
    )
    return TokenResponse(
        access_token=access_token,
        expires_in_minutes=settings.jwt_ttl_minutes,
    )
