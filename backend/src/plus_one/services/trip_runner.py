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
import json
import os
from datetime import date
from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from plus_one.agents.controller import controller as controller_phase
from plus_one.agents.itinerary import ItineraryPlan
from plus_one.agents.joiner import JoinedItem, JoinerPayload
from plus_one.agents.joiner import joiner as joiner_phase
from plus_one.agents.producer import Candidate
from plus_one.agents.producer import producer as producer_phase
from plus_one.agents.prompts import load_prompt
from plus_one.agents.refiner import refine as refine_phase
from plus_one.agents.translator import translate_items, translate_tl_dr
from plus_one.core.agents.framework.cycle import run_cycle
from plus_one.core.agents.framework.errors import CycleAbortedError
from plus_one.core.agents.framework.types import (
    AgentContext,
    CompanionForContext,
    Decision,
    PhaseResult,
    UserProfileForContext,
)
from plus_one.core.db.models import Companion, Profile, Report, Trip
from plus_one.core.db.session import session_scope
from plus_one.core.llm import Message
from plus_one.core.llm import factory as llm_factory

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = structlog.get_logger()

# Retry budget for the defense-in-depth loops in _set_status / _save_report.
# Three attempts at 50ms covers ~150ms total — enough for a request-session
# commit to land on a fresh-pool connection, well under any user-visible bar.
_RETRY_ATTEMPTS = 3


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
    for attempt in range(_RETRY_ATTEMPTS):
        async with session_scope() as session:
            trip = await session.get(Trip, trip_id)
            if trip is not None:
                trip.status = status
                return
        if attempt < _RETRY_ATTEMPTS - 1:
            await asyncio.sleep(0.05)
    logger.warning("trip_not_found_at_status_update", trip_id=str(trip_id))


async def _save_report(
    trip_id: UUID,
    items: list[JoinedItem],
    trace: list[dict[str, object]],
    input_tokens: int,
    output_tokens: int,
    tl_dr: str | None = None,
) -> UUID:
    # Same defense-in-depth as _set_status: retry the insert if the FK
    # validation trips (trip row not yet visible to this session). Fail
    # loud after 3 attempts so a real bug isn't silently swallowed.
    last_exc: IntegrityError | None = None
    # Batch-2q: optional report-level TL;DR. We only set the key when the
    # joiner emitted a non-empty, non-whitespace string so old-report
    # consumers don't accidentally render an empty sticky note.
    content: dict[str, Any] = {"items": [i.model_dump(mode="json") for i in items]}
    if tl_dr is not None and tl_dr.strip():
        content["tl_dr"] = tl_dr.strip()
    for attempt in range(_RETRY_ATTEMPTS):
        try:
            async with session_scope() as session:
                report = Report(
                    trip_id=trip_id,
                    content=content,
                    trace=trace,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )
                session.add(report)
                await session.flush()
                return report.id
        except IntegrityError as exc:
            last_exc = exc
            if attempt < _RETRY_ATTEMPTS - 1:
                await asyncio.sleep(0.05)
    assert last_exc is not None
    raise last_exc


# ---------------------------------------------------------------------------
# Post-cycle translation
# ---------------------------------------------------------------------------


def _translate_enabled() -> bool:
    """Read ``PLUS_ONE_TRANSLATE_ENABLED``; default ``True``.

    Off-switch (PRD batch 2k §6.2) — set to "0" in e2e + when translation
    misbehaves in prod. Read per-call so tests can monkeypatch.
    """
    raw = os.getenv("PLUS_ONE_TRANSLATE_ENABLED")
    if raw is None:
        return True
    return raw.strip().lower() not in ("0", "false", "no", "")


def _translate_langs() -> tuple[str, ...]:
    """Comma-separated target langs from ``PLUS_ONE_TRANSLATE_LANGS``.

    Default ``("en", "zh")``. The source-language item stays under
    ``content.items`` untouched; translations land under
    ``content.translations[<lang>]``.
    """
    raw = os.getenv("PLUS_ONE_TRANSLATE_LANGS", "en,zh")
    return tuple(part.strip() for part in raw.split(",") if part.strip())


