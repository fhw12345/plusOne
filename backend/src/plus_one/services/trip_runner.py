"""Trip runner — orchestrates one cycle execution from API request to DB write.

Flow:
  1. POST /api/trips creates the Trip row, calls :func:`register` to
     pre-create the per-trip event queue, then schedules ``run_trip``
     as a BackgroundTask. Pre-creating the queue (rather than letting
     ``run_trip`` create it lazily) closes a race where the SSE handler
     can hit ``subscribe()`` before the runner publishes its first
     event, ending up with an orphaned queue that blocks forever.
  2. ``run_trip(trip_id, query)`` opens its own ``session_scope`` per
     write unit (per ADR-006 + PR #3 reviewer F1: never hold a
     transaction across the 60-90s cycle), bumping Trip.status
     pending -> running.
  3. We drive the cycle with ``run_cycle`` (NOT ``stream_cycle``) so
     we get the accumulated joined items back as a CycleResult.items
     list, while teeing each event into the per-trip queue via a
     pump callable threaded through phase wrappers.
  4. On success: persist a Report row with the joined items + trace +
     token totals; flip Trip.status to ``complete``. If the report
     write itself fails, the trip flips to ``aborted`` (not
     ``complete``) — losing the Report row is the only persisted
     artifact, so silent loss is the wrong default.
  5. On ``CycleAbortedError`` or unhandled exception: flip Trip.status
     to ``aborted`` and emit a final cycle_aborted SSE event.

The per-trip queue is dropped in a ``try/finally`` so process shutdown
or runner crashes don't leak. The SSE handler also wraps its iteration
in try/finally so client disconnect doesn't leave the queue dangling
indefinitely either.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING
from uuid import UUID

import structlog
from sqlalchemy.exc import IntegrityError

from plus_one.agents.controller import controller as controller_phase
from plus_one.agents.joiner import JoinedItem
from plus_one.agents.joiner import joiner as joiner_phase
from plus_one.agents.producer import Candidate
from plus_one.agents.producer import producer as producer_phase
from plus_one.core.agents.framework.cycle import run_cycle
from plus_one.core.agents.framework.errors import CycleAbortedError
from plus_one.core.agents.framework.types import AgentContext, Decision, PhaseResult
from plus_one.core.db.models import Report, Trip
from plus_one.core.db.session import session_scope

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Per-trip event broker
# ---------------------------------------------------------------------------
#
# When the runner produces a progress event, we put it on a queue keyed by
# trip_id. The SSE handler subscribes to that queue. We use plain
# ``asyncio.Queue`` because both producer and consumer live in the same
# process (in-process worker for v1, per ADR-006). When v2 introduces an
# out-of-process worker, this becomes a Redis pub/sub bridge — the
# subscribe()/publish() interface stays the same, only storage flips.
#
# Queue lifecycle (Reviewer B1 / M1 fix):
#   - register(trip_id) is called from POST handler BEFORE BackgroundTask
#     schedules run_trip — guarantees the queue exists before subscribe().
#   - subscribe(trip_id) attaches to an existing queue; if none exists
#     (e.g., stale/replay subscribe to a trip whose runner already finished),
#     it returns immediately. Never creates.
#   - run_trip drops the queue in a finally block so crash / cancellation
#     paths don't leak. SSE handler's finally guards client-disconnect.

_EOF: dict[str, object] = {"name": "_eof"}
_queues: dict[UUID, asyncio.Queue[dict[str, object]]] = {}


def register(trip_id: UUID) -> None:
    """Create the per-trip queue. Idempotent. Call from POST handler."""
    _queues.setdefault(trip_id, asyncio.Queue())


def _drop_queue(trip_id: UUID) -> None:
    _queues.pop(trip_id, None)


async def subscribe(trip_id: UUID) -> AsyncIterator[dict[str, object]]:
    """SSE handler iterates this to forward events to the client.

    Returns immediately (yields nothing) if the queue is unknown — covers
    the stale-replay / wrong-trip-id path so we don't create an orphan.

    The EOF sentinel ``{"name": "_eof"}`` ends the stream cleanly.
    """
    queue = _queues.get(trip_id)
    if queue is None:
        return
    while True:
        event = await queue.get()
        if event.get("name") == "_eof":
            return
        yield event


async def _publish(trip_id: UUID, event: dict[str, object]) -> None:
    queue = _queues.get(trip_id)
    if queue is None:
        # Runner published into a queue that's already gone (shouldn't
        # normally happen — register is called first). Drop on the floor
        # rather than NPE.
        logger.warning("publish_after_drop", trip_id=str(trip_id), name=event.get("name"))
        return
    await queue.put(event)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


async def _set_status(trip_id: UUID, status: str) -> None:
    # Defense-in-depth retry: the POST handler now commits the trip row
    # before scheduling this background task (api/trips.py), but a future
    # deploy with read-replica lag or pool quirks could resurrect the race.
    # Bounded retry keeps a cheap safety net without masking persistent
    # bugs — final failure still logs trip_not_found_at_status_update.
    for attempt in range(3):
        async with session_scope() as session:
            trip = await session.get(Trip, trip_id)
            if trip is not None:
                trip.status = status
                return
        if attempt < 2:
            await asyncio.sleep(0.05)
    logger.warning("trip_not_found_at_status_update", trip_id=str(trip_id))


async def _save_report(
    trip_id: UUID,
    items: list[JoinedItem],
    trace: list[dict[str, object]],
    input_tokens: int,
    output_tokens: int,
) -> UUID:
    # Same defense-in-depth as _set_status: retry the insert if the FK
    # validation trips (trip row not yet visible to this session). Fail
    # loud after 3 attempts so a real bug isn't silently swallowed.
    last_exc: IntegrityError | None = None
    for attempt in range(3):
        try:
            async with session_scope() as session:
                report = Report(
                    trip_id=trip_id,
                    content={"items": [i.model_dump(mode="json") for i in items]},
                    trace=trace,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )
                session.add(report)
                await session.flush()
                return report.id
        except IntegrityError as exc:
            last_exc = exc
            if attempt < 2:
                await asyncio.sleep(0.05)
    assert last_exc is not None
    raise last_exc


async def run_trip(trip_id: UUID, query: str) -> None:
    """Run one trip's cycle end-to-end. Designed for FastAPI BackgroundTask.

    Errors are caught + recorded as a status flip + a final SSE event,
    NEVER re-raised — BackgroundTask exception handling is fire-and-forget
    and a leaked traceback is the worst outcome we want.
    """
    register(trip_id)  # idempotent guard in case POST handler forgot
    try:
        await _set_status(trip_id, "running")
        await _publish(trip_id, {"name": "started", "trip_id": str(trip_id)})

        ctx = AgentContext(query=query, max_depth=4, phase_timeout=120.0)
        trace: list[dict[str, object]] = []

        # Wrap each phase so we can tee per-phase progress into the SSE
        # queue while still letting run_cycle aggregate the items list.
        # The wrappers also capture token counts via the agent's notes
        # field (the agents log usage there as "in_tokens=X out_tokens=Y").
        token_totals = {"in": 0, "out": 0}

        def _accumulate_tokens(notes: str) -> None:
            for tok_kind, key in (("in_tokens=", "in"), ("out_tokens=", "out")):
                if tok_kind in notes:
                    try:
                        tail = notes.split(tok_kind, 1)[1]
                        n = int(tail.split(maxsplit=1)[0])
                        token_totals[key] += n
                    except (ValueError, IndexError):
                        pass

        async def producer_pump(c: AgentContext) -> PhaseResult[list[Candidate]]:
            event = {"name": "iteration_start", "depth": c.depth, "data": {}}
            trace.append(event)
            await _publish(trip_id, event)
            result = await producer_phase(c)
            ev = {
                "name": "producer",
                "depth": c.depth,
                "data": {"n_candidates": len(result.payload), "notes": result.notes},
            }
            trace.append(ev)
            await _publish(trip_id, ev)
            _accumulate_tokens(result.notes)
            return result

        async def joiner_pump(
            cands: list[Candidate], c: AgentContext
        ) -> PhaseResult[list[JoinedItem]]:
            result = await joiner_phase(cands, c)
            ev = {
                "name": "joiner",
                "depth": c.depth,
                "data": {
                    "n_in": len(cands),
                    "n_out": len(result.payload),
                    "notes": result.notes,
                },
            }
            trace.append(ev)
            await _publish(trip_id, ev)
            _accumulate_tokens(result.notes)
            return result

        async def controller_pump(
            items_in: list[JoinedItem], c: AgentContext
        ) -> PhaseResult[Decision]:
            result = await controller_phase(items_in, c)
            ev = {
                "name": "controller",
                "depth": c.depth,
                "data": {
                    "should_continue": result.payload.should_continue,
                    "reasoning": result.payload.reasoning,
                    "notes": result.notes,
                },
            }
            trace.append(ev)
            await _publish(trip_id, ev)
            return result

        aborted_reason: str | None = None
        items: list[JoinedItem] = []
        try:
            cycle_result = await run_cycle(
                producer=producer_pump,
                joiner=joiner_pump,
                controller=controller_pump,
                ctx=ctx,
            )
            items = cycle_result.items
        except Exception as exc:
            aborted_reason = exc.reason if isinstance(exc, CycleAbortedError) else str(exc)
            # Try to recover items from the partial-result carrier (PR #2 pattern).
            cause = getattr(exc, "__cause__", None)
            partial = getattr(cause, "result", None)
            if partial is not None:
                items = list(getattr(partial, "items", []))
            ev = {"name": "cycle_aborted", "depth": ctx.depth, "data": {"reason": aborted_reason}}
            trace.append(ev)
            await _publish(trip_id, ev)
            logger.info("run_trip_aborted", trip_id=str(trip_id), reason=aborted_reason)

        # Persistence: report-save failure is fatal for status (Reviewer M3).
        report_id: UUID | None = None
        report_save_failed = False
        try:
            report_id = await _save_report(
                trip_id,
                items,
                trace,
                input_tokens=token_totals["in"],
                output_tokens=token_totals["out"],
            )
        except Exception:
            logger.exception("report_save_failed", trip_id=str(trip_id))
            report_save_failed = True

        if aborted_reason is not None or report_save_failed:  # noqa: SIM108
            final_status = "aborted"
        else:
            final_status = "complete"

        with contextlib.suppress(Exception):
            await _set_status(trip_id, final_status)

        await _publish(
            trip_id,
            {
                "name": "trip_complete",
                "trip_id": str(trip_id),
                "status": final_status,
                "report_id": str(report_id) if report_id else None,
            },
        )
        await _publish(trip_id, _EOF)
    finally:
        # Always drop the queue — even on cancellation / unhandled error
        # so the per-trip queue dictionary doesn't leak across hot reloads
        # or worker restarts.
        _drop_queue(trip_id)
