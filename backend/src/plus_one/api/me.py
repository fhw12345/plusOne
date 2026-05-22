"""Me endpoints — GET /api/me/export and DELETE /api/me (batch-2s).

These cover the PRD §8 privacy promise: a user can take their data back
as a single JSON blob, or hard-delete their account outright. Admins are
blocked from self-deletion to avoid orphaning the deployment.

Cascade strategy: every user-scoped child table (``profiles``,
``companions``, ``trips`` → ``reports`` / ``shared_trips`` /
``trip_companions`` / ``feedback``) has ``ON DELETE CASCADE`` at the
DB level (verified against ``backend/alembic/versions/*.py``).
``email_codes`` is keyed by email string (no FK), so the delete handler
clears it explicitly before dropping the user row.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,  # noqa: TC002 — FastAPI Depends needs the runtime symbol
)
from sqlalchemy.orm import selectinload

from plus_one.core.auth.deps import current_user
from plus_one.core.db.models import (
    Companion,
    EmailCode,
    Feedback,
    Profile,
    Trip,
    User,
)
from plus_one.core.db.session import get_request_session

router = APIRouter(prefix="/api/me", tags=["me"])


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _user_to_dict(user: User) -> dict[str, Any]:
    """Render a User row for export. Excludes secrets per PRD §5."""
    return {
        "id": str(user.id),
        "email": user.email,
        "username": user.username,
        "is_admin": user.is_admin,
        "is_active": user.is_active,
        "email_verified_at": _iso(user.email_verified_at),
        "last_login_at": _iso(user.last_login_at),
        "created_at": _iso(user.created_at),
        "updated_at": _iso(user.updated_at),
    }


def _profile_to_dict(profile: Profile | None) -> dict[str, Any] | None:
    if profile is None:
        return None
    return {
        "demographics": profile.demographics or {},
        "travel_style": profile.travel_style or {},
        "explicit_preferences": profile.explicit_preferences or {},
        "visited_cities": profile.visited_cities or [],
    }


def _companion_to_dict(c: Companion) -> dict[str, Any]:
    return {
        "id": str(c.id),
        "name": c.name,
        "explicit_preferences": c.explicit_preferences or {},
        "constraints": c.constraints or {},
        "created_at": _iso(c.created_at),
        "updated_at": _iso(c.updated_at),
    }


def _trip_to_dict(trip: Trip) -> dict[str, Any]:
    return {
        "id": str(trip.id),
        "destination": trip.destination,
        "date_start": _iso(trip.date_start),
        "date_end": _iso(trip.date_end),
        "budget_amount": trip.budget_amount,
        "budget_currency": trip.budget_currency,
        "free_text": trip.free_text,
        "status": trip.status,
        "companion_ids": [str(c.id) for c in trip.companions],
        "created_at": _iso(trip.created_at),
        "updated_at": _iso(trip.updated_at),
        "reports": [
            {
                "id": str(r.id),
                "content": r.content or {},
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
                "created_at": _iso(r.created_at),
            }
            for r in trip.reports
        ],
    }


def _feedback_to_dict(fb: Feedback) -> dict[str, Any]:
    return {
        "id": str(fb.id),
        "trip_id": str(fb.trip_id),
        "card_id": fb.card_id,
        "for_companion_id": str(fb.for_companion_id) if fb.for_companion_id else None,
        "signal": fb.signal,
        "text": fb.text,
        "created_at": _iso(fb.created_at),
    }


async def _build_export_payload(session: AsyncSession, user: User) -> dict[str, Any]:
    """Assemble the full export payload for ``user``.

    All queries are scoped to ``user.id`` so a horizontal join bug cannot
    leak another user's rows. Feedback is fetched in one IN-query rather
    than N+1 across the trip list.
    """
    profile_res = await session.execute(select(Profile).where(Profile.user_id == user.id))
    profile = profile_res.scalar_one_or_none()

    companions_res = await session.execute(
        select(Companion).where(Companion.user_id == user.id).order_by(Companion.created_at)
    )
    companions = list(companions_res.scalars().all())

    trips_res = await session.execute(
        select(Trip)
        .where(Trip.user_id == user.id)
        .options(selectinload(Trip.reports), selectinload(Trip.companions))
        .order_by(Trip.created_at)
    )
    trips = list(trips_res.scalars().all())

    trip_ids = [t.id for t in trips]
    if trip_ids:
        feedback_res = await session.execute(
            select(Feedback).where(Feedback.trip_id.in_(trip_ids)).order_by(Feedback.created_at)
        )
        feedback_rows = list(feedback_res.scalars().all())
    else:
        feedback_rows = []

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "user": _user_to_dict(user),
        "profile": _profile_to_dict(profile),
        "companions": [_companion_to_dict(c) for c in companions],
        "trips": [_trip_to_dict(t) for t in trips],
        "feedback": [_feedback_to_dict(fb) for fb in feedback_rows],
    }


@router.get(
    "/export",
    summary="Download all of the current user's data as JSON",
)
async def export_me(
    user: Annotated[User, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_request_session)],
) -> Response:
    payload = await _build_export_payload(session, user)
    body = json.dumps(payload, ensure_ascii=False)
    today = datetime.now(UTC).date().isoformat()
    filename = f"plus-one-export-{user.id}-{today}.json"
    return Response(
        content=body,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Hard-delete the current user (idempotent; admin blocked)",
)
async def delete_me(
    user: Annotated[User, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_request_session)],
) -> Response:
    if user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="admin_cannot_self_delete",
        )

    # email_codes carries no FK to users.id (it's keyed by email string).
    # Drop active + consumed rows for this email so a re-registration of
    # the same address doesn't trip the partial-unique active-code index.
    await session.execute(delete(EmailCode).where(EmailCode.email == user.email))

    # Hard-delete the user row. ON DELETE CASCADE (verified in the initial
    # schema + batch-2k migrations) takes care of profiles, companions,
    # trips → reports / shared_trips / trip_companions / feedback.
    await session.execute(delete(User).where(User.id == user.id))
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