async def _run_translations_and_update(
    report_id: UUID,
    items: list[JoinedItem],
    tl_dr: str | None = None,
) -> None:
    """Translate ``items`` (+ optional ``tl_dr``) into each enabled lang.

    Best-effort: any exception is logged and swallowed (the trip already
    saved the original-language report, so the user still sees results).

    Batch-2q widened the per-language shape: ``translations[lang]`` is now
    an object ``{"items": [...], "tl_dr": "..."}`` so the language toggle
    can swap both the per-card text and the top-of-report TL;DR. Old
    reports that pre-date this batch keep their bare-array shape and the
    frontend zod transform normalises both shapes to the object form.

    The Report row is re-read inside its own ``session_scope`` so we
    don't hold a transaction across the LLM calls (~ADR-006 + ADR
    short-session pattern).
    """
    if not items:
        return
    langs = _translate_langs()
    if not langs:
        return

    translations: dict[str, dict[str, Any]] = {}
    for lang in langs:
        per_lang: dict[str, Any] = {}
        try:
            per_lang["items"] = await translate_items(items, src_lang="original", dst_lang=lang)
        except Exception:
            logger.exception("translation_failed", report_id=str(report_id), lang=lang)
            # If items translation blew up, don't carry a half-built entry —
            # the frontend would render an empty tab.
            continue
        if tl_dr is not None and tl_dr.strip():
            try:
                per_lang["tl_dr"] = await translate_tl_dr(
                    tl_dr.strip(), src_lang="original", dst_lang=lang
                )
            except Exception:
                logger.exception("translation_tl_dr_failed", report_id=str(report_id), lang=lang)
                # Fail-soft to the source string so the language toggle
                # still has something to show.
                per_lang["tl_dr"] = tl_dr.strip()
        translations[lang] = per_lang

    if not translations:
        return

    async with session_scope() as session:
        report = await session.get(Report, report_id)
        if report is None:
            logger.warning("translation_report_missing", report_id=str(report_id))
            return
        # JSONB column needs a NEW dict object for SQLAlchemy to detect
        # the change — mutating in place won't dirty the attribute.
        new_content: dict[str, Any] = dict(report.content or {})
        new_content["translations"] = translations
        report.content = new_content


# ---------------------------------------------------------------------------
# Itinerary scheduler (batch-3a)
# ---------------------------------------------------------------------------


async def _load_trip_dates(trip_id: UUID) -> tuple[date | None, date | None]:
    """Read the Trip row's date_start / date_end and project to ``date``.

    The ORM column type is ``datetime`` (timezone-aware). The agent-side
    context + scheduler model use ``date``, so we drop the time portion
    here. Returns ``(None, None)`` on a missing trip row — the caller's
    scheduler then falls back to the default 3-day plan.
    """
    async with session_scope() as session:
        trip = await session.get(Trip, trip_id)
        if trip is None:
            return None, None
        ds = trip.date_start.date() if trip.date_start is not None else None
        de = trip.date_end.date() if trip.date_end is not None else None
        return ds, de


_ITINERARY_ELIGIBLE: frozenset[str] = frozenset({"local_gem", "neutral"})
_ITINERARY_MAX_DAYS = 7
_ITINERARY_DEFAULT_DAYS = 3


