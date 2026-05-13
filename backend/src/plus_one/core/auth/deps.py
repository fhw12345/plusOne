"""FastAPI dependency: ``current_user``.

Reads ``Authorization: Bearer <jwt>`` header, verifies, loads User from
DB. Raises 401 if any step fails. Use as::

    @router.get("/profile")
    async def get_profile(user: CurrentUser): ...
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

    try:
        payload = decode_access_token(creds.credentials)
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


# Type alias so endpoints can write `user: CurrentUser` directly without
# the verbose Annotated[..., Depends(...)] form.
CurrentUser = Annotated[User, Depends(current_user)]
