"""Admin-only dependency (batch-2m).

Extends :func:`current_user` with a 403 check on ``is_admin``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status

from plus_one.core.auth.deps import CurrentUser, CurrentUserOrSse
from plus_one.core.db.models import User


async def _require_admin(user: CurrentUser) -> User:
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="admin_only"
        )
    return user


async def _require_admin_sse(user: CurrentUserOrSse) -> User:
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="admin_only"
        )
    return user


RequireAdmin = Annotated[User, Depends(_require_admin)]
RequireAdminSse = Annotated[User, Depends(_require_admin_sse)]