async def _run_itinerary_scheduler(
    items: list[JoinedItem],
    date_start: date | None,
    date_end: date | None,
) -> list[dict[str, Any]] | None:
    """Ask the scheduler LLM to arrange eligible items into days x periods.

    Returns the JSON-serialisable list of ``DayPlan`` dicts on success,
    or ``None`` on any failure (no eligible items, LLM error, validation
    error). The caller treats ``None`` as "skip day_plan patching" so the
    frontend falls back to the flat report view (PRD AC-9 / AC-12).

    Best-effort by design: this MUST NOT crash the surrounding cycle.
    """
    try:
        eligible_indices: list[int] = [
            idx for idx, item in enumerate(items) if item.classification in _ITINERARY_ELIGIBLE
        ]
        if not eligible_indices:
            return None

        if date_start is not None and date_end is not None:
            day_count = min(_ITINERARY_MAX_DAYS, max(1, (date_end - date_start).days + 1))
        else:
            day_count = _ITINERARY_DEFAULT_DAYS

        # Build items_json with the ORIGINAL index (not the filtered
        # position) so the LLM's `item_index` lines up with `items[i]`
        # downstream. Critical for slot resolution on the frontend.
        items_payload = [
            {
                "index": idx,
                "name": items[idx].candidate.name,
                "area": items[idx].candidate.area or "",
                "classification": items[idx].classification,
            }
            for idx in eligible_indices
        ]
        items_json = json.dumps(items_payload, ensure_ascii=False)

        # Destination is implicit in the items; reuse the first eligible
        # item's `area` if available, else empty.
        destination = ""
        for idx in eligible_indices:
            if items[idx].candidate.area:
                destination = items[idx].candidate.area or ""
                break

        prompt = (
            load_prompt("itinerary", "v1")
            .replace("{destination}", destination)
            .replace(
                "{date_start_iso_or_none}",
                date_start.isoformat() if date_start else "none",
            )
            .replace(
                "{date_end_iso_or_none}",
                date_end.isoformat() if date_end else "none",
            )
            .replace("{day_count}", str(day_count))
            .replace("{items_json}", items_json)
        )

        llm = llm_factory.get_llm_provider("itinerary_agent")
        response = await llm.complete(
            system=prompt,
            messages=[Message(role="user", content=items_json)],
            response_model=ItineraryPlan,
        )
        plan = response.parsed
        if plan is None:
            logger.warning("itinerary_scheduler_no_parse")
            return None

        # Defense in depth: ensure every emitted item_index is in range
        # (Pydantic validates >= 0 + dedup, but does not know N items).
        n_items = len(items)
        for day in plan.days:
            for slot in day.slots:
                if slot.item_index >= n_items:
                    logger.warning(
                        "itinerary_scheduler_oor_index",
                        item_index=slot.item_index,
                        n_items=n_items,
                    )
                    return None

        return [day.model_dump(mode="json") for day in plan.days]
    except ValidationError as exc:
        logger.warning("itinerary_scheduler_validation_failed", error=str(exc))
        return None
    except Exception:
        logger.exception("itinerary_scheduler_failed")
        return None


async def _update_report_day_plan(report_id: UUID, day_plan: list[dict[str, Any]]) -> None:
    """Patch ``content.day_plan`` on an existing Report row.

    Uses ``jsonb_set`` so the surrounding content (items, translations,
    tl_dr, refine) is untouched. Best-effort: any failure is logged and
    swallowed so a scheduler-side hiccup never flips a successful trip
    to aborted.
    """
    try:
        payload = json.dumps(day_plan, ensure_ascii=False)
        async with session_scope() as session:
            await session.execute(
                text(
                    "UPDATE reports SET content = jsonb_set("
                    "COALESCE(content, '{}'::jsonb), '{day_plan}', "
                    "CAST(:dp AS jsonb), true) WHERE id = :rid"
                ),
                {"dp": payload, "rid": report_id},
            )
    except Exception:
        logger.exception("itinerary_day_plan_patch_failed", report_id=str(report_id))


async def _load_profile_context(
    user_id: UUID,
    companion_ids: list[UUID] | None = None,
) -> tuple[UserProfileForContext, list[CompanionForContext]]:
    """Snapshot the user's Profile + Companions into agent-layer types.

    When ``companion_ids`` is None or empty, loads all of the user's
    companions (v1 contract / backward-compatible default).

    When ``companion_ids`` is non-empty, filters to that subset. Cross-user
    or unknown ids are silently dropped — the per-user ``user_id`` filter
    enforces ownership, and a missing id (e.g. companion deleted between
    trip-create and runner load) is treated as "user didn't select it"
    rather than a 4xx (the BackgroundTask path has no client to surface
    a 4xx to). See PRD §10 R1.

    Returns empty defaults when the user has no profile row (lazy-create
    path — see PRD §5 GET semantics + §10 migration safety). Defensive
    about JSONB shape so a malformed legacy row never crashes the cycle.
    """
    async with session_scope() as session:
        profile_row = (
            await session.execute(select(Profile).where(Profile.user_id == user_id))
        ).scalar_one_or_none()

        companion_stmt = (
            select(Companion)
            .where(Companion.user_id == user_id)
            .order_by(Companion.created_at.asc())
        )
        if companion_ids:
            companion_stmt = companion_stmt.where(Companion.id.in_(companion_ids))
        companion_rows = (await session.execute(companion_stmt)).scalars().all()

    user_profile = UserProfileForContext(id=user_id)
    if profile_row is not None:
        explicit = profile_row.explicit_preferences or {}
        user_profile = UserProfileForContext(
            id=user_id,
            loves=tuple(explicit.get("loves") or ()),
            hates=tuple(explicit.get("hates") or ()),
        )

    companions: list[CompanionForContext] = []
    for c in companion_rows:
        explicit = c.explicit_preferences or {}
        companions.append(
            CompanionForContext(
                id=c.id,
                name=c.name,
                loves=tuple(explicit.get("loves") or ()),
                hates=tuple(explicit.get("hates") or ()),
            )
        )
    return user_profile, companions


