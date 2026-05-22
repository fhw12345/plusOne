"""Trip endpoints — POST /api/trips, GET /api/trips/{id}/stream (SSE), GET /api/trips/{id}.

POST creates the trip + spawns a BackgroundTask running the agent cycle.
The client is expected to immediately open the stream endpoint to receive
live progress events; the report row is persisted on cycle completion
and is then fetchable via the GET endpoint.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import secrets
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ValidationError, model_validator
from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from plus_one.agents.clarifier import run_clarifier
from plus_one.config import settings
from plus_one.core.auth.deps import current_user, current_user_or_sse
from plus_one.core.db.models import Companion, Report, SharedTrip, Trip, User
from plus_one.core.db.session import get_request_session
from plus_one.services.trip_runner import register, run_refine, run_trip, subscribe

logger = structlog.get_logger()

router = APIRouter(prefix="/api/trips", tags=["trips"])


# Batch-2o: closed whitelist of accepted currency codes. Kept narrow on
# purpose — Mode D is a "hint" surface, not a multi-currency planner.
# Extending this set is a deliberate product call, not a config tweak.
_ALLOWED_CURRENCIES = frozenset({"USD", "EUR", "JPY", "CNY", "GBP", "TWD", "KRW", "AUD"})


class CreateTripBody(BaseModel):
    destination: str = Field(min_length=1, max_length=200)
    free_text: str | None = Field(default=None, max_length=2000)
    # Per-trip companion selection. Empty list = all-of-user's-companions
    # (backward-compatible default — see PRD §4 option A). Backend silently
    # drops dangling / cross-user ids in the runner; we never 400 here
    # because the create-trip path is fire-and-forget BackgroundTask and
    # a hard rejection on a stale id is unrecoverable for the client.
    companion_ids: list[UUID] = Field(default_factory=list, max_length=50)
    # Batch-2o: structured trip hints. All four are independently optional
    # (Mode D is hybrid, not a wizard). Cross-field check below enforces
    # end>=start; currency membership; budget non-negative + ceiling.
    date_start: datetime | None = None
    date_end: datetime | None = None
    budget_amount: int | None = Field(default=None, ge=0, le=10_000_000)
    budget_currency: str | None = Field(default=None, min_length=3, max_length=3)

    @model_validator(mode="after")
    def _check_dates_and_currency(self) -> CreateTripBody:
        if (
            self.date_start is not None
            and self.date_end is not None
            and self.date_end < self.date_start
        ):
            raise ValueError("date_end must be on or after date_start")
        if self.budget_currency is not None and self.budget_currency not in _ALLOWED_CURRENCIES:
            raise ValueError(f"budget_currency must be one of {sorted(_ALLOWED_CURRENCIES)}")
        return self


class CreateTripResponse(BaseModel):
    trip_id: UUID
    status: str
    # batch-2t: 0-3 clarifying questions surfaced when ``status ==
    # "clarifying"``. Always present (empty list on the pass-through
    # path) so typed clients can rely on the field without a null check.
    clarifier_questions: list[dict[str, str]] = Field(default_factory=list)


class ClarifierAnswer(BaseModel):
    id: str = Field(min_length=1, max_length=8)
    # Trimmed at the API boundary below; cap at 1000 chars per PRD §4.1.
    text: str = Field(min_length=1, max_length=1000)


class ClarifyTripBody(BaseModel):
    answers: list[ClarifierAnswer] = Field(min_length=1, max_length=3)


class ClarifyTripResponse(BaseModel):
    status: str


class TripParty(BaseModel):
    """Identity of who's on the trip — used by the report UI to label
    per-person ``match_scores`` (batch-2p) and to render shared-report
    party context without leaking PII beyond what the owner already saw.
    """

    user_id: UUID
    companion_ids: list[UUID] = Field(default_factory=list)


class TripDetail(BaseModel):
    trip_id: UUID
    destination: str
    status: str
    latest_report_id: UUID | None = None
    content: dict[str, object] | None = None
    # Batch-2p: ``party.user_id`` + ``party.companion_ids`` let the
    # frontend resolve ``JoinedItem.match_scores`` keys against the
    # current user + companions and render labels like
    # ``match  you: 0.8 · alice: 0.3``. Optional so old / pre-2p code
    # paths and the SSR boundary stay backward-compatible.
    party: TripParty | None = None
    # Batch-2o: echo back the structured hints the user provided at create
    # time. All four are nullable so pre-2o trips (created before these
    # columns were exposed) return ``null`` cleanly.
    date_start: datetime | None = None
    date_end: datetime | None = None
    budget_amount: int | None = None
    budget_currency: str | None = None


class TripListItem(BaseModel):
    trip_id: UUID
    destination: str
    status: str
    created_at: datetime
    latest_report_id: UUID | None = None
    has_report: bool


class TripListResponse(BaseModel):
    trips: list[TripListItem]
    next_cursor: str | None = None


class _Cursor(BaseModel):
    created_at: datetime
    id: UUID


def _encode_cursor(c: _Cursor) -> str:
    raw = c.model_dump_json().encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(s: str) -> _Cursor:
    # Re-pad before decode (urlsafe_b64encode strips '=' in encode).
    padding = "=" * (-len(s) % 4)
    try:
        raw = base64.urlsafe_b64decode(s + padding)
        return _Cursor.model_validate_json(raw)
    except (binascii.Error, ValueError, ValidationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid_cursor",
        ) from exc


@router.post(
    "",
    response_model=CreateTripResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new trip query; may return clarifier questions before the cycle starts",
    description=(
        "Persists the trip row, then synchronously runs the clarifier "
        "(<=5s, fails open). If the clarifier returns 0 questions, the "
        "cycle is scheduled immediately and ``status`` is ``running``. "
        "If 1-3 questions, the trip is parked at ``status='clarifying'`` "
        "and the cycle is deferred until the client POSTs to "
        "``/api/trips/{id}/clarify`` (or ``/clarify/skip``)."
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
        # Batch-2o: persist structured hints onto the existing columns.
        # NOTE: the runner does not yet project these into AgentContext —
        # follow-up batch will wire them through. Stored-only for now.
        date_start=body.date_start,
        date_end=body.date_end,
        budget_amount=body.budget_amount,
        budget_currency=body.budget_currency,
        status="pending",
    )
    session.add(trip)
    await session.flush()  # surface trip.id before commit

    # Persist the trip <-> companion association so the trip-detail / shared
    # endpoints (batch-2p ``party``) can later resolve which companions were
    # on the run without the runner having to hand them back. We scope by
    # ``user_id`` to silently drop cross-user ids — matches the runner's
    # silent-drop policy (PRD batch-2h §10 R1). Skips when no ids requested.
    owned_companions: list[Companion] = []
    if body.companion_ids:
        owned_companions = list(
            (
                await session.execute(
                    select(Companion).where(
                        Companion.user_id == user.id,
                        Companion.id.in_(body.companion_ids),
                    )
                )
            )
            .scalars()
            .all()
        )
        if owned_companions:
            trip.companions = owned_companions

    # batch-2t: run the clarifier synchronously. ``run_clarifier`` is
    # fail-open — timeout / LLM error / invalid output all return ``[]``,
    # so the trip falls through into the existing fast path. We render the
    # resolved companion preferences here (rather than letting the agent
    # do it) so the clarifier sees the exact same loves/hates the runner
    # will eventually pass to the joiner.
    companion_preferences = [
        {
            "name": c.name,
            "loves": list((c.explicit_preferences or {}).get("loves") or []),
            "hates": list((c.explicit_preferences or {}).get("hates") or []),
            "constraints": list((c.constraints or {}).keys()),
        }
        for c in owned_companions
    ]
    clarifier_questions = await run_clarifier(
        destination=body.destination,
        free_text=body.free_text,
        companion_preferences=companion_preferences,
        date_start=body.date_start.isoformat() if body.date_start else None,
        date_end=body.date_end.isoformat() if body.date_end else None,
        budget_amount=body.budget_amount,
        budget_currency=body.budget_currency,
    )

    if clarifier_questions:
        # Park the trip; defer ``register`` + ``run_trip`` until the
        # client posts back to /clarify (or /clarify/skip).
        trip.status = "clarifying"
        trip.clarifier_questions = clarifier_questions
        await session.commit()
        logger.info(
            "trip_clarifying",
            trip_id=str(trip.id),
            n_questions=len(clarifier_questions),
        )
        return CreateTripResponse(
            trip_id=trip.id,
            status="clarifying",
            clarifier_questions=clarifier_questions,
        )

    # 0 questions: fast path — same as pre-2t behaviour.
    trip.status = "running"

    # Commit BEFORE scheduling the background task. FastAPI's `BackgroundTasks`
    # runs after the response is sent, but racing with the request-session's
    # __aexit__ commit; the runner opens its own session_scope and would see
    # the trip row as missing (→ trip_not_found_at_status_update, FK violation
    # on report insert, status frozen at "pending" forever).
    await session.commit()

    # Build the query the agents see. For v1 it's just destination + free
    # text concatenated; v2 will incorporate Profile + companions.
    query_parts = [body.destination]
    if body.free_text:
        query_parts.append(body.free_text)
    query = " | ".join(query_parts)

    # Pre-create the per-trip event queue BEFORE the response so the
    # client can race straight to GET /stream and not lose events.
    # Reviewer B1: register before BackgroundTask schedules run_trip.
    register(trip.id)
    background.add_task(run_trip, trip.id, query, user.id, body.companion_ids)
    return CreateTripResponse(
        trip_id=trip.id,
        status="running",
        clarifier_questions=[],
    )


def _build_query_with_clarifications(
    destination: str,
    free_text: str | None,
    questions: list[dict[str, str]] | None,
    answers: list[dict[str, str]] | None,
) -> str:
    """Render the agent-visible query string.

    Pre-2t shape: ``destination | free_text``. With clarifier answers we
    append a third ``|``-separated block ``Clarifications: q1: …; q2: …``
    so the joiner's ``ctx.query`` carries the new info verbatim (joiner
    user payload prepends ``User query: {ctx.query}`` — see joiner.py).
    """
    parts: list[str] = [destination]
    if free_text:
        parts.append(free_text)
    if questions and answers:
        by_id = {q.get("id"): q.get("text", "") for q in questions}
        clar_parts: list[str] = []
        for ans in answers:
            qid = ans.get("id")
            qtext = by_id.get(qid, "")
            atext = (ans.get("text") or "").strip()
            if not atext:
                continue
            label = qtext or qid or "?"
            clar_parts.append(f"{label}: {atext}")
        if clar_parts:
            parts.append("Clarifications: " + "; ".join(clar_parts))
    return " | ".join(parts)


@router.post(
    "/{trip_id}/clarify",
    response_model=ClarifyTripResponse,
    status_code=status.HTTP_200_OK,
    summary="Submit answers to clarifier questions and kick off the cycle.",
)
async def clarify_trip(
    trip_id: UUID,
    body: ClarifyTripBody,
    background: BackgroundTasks,
    user: Annotated[User, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_request_session)],
) -> ClarifyTripResponse:
    trip = await session.get(Trip, trip_id, with_for_update=True)
    if trip is None or trip.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="trip_not_found")
    if trip.status != "clarifying":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="trip_not_clarifying")

    questions: list[dict[str, str]] = list(trip.clarifier_questions or [])
    expected_ids = {str(q.get("id")) for q in questions}
    submitted_ids = {a.id for a in body.answers}

    if len(body.answers) != len(questions) or submitted_ids != expected_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="clarifier_answers_mismatch",
        )

    answers_payload: list[dict[str, str]] = []
    for ans in body.answers:
        text = ans.text.strip()
        if not text:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="clarifier_answer_empty",
            )
        answers_payload.append({"id": ans.id, "text": text})

    trip.clarifier_answers = answers_payload
    trip.status = "running"

    # Snapshot the values we need post-commit (avoid touching the trip
    # row after the session closes — selectin lazy-loads would re-greenlet).
    destination = trip.destination
    free_text = trip.free_text
    companion_ids = [c.id for c in trip.companions]
    await session.commit()

    query = _build_query_with_clarifications(destination, free_text, questions, answers_payload)
    register(trip_id)
    background.add_task(run_trip, trip_id, query, user.id, companion_ids)
    return ClarifyTripResponse(status="running")


@router.post(
    "/{trip_id}/clarify/skip",
    response_model=ClarifyTripResponse,
    status_code=status.HTTP_200_OK,
    summary="Skip clarifier questions and kick off the cycle with the original query.",
)
async def skip_clarify_trip(
    trip_id: UUID,
    background: BackgroundTasks,
    user: Annotated[User, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_request_session)],
) -> ClarifyTripResponse:
    trip = await session.get(Trip, trip_id, with_for_update=True)
    if trip is None or trip.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="trip_not_found")
    if trip.status != "clarifying":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="trip_not_clarifying")

    # clarifier_answers stays None on skip — the runner reads from
    # clarifier_questions+answers, NULL is the explicit "skipped" sentinel.
    trip.status = "running"
    destination = trip.destination
    free_text = trip.free_text
    companion_ids = [c.id for c in trip.companions]
    await session.commit()

    query = _build_query_with_clarifications(destination, free_text, None, None)
    register(trip_id)
    background.add_task(run_trip, trip_id, query, user.id, companion_ids)
    return ClarifyTripResponse(status="running")


@router.get(
    "/{trip_id}/stream",
    summary="Server-Sent Events stream of cycle progress for one trip",
)
async def stream_trip(
    trip_id: UUID,
    user: Annotated[User, Depends(current_user_or_sse)],
    session: Annotated[AsyncSession, Depends(get_request_session)],
    access_token: str | None = None,
) -> StreamingResponse:
    # Authorize: make sure the trip belongs to the current user. We don't
    # want one user subscribing to another user's stream.
    trip = await session.get(Trip, trip_id)
    if trip is None or trip.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="trip_not_found")

    async def event_generator() -> AsyncIterator[str]:
        # Reviewer M1: client disconnect raises CancelledError /
        # GeneratorExit inside this generator. Catching them here makes
        # the asyncio cancellation chain complete cleanly so the
        # underlying subscribe() doesn't leak a pending queue.get().
        # The runner owns the per-trip queue's lifecycle (drops on
        # cycle end / runner crash); we just exit our consumer half.
        try:
            async for event in subscribe(trip_id):
                payload = json.dumps(event, default=str)
                yield f"event: {event.get('name', 'message')}\ndata: {payload}\n\n"
        except asyncio.CancelledError:
            logger.info("sse_client_disconnected", trip_id=str(trip_id))
            raise

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get(
    "",
    response_model=TripListResponse,
    summary="List the current user's trips, newest first",
)
async def list_trips(
    user: Annotated[User, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_request_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query()] = None,
) -> TripListResponse:
    # Correlated subquery for the latest report id per trip — avoids N+1
    # without forcing a join that would also need a GROUP BY. Postgres
    # plans this as a per-row scan over the (trip_id, created_at) order
    # which is cheap given reports.trip_id is indexed.
    latest_report_subq = (
        select(Report.id)
        .where(Report.trip_id == Trip.id)
        .order_by(Report.created_at.desc())
        .limit(1)
        .correlate(Trip)
        .scalar_subquery()
    )

    stmt = (
        select(
            Trip.id,
            Trip.destination,
            Trip.status,
            Trip.created_at,
            latest_report_subq.label("latest_report_id"),
        )
        .where(Trip.user_id == user.id)
        .order_by(Trip.created_at.desc(), Trip.id.desc())
        .limit(limit + 1)  # +1 to detect "more"
    )

    if cursor is not None:
        decoded = _decode_cursor(cursor)
        # Keyset pagination on (created_at, id) gives a total order stable
        # under concurrent inserts at the head of the list.
        stmt = stmt.where(tuple_(Trip.created_at, Trip.id) < (decoded.created_at, decoded.id))

    rows = (await session.execute(stmt)).all()
    has_more = len(rows) > limit
    page_rows = rows[:limit]

    items = [
        TripListItem(
            trip_id=row.id,
            destination=row.destination,
            status=row.status,
            created_at=row.created_at,
            latest_report_id=row.latest_report_id,
            has_report=row.latest_report_id is not None,
        )
        for row in page_rows
    ]

    next_cursor: str | None = None
    if has_more and page_rows:
        last = page_rows[-1]
        next_cursor = _encode_cursor(_Cursor(created_at=last.created_at, id=last.id))

    return TripListResponse(trips=items, next_cursor=next_cursor)


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

    # Batch-2p: surface the trip's party so the frontend can resolve
    # per-person ``match_scores`` keys against the current user + the
    # companions that ran with this trip. ``trip.companions`` is
    # ``selectin``-loaded so this is a single extra query at worst.
    party = TripParty(
        user_id=trip.user_id,
        companion_ids=[c.id for c in trip.companions],
    )

    return TripDetail(
        trip_id=trip.id,
        destination=trip.destination,
        status=trip.status,
        latest_report_id=latest.id if latest else None,
        content=latest.content if latest else None,
        party=party,
        # Batch-2o: surface structured hints back to the client. Null on
        # legacy trips (created before the form exposed these fields).
        date_start=trip.date_start,
        date_end=trip.date_end,
        budget_amount=trip.budget_amount,
        budget_currency=trip.budget_currency,
    )


# === Share + Delete ======================================================


class CreateShareResponse(BaseModel):
    token: str
    share_url: str
    expires_at: datetime


_SHARE_TTL = timedelta(days=30)


@router.post(
    "/{trip_id}/share",
    response_model=CreateShareResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Mint a public, revokable share link for a trip",
)
async def create_share(
    trip_id: UUID,
    user: Annotated[User, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_request_session)],
) -> CreateShareResponse:
    trip = await session.get(Trip, trip_id)
    if trip is None or trip.user_id != user.id:
        # 404 (not 403) — never confirm existence of trips you don't own.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="trip_not_found")

    token = secrets.token_urlsafe(24)
    expires_at = datetime.now(UTC) + _SHARE_TTL
    share = SharedTrip(
        token=token,
        trip_id=trip.id,
        created_by=user.id,
        expires_at=expires_at,
    )
    session.add(share)
    await session.commit()

    share_url = f"{settings.frontend_base_url.rstrip('/')}/share/{token}"
    return CreateShareResponse(token=token, share_url=share_url, expires_at=expires_at)


@router.delete(
    "/{trip_id}/share/{token}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke a previously-minted share link",
)
async def revoke_share(
    trip_id: UUID,
    token: str,
    user: Annotated[User, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_request_session)],
) -> Response:
    share = await session.get(SharedTrip, token)
    # Defensive: row must exist, be owned by current user, AND match the
    # trip_id from the path (defends against URL-tampering across one's own
    # trips). All three failures collapse to 404 — no info leak.
    if share is None or share.created_by != user.id or share.trip_id != trip_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="share_not_found")
    await session.delete(share)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/{trip_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a trip and its reports + share links",
)
async def delete_trip(
    trip_id: UUID,
    user: Annotated[User, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_request_session)],
) -> Response:
    # ``with_for_update`` locks the row for the duration of the txn so a
    # concurrent worker flipping ``pending → running`` can't race past the
    # status check.
    trip = await session.get(Trip, trip_id, with_for_update=True)
    if trip is None or trip.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="trip_not_found")
    if trip.status == "running":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="trip_running")
    await session.delete(trip)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# === Refine (batch-2u) ===================================================


class RefineTripBody(BaseModel):
    # 500-char cap matches the prompt's `hint` fence + DB column comfort.
    # whitespace-only hints fail the 1-char min after the API strips them.
    hint: str = Field(min_length=1, max_length=500)


class RefineTripResponse(BaseModel):
    report_id: UUID
    status: str  # always "running" on the 202 path


class _TripReportSummary(BaseModel):
    report_id: UUID
    created_at: datetime
    is_original: bool
    hint: str | None
    previous_report_id: UUID | None


class TripReportsResponse(BaseModel):
    reports: list[_TripReportSummary]


@router.post(
    "/{trip_id}/refine",
    response_model=RefineTripResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger a refinement cycle against the latest Report.",
)
async def refine_trip(
    trip_id: UUID,
    body: RefineTripBody,
    background: BackgroundTasks,
    user: Annotated[User, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_request_session)],
) -> RefineTripResponse:
    # Lock the trip row so a concurrent status flip can't sneak past the
    # check below. Same pattern as ``delete_trip``.
    trip = await session.get(Trip, trip_id, with_for_update=True)
    if trip is None or trip.user_id != user.id:
        # 404 (not 403) — never confirm existence of trips you don't own.
        # Matches the opacity convention used by delete_trip / create_share.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="trip_not_found")

    if trip.status in ("pending", "running"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="trip_busy")
    if trip.status == "aborted":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="trip_not_complete")
    # Defensive: status == "complete" but no Report row exists. Shouldn't
    # happen but the refiner has nothing to work from in that case.
    latest_q = (
        select(Report).where(Report.trip_id == trip_id).order_by(Report.created_at.desc()).limit(1)
    )
    latest_report = (await session.execute(latest_q)).scalar_one_or_none()
    if latest_report is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="trip_not_complete")

    # Strip the hint server-side — UI may pass leading/trailing whitespace.
    hint = body.hint.strip()
    if not hint:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="hint_empty")

    # Pre-allocate the new report id so we can return it in the 202.
    # The runner writes the row at this exact id; the client uses it to
    # correlate with the trip_complete SSE event.
    pre_report_id = UUID(bytes=secrets.token_bytes(16), version=4)
    previous_report_id = latest_report.id

    # Flip status back to running BEFORE committing so subsequent reads
    # see the busy state. The check above already locked the row.
    trip.status = "running"
    await session.commit()

    # Pre-create the SSE queue before scheduling the BackgroundTask so a
    # client can race straight to /stream without losing events. Same
    # ordering pattern as ``create_trip``.
    register(trip_id)
    background.add_task(run_refine, trip_id, previous_report_id, hint, user.id, pre_report_id)

    logger.info(
        "trip_refine_requested",
        trip_id=str(trip_id),
        previous_report_id=str(previous_report_id),
        new_report_id=str(pre_report_id),
        refine=True,
        refine_hint_len=len(hint),
    )
    return RefineTripResponse(report_id=pre_report_id, status="running")


@router.get(
    "/{trip_id}/reports",
    response_model=TripReportsResponse,
    summary="List all Report revisions for a trip (chronological, ASC).",
)
async def list_trip_reports(
    trip_id: UUID,
    user: Annotated[User, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_request_session)],
) -> TripReportsResponse:
    trip = await session.get(Trip, trip_id)
    if trip is None or trip.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="trip_not_found")

    stmt = (
        select(Report)
        .where(Report.trip_id == trip_id)
        .order_by(Report.created_at.asc(), Report.id.asc())
    )
    rows = (await session.execute(stmt)).scalars().all()

    summaries: list[_TripReportSummary] = []
    for row in rows:
        refine_meta: dict[str, object] | None = None
        if isinstance(row.content, dict):
            raw_meta = row.content.get("refine")
            if isinstance(raw_meta, dict):
                refine_meta = raw_meta
        hint_val: str | None = None
        prev_id_val: UUID | None = None
        if refine_meta is not None:
            raw_hint = refine_meta.get("hint")
            if isinstance(raw_hint, str):
                hint_val = raw_hint
            raw_prev = refine_meta.get("previous_report_id")
            if isinstance(raw_prev, str):
                try:
                    prev_id_val = UUID(raw_prev)
                except ValueError:
                    prev_id_val = None
        summaries.append(
            _TripReportSummary(
                report_id=row.id,
                created_at=row.created_at,
                is_original=refine_meta is None,
                hint=hint_val,
                previous_report_id=prev_id_val,
            )
        )

    return TripReportsResponse(reports=summaries)


class _ReportDetail(BaseModel):
    report_id: UUID
    trip_id: UUID
    created_at: datetime
    content: dict[str, object]
    is_original: bool


@router.get(
    "/{trip_id}/reports/{report_id}",
    response_model=_ReportDetail,
    summary="Fetch a specific Report revision by id.",
)
async def get_trip_report(
    trip_id: UUID,
    report_id: UUID,
    user: Annotated[User, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_request_session)],
) -> _ReportDetail:
    trip = await session.get(Trip, trip_id)
    if trip is None or trip.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="trip_not_found")

    report = await session.get(Report, report_id)
    if report is None or report.trip_id != trip_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="report_not_found")

    content = report.content if isinstance(report.content, dict) else {}
    is_original = not (isinstance(content.get("refine"), dict))
    return _ReportDetail(
        report_id=report.id,
        trip_id=report.trip_id,
        created_at=report.created_at,
        content=content,
        is_original=is_original,
    )
