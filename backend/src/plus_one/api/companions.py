"""Companion endpoints — full CRUD under /api/companions.

Per-user isolation: every read/write filters on ``user_id == current_user.id``
so user B never sees user A's companions; cross-user GET/PUT/DELETE all
return 404 (we never leak existence — matches /api/trips/{id} masking).

Case-insensitive name uniqueness is enforced in app code via a
``lower(name)`` pre-check (PRD §5). The DB-level UNIQUE constraint is
case-sensitive, so a race window may slip through; the second writer is
caught by the IntegrityError fallback (R5 in the PRD).
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID  # noqa: TC003 — used at runtime as FastAPI path-param type

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncSession,  # noqa: TC002 — FastAPI Depends needs the runtime symbol
)

from plus_one.api.schemas import (
    CompanionCreateBody,
    CompanionResponse,
    CompanionsListResponse,
    CompanionUpdateBody,
)
from plus_one.core.auth.deps import current_user
from plus_one.core.db.models import Companion, User
from plus_one.core.db.session import get_request_session

router = APIRouter(prefix="/api/companions", tags=["companions"])

# Hard cap (PRD §5): no user is expected to have more than 20 companions.
# Frontend hides the create button at the cap; server enforces independently.
_COMPANION_CAP = 20


def _to_response(companion: Companion) -> CompanionResponse:
    """Render a Companion ORM row as a CompanionResponse."""
    return CompanionResponse(
        id=companion.id,
        name=companion.name,
        explicit_preferences=companion.explicit_preferences,
        constraints=companion.constraints,
        created_at=companion.created_at,
        updated_at=companion.updated_at,
    )


async def _get_owned_companion(
    session: AsyncSession, user_id: UUID, companion_id: UUID
) -> Companion:
    """Fetch a companion owned by ``user_id`` or raise 404.

    Returns 404 for "not found" AND "not yours" — same response, no
    existence leak (matches ``GET /api/trips/{id}`` masking).
    """
    companion = await session.get(Companion, companion_id)
    if companion is None or companion.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="companion_not_found"
        )
    return companion


async def _name_taken(
    session: AsyncSession, user_id: UUID, name: str, exclude_id: UUID | None = None
) -> bool:
    """Case-insensitive name collision check within a user's companions."""
    stmt = select(Companion.id).where(
        Companion.user_id == user_id,
        func.lower(Companion.name) == name.lower(),
    )
    if exclude_id is not None:
        stmt = stmt.where(Companion.id != exclude_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None


@router.get(
    "",
    response_model=CompanionsListResponse,
    summary="List the current user's companions (ordered by created_at ASC)",
)
async def list_companions(
    user: Annotated[User, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_request_session)],
) -> CompanionsListResponse:
    stmt = (
        select(Companion)
        .where(Companion.user_id == user.id)
        .order_by(Companion.created_at.asc())
    )
    result = await session.execute(stmt)
    companions = result.scalars().all()
    return CompanionsListResponse(companions=[_to_response(c) for c in companions])


@router.post(
    "",
    response_model=CompanionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a companion for the current user",
)
async def create_companion(
    body: CompanionCreateBody,
    user: Annotated[User, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_request_session)],
) -> CompanionResponse:
    # Cap check first — cheapest, no name-comparison work needed.
    count_stmt = select(func.count(Companion.id)).where(Companion.user_id == user.id)
    count = (await session.execute(count_stmt)).scalar_one()
    if count >= _COMPANION_CAP:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="companion_limit_reached"
        )

    if await _name_taken(session, user.id, body.name):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="companion_name_taken"
        )

    companion = Companion(
        user_id=user.id,
        name=body.name,
        explicit_preferences=body.explicit_preferences.model_dump(mode="json"),
        constraints=body.constraints.model_dump(mode="json"),
    )
    session.add(companion)
    try:
        await session.flush()
    except IntegrityError as exc:
        # Lost the race against another POST with the exact-case-matching
        # name — the DB UNIQUE(user_id, name) caught what our pre-check
        # missed. Surface as the same 409 the pre-check returns.
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="companion_name_taken"
        ) from exc
    return _to_response(companion)


@router.put(
    "/{companion_id}",
    response_model=CompanionResponse,
    summary="Update a companion (whole-document)",
)
async def update_companion(
    companion_id: UUID,
    body: CompanionUpdateBody,
    user: Annotated[User, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_request_session)],
) -> CompanionResponse:
    companion = await _get_owned_companion(session, user.id, companion_id)

    if await _name_taken(session, user.id, body.name, exclude_id=companion.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="companion_name_taken"
        )

    companion.name = body.name
    companion.explicit_preferences = body.explicit_preferences.model_dump(mode="json")
    companion.constraints = body.constraints.model_dump(mode="json")
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="companion_name_taken"
        ) from exc
    return _to_response(companion)


@router.delete(
    "/{companion_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a companion",
)
async def delete_companion(
    companion_id: UUID,
    user: Annotated[User, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_request_session)],
) -> Response:
    companion = await _get_owned_companion(session, user.id, companion_id)
    await session.delete(companion)
    await session.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