async def run_trip(
    trip_id: UUID,
    query: str,
    user_id: UUID,
    companion_ids: list[UUID] | None = None,
) -> None:
    """Run one trip's cycle end-to-end. Designed for FastAPI BackgroundTask.

    Errors are caught + recorded as a status flip + a final SSE event,
    NEVER re-raised — BackgroundTask exception handling is fire-and-forget
    and a leaked traceback is the worst outcome we want.

    ``user_id`` is passed by the POST handler so the runner can load the
    user's Profile + Companions into AgentContext without re-reading the
    Trip row (which doesn't carry the user object eagerly).

    ``companion_ids`` (None / [] = all-companions, non-empty = filter to
    that subset) drives per-trip companion selection. See
    ``_load_profile_context``.

    Batch-2o note: ``Trip.date_start``, ``Trip.date_end``,
    ``Trip.budget_amount``, ``Trip.budget_currency`` are persisted by
    the POST handler but NOT yet projected into ``AgentContext``. The
    agents currently see only the destination + free_text concatenation
    via ``query``. Follow-up batch will widen ``AgentContext`` to carry
    the structured hints so the planner can use them.
    """
    register(trip_id)  # idempotent guard in case POST handler forgot
    try:
        await _set_status(trip_id, "running")
        await _publish(trip_id, {"name": "started", "trip_id": str(trip_id)})

        user_profile, selected_companions = await _load_profile_context(user_id, companion_ids)
        # Batch-3a: project Trip.date_start / date_end into AgentContext so
        # the itinerary scheduler can size the day count.
        trip_date_start, trip_date_end = await _load_trip_dates(trip_id)
        ctx = AgentContext(
            query=query,
            max_depth=4,
            phase_timeout=120.0,
            user_profile=user_profile,
            selected_companions=selected_companions,
            date_start=trip_date_start,
            date_end=trip_date_end,
        )
        trace: list[dict[str, object]] = []

        # Wrap each phase so we can tee per-phase progress into the SSE
        # queue while still letting run_cycle aggregate the items list.
        # The wrappers also capture token counts via the agent's notes
        # field (the agents log usage there as "in_tokens=X out_tokens=Y").
        token_totals = {"in": 0, "out": 0}
        # Batch-2q: the joiner emits a per-round ``tl_dr`` paragraph; the
        # final round's value wins (earlier rounds are discarded, same
        # lifecycle as ``ctx.summary``). Stored in a single-key dict so
        # the nested ``joiner_pump`` closure can mutate it.
        latest_tl_dr: dict[str, str | None] = {"value": None}

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
        ) -> PhaseResult[JoinerPayload]:
            result = await joiner_phase(cands, c)
            ev = {
                "name": "joiner",
                "depth": c.depth,
                "data": {
                    "n_in": len(cands),
                    "n_out": len(result.payload.items),
                    "notes": result.notes,
                },
            }
            trace.append(ev)
            await _publish(trip_id, ev)
            _accumulate_tokens(result.notes)
            # Capture the latest TL;DR — the final round wins, mirroring
            # how ``summary`` is overwritten each iteration. See batch-2q
            # PRD §4.1 ("last round's tl_dr is what gets persisted").
            if result.payload.tl_dr is not None:
                latest_tl_dr["value"] = result.payload.tl_dr
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
                tl_dr=latest_tl_dr["value"],
            )
        except Exception:
            logger.exception("report_save_failed", trip_id=str(trip_id))
            report_save_failed = True

        if aborted_reason is not None or report_save_failed:  # noqa: SIM108
            final_status = "aborted"
        else:
            final_status = "complete"

        # Batch-3a: best-effort itinerary scheduler. Runs only when the
        # report saved successfully and we have items to schedule. Failures
        # are swallowed inside _run_itinerary_scheduler so a scheduler
        # hiccup never flips the trip to aborted.
        if report_id is not None and not report_save_failed and aborted_reason is None and items:
            day_plan = await _run_itinerary_scheduler(items, ctx.date_start, ctx.date_end)
            if day_plan is not None:
                await _update_report_day_plan(report_id, day_plan)

        # Best-effort post-cycle translations (PRD batch 2k §6.4). Runs
        # only on a successful report write, gated by
        # PLUS_ONE_TRANSLATE_ENABLED (default on). Failure is swallowed
        # inside _run_translations_and_update — the user already has the
        # original-language report.
        if (
            report_id is not None
            and not report_save_failed
            and aborted_reason is None
            and _translate_enabled()
        ):
            with contextlib.suppress(Exception):
                await _run_translations_and_update(report_id, items, latest_tl_dr["value"])

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


