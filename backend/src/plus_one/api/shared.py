"""Public, unauthed share endpoint — GET /api/shared/{token}.

Returns a stripped-down read-only view of the trip + its latest report.
Strips ``user_id``, ``trace``, and token-cost fields so the public payload
never leaks owner or per-call observability data.

Lazy-404 semantics: expired / revoked / never-existed tokens all return
the same 404 with ``detail="share_not_found_or_expired"`` — no info leak
between "wrong token" and "right token, expired".
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID  # noqa: TC003 — runtime use as FastAPI response field type

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,  # noqa: TC002 — FastAPI Depends needs runtime symbol
)

from plus_one.core.db.models import Report, SharedTrip, Trip
from plus_one.core.db.session import get_request_session

router = APIRouter(prefix="/api/shared", tags=["shared"])


class SharedTripResponse(BaseModel):
    trip_id: UUID
    destination: str
    status: str
    content: dict[str, object] | None = None
    shared: bool = True
    expires_at: datetime


@router.get(
    "/{token}",
    response_model=SharedTripResponse,
    summary="Public read-only view of a shared trip",
)
async def get_shared_trip(
    token: str,
    session: Annotated[AsyncSession, Depends(get_request_session)],
) -> SharedTripResponse:
    share = await session.get(SharedTrip, token)
    if share is None or share.expires_at <= datetime.now(UTC):
        # Lazy 404: collapse "missing", "revoked", and "expired" into a
        # single response so token-state enumeration is impossible.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="share_not_found_or_expired",
        )

    trip = await session.get(Trip, share.trip_id)
    if trip is None:
        # CASCADE should have removed the share row when the trip was
        # deleted, but if the row lingers for any reason treat it the
        # same as expired.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="share_not_found_or_expired",
        )

    latest_report_q = (
        select(Report).where(Report.trip_id == trip.id).order_by(Report.created_at.desc()).limit(1)
    )
    latest = (await session.execute(latest_report_q)).scalar_one_or_none()

    return SharedTripResponse(
        trip_id=trip.id,
        destination=trip.destination,
        status=trip.status,
        content=latest.content if latest else None,
        shared=True,
        expires_at=share.expires_at,
    )
