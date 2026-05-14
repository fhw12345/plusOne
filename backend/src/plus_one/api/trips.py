"""Trip endpoints — POST /api/trips, GET /api/trips/{id}/stream (SSE), GET /api/trips/{id}.

POST creates the trip + spawns a BackgroundTask running the agent cycle.
The client is expected to immediately open the stream endpoint to receive
live progress events; the report row is persisted on cycle completion
and is then fetchable via the GET endpoint.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from plus_one.core.auth.deps import current_user
from plus_one.core.db.models import Report, Trip, User
from plus_one.core.db.session import get_request_session
from plus_one.services.trip_runner import run_trip, subscribe

router = APIRouter(prefix="/api/trips", tags=["trips"])


class CreateTripBody(BaseModel):
    destination: str = Field(min_length=1, max_length=200)
    free_text: str | None = Field(default=None, max_length=2000)


class CreateTripResponse(BaseModel):
    trip_id: UUID
    status: str


class TripDetail(BaseModel):
    trip_id: UUID
    destination: str
    status: str
    latest_report_id: UUID | None = None
    content: dict[str, object] | None = None


@router.post(
    "",
    response_model=CreateTripResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Create a new trip query and start the agent cycle",
    description=(
        "Returns immediately with the trip_id. The cycle runs in a "
        "BackgroundTask; subscribe via GET /api/trips/{id}/stream for "
        "live progress."
    ),
)
async def create_trip(
    body: CreateTripBody,
    background: BackgroundTasks,
    user: Annotated[User, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_request_session)],
) -> CreateTripResponse:
    trip = Trip(
        user_id=user.id,
        destination=body.destination,
        free_text=body.free_text,
        status="pending",
    )
    session.add(trip)
    await session.flush()  # surface trip.id before commit

    # Build the query the agents see. For v1 it's just destination + free
    # text concatenated; v2 will incorporate Profile + companions.
    query_parts = [body.destination]
    if body.free_text:
        query_parts.append(body.free_text)
    query = " | ".join(query_parts)

    background.add_task(run_trip, trip.id, query)
    return CreateTripResponse(trip_id=trip.id, status=trip.status)


@router.get(
    "/{trip_id}/stream",
    summary="Server-Sent Events stream of cycle progress for one trip",
)
async def stream_trip(
    trip_id: UUID,
    user: Annotated[User, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_request_session)],
) -> StreamingResponse:
    # Authorize: make sure the trip belongs to the current user. We don't
    # want one user subscribing to another user's stream.
    trip = await session.get(Trip, trip_id)
    if trip is None or trip.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="trip_not_found")

    async def event_generator() -> AsyncIterator[str]:
        async for event in subscribe(trip_id):
            payload = json.dumps(event, default=str)
            yield f"event: {event.get('name', 'message')}\ndata: {payload}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get(
    "/{trip_id}",
    response_model=TripDetail,
    summary="Fetch the latest report for a trip",
)
async def get_trip(
    trip_id: UUID,
    user: Annotated[User, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_request_session)],
) -> TripDetail:
    trip = await session.get(Trip, trip_id)
    if trip is None or trip.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="trip_not_found")

    # Most recent report (Trip.reports is order_by="Report.created_at" ASC).
    latest_report_q = (
        select(Report).where(Report.trip_id == trip_id).order_by(Report.created_at.desc()).limit(1)
    )
    latest = (await session.execute(latest_report_q)).scalar_one_or_none()

    return TripDetail(
        trip_id=trip.id,
        destination=trip.destination,
        status=trip.status,
        latest_report_id=latest.id if latest else None,
        content=latest.content if latest else None,
    )