# ---------------------------------------------------------------------------
# Refine cycle (batch-2u)
# ---------------------------------------------------------------------------
#
# Unlike `run_trip`, `run_refine` does NOT re-run the producer/joiner/
# controller cycle. It runs a single LLM call (the refiner agent) that
# takes the previous report's items + the user's hint and emits a new
# items list. The new Report row is written with `content.refine`
# metadata so the UI can render the version history.
#
# It piggy-backs on the existing per-trip SSE queue: the API handler
# calls `register(trip_id)` before scheduling the BackgroundTask, and
# we publish the same `started` / `iteration_start` / `joiner` /
# `trip_complete` event names plus a new `refine_started` event so
# the existing frontend stream parser keeps working.


async def _save_refine_report(
    report_id: UUID,
    trip_id: UUID,
    items: list[JoinedItem],
    trace: list[dict[str, object]],
    input_tokens: int,
    output_tokens: int,
    previous_report_id: UUID,
    hint: str,
    tl_dr: str = "",
) -> UUID:
    """Persist a refine Report row at a pre-allocated id.

    The id is allocated by the API handler so the 202 response can
    promise the client which row will land. We use INSERT with an
    explicit primary key (not ``default=new_uuid``) — SQLAlchemy treats
    that as a plain column write.

    Same defense-in-depth retry as :func:`_save_report`: an FK
    violation can happen if the trip-row write hasn't propagated yet,
    so retry a couple of times before failing the cycle.
    """
    content: dict[str, Any] = {
        "items": [i.model_dump(mode="json") for i in items],
        "refine": {
            "previous_report_id": str(previous_report_id),
            "hint": hint,
        },
    }
    if tl_dr:
        content["tl_dr"] = tl_dr

    last_exc: IntegrityError | None = None
    for attempt in range(_RETRY_ATTEMPTS):
        try:
            async with session_scope() as session:
                report = Report(
                    id=report_id,
                    trip_id=trip_id,
                    content=content,
                    trace=trace,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )
                session.add(report)
                await session.flush()
                return report.id
        except IntegrityError as exc:
            last_exc = exc
            if attempt < _RETRY_ATTEMPTS - 1:
                await asyncio.sleep(0.05)
    assert last_exc is not None
    raise last_exc


