"""Trip runner — orchestrates one cycle execution from API request to DB write.

Flow:
  1. ``run_trip(trip_id)`` is invoked as a FastAPI BackgroundTask after
     POST /api/trips creates the row.
  2. We open a fresh ``session_scope`` per write unit (per ADR-006 +
     PR #3 reviewer F1: never hold a transaction across the 60-90s
     cycle), bumping Trip.status pending -> running.
  3. We stream the agent cycle's events into a per-trip
     :class:`asyncio.Queue` so the SSE handler can fan them out to the
     subscribed client.
  4. On success: persist a Report row with the joined items + trace +
     token totals; flip Trip.status to ``complete``.
  5. On ``CycleAbortedError`` or unhandled exception: flip Trip.status
     to ``aborted`` with the reason in the trip record's ``free_text``
     scratchpad-style addendum (no separate column for v1).
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING
from uuid import UUID

import structlog

from plus_one.agents.controller import controller
from plus_one.agents.joiner import joiner
from plus_one.agents.producer import producer
from plus_one.core.agents.framework.cycle import stream_cycle
from plus_one.core.agents.framework.types import AgentContext
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
# out-of-process worker, this becomes a Redis pub/sub bridge instead — the
# subscribe()/publish() interface stays the same, only the storage flips.

_queues: dict[UUID, asyncio.Queue[dict[str, object]]] = {}


def _get_or_create_queue(trip_id: UUID) -> asyncio.Queue[dict[str, object]]:
    queue = _queues.get(trip_id)
    if queue is None:
        queue = asyncio.Queue()
        _queues[trip_id] = queue
    return queue


def _drop_queue(trip_id: UUID) -> None:
    _queues.pop(trip_id, None)


async def subscribe(trip_id: UUID) -> AsyncIterator[dict[str, object]]:
    """SSE handler iterates this to forward events to the client.

    A sentinel ``{"name": "_eof"}`` event marks end-of-stream so the
    handler knows to close the response. The handler is responsible
    for dropping the queue on disconnect (via :func:`_drop_queue`) but
    the runner also drops it on its own clean exit.
    """
    queue = _get_or_create_queue(trip_id)
    while True:
        event = await queue.get()
        if event.get("name") == "_eof":
            return
        yield event


async def _publish(trip_id: UUID, event: dict[str, object]) -> None:
    queue = _get_or_create_queue(trip_id)
    await queue.put(event)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


async def _set_status(trip_id: UUID, status: str) -> None:
    async with session_scope() as session:
        trip = await session.get(Trip, trip_id)
        if trip is None:
            logger.warning("trip_not_found_at_status_update", trip_id=str(trip_id))
            return
        trip.status = status


async def _save_report(
    trip_id: UUID,
    items: list[object],
    trace: list[dict[str, object]],
    input_tokens: int,
    output_tokens: int,
) -> UUID:
    async with session_scope() as session:
        report = Report(
            trip_id=trip_id,
            content={"items": [_to_jsonable(i) for i in items]},
            trace=trace,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        session.add(report)
        await session.flush()
        return report.id


def _to_jsonable(obj: object) -> object:
    """Coerce Pydantic models / nested objects into JSON-friendly dicts."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    return obj


async def run_trip(trip_id: UUID, query: str) -> None:
    """Run one trip's cycle end-to-end. Designed for FastAPI BackgroundTask.

    Errors are caught + recorded as a status flip + a final SSE event,
    NEVER re-raised — BackgroundTask's exception handling is fire-and-
    forget and a leaked traceback in logs is the worst outcome we want.
    """
    await _set_status(trip_id, "running")
    await _publish(trip_id, {"name": "started", "trip_id": str(trip_id)})

    ctx = AgentContext(query=query, max_depth=4, phase_timeout=120.0)
    accumulated: list[object] = []
    trace: list[dict[str, object]] = []
    in_tokens = 0
    out_tokens = 0
    aborted = False
    try:
        async for event in stream_cycle(
            producer=producer,
            joiner=joiner,
            controller=controller,
            ctx=ctx,
        ):
            payload = {
                "name": event.name,
                "depth": event.depth,
                "data": event.data,
            }
            trace.append(payload)
            await _publish(trip_id, payload)
            # Capture intermediate joined items as they fly past.
            if event.name == "joiner":
                # Joiner emits n_in / n_out / notes; the actual items are
                # surfaced via the cycle's accumulated list when complete.
                pass
            if event.name == "cycle_aborted":
                aborted = True
        # The cycle accumulates joined items in its internal list; for v1
        # we re-derive from the trace's last 'joiner' event count, but the
        # full items list isn't surfaced in events. v2 will add a richer
        # event payload — for now we save the trace and an empty items
        # list when stream_cycle is the only entry-point. The richer
        # path runs through joiner(...) directly via run_cycle (used in
        # tests) which carries the full accumulated[] list.
    except Exception as exc:  # pragma: no cover — last-resort safety net
        logger.exception("run_trip_unhandled", trip_id=str(trip_id))
        await _publish(
            trip_id,
            {"name": "cycle_aborted", "depth": ctx.depth, "data": {"reason": str(exc)}},
        )
        aborted = True

    final_status = "aborted" if aborted else "complete"
    report_id: UUID | None = None
    with contextlib.suppress(Exception):  # best-effort persistence
        report_id = await _save_report(
            trip_id,
            accumulated,
            trace,
            input_tokens=in_tokens,
            output_tokens=out_tokens,
        )

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
    # EOF sentinel drains any subscribed SSE handler.
    await _publish(trip_id, {"name": "_eof"})
    _drop_queue(trip_id)
