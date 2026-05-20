"""FastAPI dependency: ``current_user`` (+ SSE fallback variant).

Reads ``Authorization: Bearer <jwt>`` header, verifies, loads User from
DB. Raises 401 if any step fails. Use as::

    @router.get("/profile")
    async def get_profile(user: CurrentUser): ...

SSE endpoints use ``current_user_or_sse`` instead: browsers' EventSource
cannot set headers, so it also accepts ``?access_token=`` as a fallback.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from plus_one.core.auth.jwt import InvalidTokenError, decode_access_token
from plus_one.core.db.models import User
from plus_one.core.db.session import get_request_session

_bearer = HTTPBearer(auto_error=False)


async def _load_user_from_token(token: str, session: AsyncSession) -> User:
    try:
        payload = decode_access_token(token)
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user = await session.get(User, payload.user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    session: Annotated[AsyncSession, Depends(get_request_session)],
) -> User:
    """Validate Authorization header + return the matching User."""
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return await _load_user_from_token(creds.credentials, session)


async def current_user_or_sse(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    session: Annotated[AsyncSession, Depends(get_request_session)],
    access_token: str | None = None,
) -> User:
    """Auth dep for SSE endpoints — header preferred, query param fallback.

    Browsers using ``EventSource`` cannot set request headers, so we accept
    the JWT via ``?access_token=`` as a narrow fallback for SSE endpoints
    only. Use the standard ``current_user`` everywhere else.

    SECURITY NOTE: tokens in URLs can leak via access logs and DevTools.
    Mitigated in-process by the uvicorn access-log scrubbing filter
    installed in ``plus_one.main``. JWT TTL of 60min limits blast radius.
    Production deployments behind a proxy must additionally scrub the
    proxy's access log (operations runbook task).
    """
    if creds is not None and creds.scheme.lower() == "bearer":
        token = creds.credentials
    elif access_token:
        token = access_token
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization (header or ?access_token)",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return await _load_user_from_token(token, session)


# Type aliases so endpoints can write `user: CurrentUser` / `user: CurrentUserOrSse`
# directly without the verbose Annotated[..., Depends(...)] form.
CurrentUser = Annotated[User, Depends(current_user)]
CurrentUserOrSse = Annotated[User, Depends(current_user_or_sse)]