async def run_refine(
    trip_id: UUID,
    previous_report_id: UUID,
    hint: str,
    user_id: UUID,
    report_id: UUID,
) -> None:
    """Run one refine cycle end-to-end.

    Designed for FastAPI BackgroundTask. Errors are caught + recorded
    as a status flip + a final SSE event, NEVER re-raised — same
    fire-and-forget contract as :func:`run_trip`.

    Args:
        trip_id: The trip being refined.
        previous_report_id: The report the user is refining against
            (almost always the latest, but the API hands it through
            explicitly so this coroutine doesn't need to query again).
        hint: User's verbatim refinement instruction (already trimmed
            + length-validated at the API boundary).
        user_id: Owner of the trip. Kept in the signature for symmetry
            with :func:`run_trip` and for future profile re-snapshot.
        report_id: Pre-allocated UUID for the new Report row. The 202
            response already returned this to the client.
    """
    del user_id  # reserved for future profile re-snapshot (PRD §8.3)
    register(trip_id)  # idempotent guard in case POST handler forgot
    try:
        await _set_status(trip_id, "running")
        await _publish(trip_id, {"name": "started", "trip_id": str(trip_id)})
        await _publish(
            trip_id,
            {
                "name": "refine_started",
                "trip_id": str(trip_id),
                "previous_report_id": str(previous_report_id),
                "hint": hint,
            },
        )

        trace: list[dict[str, object]] = []
        previous_items: list[dict[str, Any]] = []
        previous_tl_dr: str = ""

        # Load the previous report's content so the refiner has something
        # to work from. We accept whatever shape was persisted — old
        # reports may not carry tl_dr, and that's fine.
        async with session_scope() as session:
            prev = await session.get(Report, previous_report_id)
            if prev is not None and isinstance(prev.content, dict):
                raw_items = prev.content.get("items")
                if isinstance(raw_items, list):
                    previous_items = raw_items
                raw_tl_dr = prev.content.get("tl_dr")
                if isinstance(raw_tl_dr, str):
                    previous_tl_dr = raw_tl_dr

        aborted_reason: str | None = None
        new_items: list[JoinedItem] = []
        new_tl_dr = ""
        input_tokens = 0
        output_tokens = 0
        try:
            new_items, new_tl_dr, input_tokens, output_tokens = await refine_phase(
                previous_items=previous_items,
                previous_tl_dr=previous_tl_dr,
                hint=hint,
            )
            ev = {
                "name": "joiner",
                "depth": 0,
                "data": {
                    "n_in": len(previous_items),
                    "n_out": len(new_items),
                    "notes": (f"refine in_tokens={input_tokens} out_tokens={output_tokens}"),
                },
            }
            trace.append(ev)
            await _publish(trip_id, ev)
        except Exception as exc:
            aborted_reason = str(exc)
            ev = {"name": "cycle_aborted", "depth": 0, "data": {"reason": aborted_reason}}
            trace.append(ev)
            await _publish(trip_id, ev)
            logger.info(
                "run_refine_aborted",
                trip_id=str(trip_id),
                previous_report_id=str(previous_report_id),
                refine=True,
                refine_hint_len=len(hint),
                reason=aborted_reason,
            )

        report_save_failed = False
        if not aborted_reason:
            try:
                await _save_refine_report(
                    report_id,
                    trip_id,
                    new_items,
                    trace,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    previous_report_id=previous_report_id,
                    hint=hint,
                    tl_dr=new_tl_dr,
                )
            except Exception:
                logger.exception(
                    "refine_report_save_failed",
                    trip_id=str(trip_id),
                    refine=True,
                )
                report_save_failed = True

        if aborted_reason is not None or report_save_failed:  # noqa: SIM108
            final_status = "aborted"
        else:
            final_status = "complete"

        # Batch-3a: regenerate the itinerary day_plan against the new
        # items set. Same best-effort contract as run_trip.
        if final_status == "complete" and new_items:
            refine_date_start, refine_date_end = await _load_trip_dates(trip_id)
            day_plan = await _run_itinerary_scheduler(new_items, refine_date_start, refine_date_end)
            if day_plan is not None:
                await _update_report_day_plan(report_id, day_plan)

        if final_status == "complete" and new_items and _translate_enabled():
            with contextlib.suppress(Exception):
                await _run_translations_and_update(report_id, new_items)

        with contextlib.suppress(Exception):
            await _set_status(trip_id, final_status)

        await _publish(
            trip_id,
            {
                "name": "trip_complete",
                "trip_id": str(trip_id),
                "status": final_status,
                "report_id": str(report_id) if final_status == "complete" else None,
            },
        )
        await _publish(trip_id, _EOF)
    finally:
        _drop_queue(trip_id)
