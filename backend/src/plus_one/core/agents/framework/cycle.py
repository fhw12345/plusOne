"""Cycle main loop — Producer -> Joiner -> Controller, looped until done.

The cycle is generic: it knows how to call three async callables in order,
ask the Controller "should we continue", track depth, enforce a per-phase
timeout, and emit progress events. It does NOT know about ramen, Reddit,
or any Plus One specifics.

Domain agents adapt themselves to the three phase signatures::

    ProducerFn[Cand] = (AgentContext) -> PhaseResult[list[Cand]]
    JoinerFn[Cand, Joined] = (list[Cand], AgentContext) -> PhaseResult[list[Joined]]
    ControllerFn[Joined] = (list[Joined], AgentContext) -> PhaseResult[Decision]

Two entry points share a single internal stepper so behaviour, trace
content, and stop semantics stay aligned:

  - :func:`run_cycle` — wait for full result + return CycleResult
  - :func:`stream_cycle` — yield events as they happen (for SSE)

Stop conditions (in order):
  1. Producer returned empty -> ``cycle_aborted`` event then stop
  2. Phase exceeded ``ctx.phase_timeout`` -> ``cycle_aborted`` event then stop
  3. Controller says ``should_continue=False`` -> ``cycle_complete``
  4. ``ctx.depth >= ctx.max_depth`` -> ``cycle_complete``

``CycleAbortedError`` is the *terminal aggregate* result of an aborted
stream when consumed via :func:`run_cycle`. Stream consumers see only the
events; they should react to ``event.name == "cycle_aborted"`` themselves
rather than catching exceptions from the iterator.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol

import structlog

from plus_one.core.agents.framework.errors import CycleAbortedError
from plus_one.core.agents.framework.types import AgentContext, Decision, PhaseResult

logger = structlog.get_logger()


class ProgressEvent(Protocol):
    """Marker for events emitted during the cycle."""

    name: str
    depth: int


@dataclass(slots=True)
class _Event:
    """Generic, lightweight progress event."""

    name: str
    depth: int
    data: dict[str, Any]

    @classmethod
    def make(cls, name: str, depth: int, **data: object) -> _Event:
        return cls(name=name, depth=depth, data=dict(data))


@dataclass(slots=True)
class CycleResult[TJoined]:
    """Final output of a cycle run."""

    items: list[TJoined]
    decision: Decision
    ctx: AgentContext
    trace: list[_Event]
    aborted_reason: str | None = None
    """Set if the cycle ended via cycle_aborted (e.g. empty Producer / timeout)."""


type ProducerFn[TCand] = Callable[[AgentContext], Awaitable[PhaseResult[list[TCand]]]]
# Batch-2q widened the joiner phase result from a bare ``list`` to a
# payload object carrying ``items`` (the cycle's append target) alongside
# extra report-level fields like ``tl_dr``. The cycle stays generic by
# accepting either shape — see ``_extract_joined_items`` below.
type JoinerFn[TCand, TJoined] = Callable[[list[TCand], AgentContext], Awaitable[PhaseResult[Any]]]
type ControllerFn[TJoined] = Callable[
    [list[TJoined], AgentContext], Awaitable[PhaseResult[Decision]]
]


def _extract_joined_items(payload: Any) -> list[Any]:
    """Pull the joined-items list out of a Joiner phase payload.

    Accepts either:
      * a plain ``list`` (legacy v1/v2 joiner shape), or
      * an object with an ``items`` attribute (batch-2q ``JoinerPayload``).
    """
    if isinstance(payload, list):
        return payload
    items = getattr(payload, "items", None)
    if isinstance(items, list):
        return items
    return []


async def _await_with_timeout[T](coro: Awaitable[T], seconds: float | None) -> T:
    """``asyncio.wait_for`` shim that passes through when ``seconds`` is None.

    Named ``seconds`` rather than ``timeout`` to dodge the ASYNC109 lint
    (which assumes a ``timeout`` kwarg on an async function is a public API
    smell — true for end-user APIs, false for this internal helper).
    """
    if seconds is None:
        return await coro
    return await asyncio.wait_for(coro, timeout=seconds)


async def _step_cycle[TCand, TJoined](
    *,
    producer: ProducerFn[TCand],
    joiner: JoinerFn[TCand, TJoined],
    controller: ControllerFn[TJoined],
    ctx: AgentContext,
    accumulated: list[TJoined],
) -> AsyncIterator[_Event]:
    """Single source of truth for cycle behaviour.

    Both :func:`run_cycle` and :func:`stream_cycle` consume this. ``accumulated``
    is mutated in place so the caller can see Joiner output even on early
    termination.

    On a fatal condition (empty Producer, phase timeout, cancellation) yields
    a single ``cycle_aborted`` event with a ``reason`` data field and returns —
    NEVER raises into the consumer's ``async for`` loop. Cancellation is
    re-raised after yielding the event so structured-concurrency cleanup
    still runs upstream.
    """
    timeout = ctx.phase_timeout

    while True:
        yield _Event.make("iteration_start", ctx.depth)

        # === Producer phase ===
        try:
            producer_result = await _await_with_timeout(producer(ctx), timeout)
        except TimeoutError:
            yield _Event.make("cycle_aborted", ctx.depth, reason="producer timeout")
            return
        except asyncio.CancelledError:
            yield _Event.make("cycle_aborted", ctx.depth, reason="cancelled")
            raise

        candidates = producer_result.payload
        yield _Event.make(
            "producer",
            ctx.depth,
            n_candidates=len(candidates),
            notes=producer_result.notes,
        )

        if not candidates:
            yield _Event.make("cycle_aborted", ctx.depth, reason="empty producer")
            return

        # === Joiner phase ===
        try:
            joiner_result = await _await_with_timeout(joiner(candidates, ctx), timeout)
        except TimeoutError:
            yield _Event.make("cycle_aborted", ctx.depth, reason="joiner timeout")
            return
        except asyncio.CancelledError:
            yield _Event.make("cycle_aborted", ctx.depth, reason="cancelled")
            raise

        joined_items = _extract_joined_items(joiner_result.payload)
        accumulated.extend(joined_items)
        yield _Event.make(
            "joiner",
            ctx.depth,
            n_in=len(candidates),
            n_out=len(joined_items),
            notes=joiner_result.notes,
        )

        # === Controller phase ===
        try:
            controller_result = await _await_with_timeout(controller(accumulated, ctx), timeout)
        except TimeoutError:
            yield _Event.make("cycle_aborted", ctx.depth, reason="controller timeout")
            return
        except asyncio.CancelledError:
            yield _Event.make("cycle_aborted", ctx.depth, reason="cancelled")
            raise

        decision = controller_result.payload
        yield _Event.make(
            "controller",
            ctx.depth,
            should_continue=decision.should_continue,
            reasoning=decision.reasoning,
        )

        ctx.summary = decision.summary or ctx.summary

        if not decision.should_continue:
            yield _Event.make("cycle_complete", ctx.depth, reason="controller stop")
            return

        ctx.depth += 1
        if ctx.at_depth_cap():
            yield _Event.make("cycle_complete", ctx.depth, reason="depth cap")
            return


async def run_cycle[TCand, TJoined](
    *,
    producer: ProducerFn[TCand],
    joiner: JoinerFn[TCand, TJoined],
    controller: ControllerFn[TJoined],
    ctx: AgentContext,
) -> CycleResult[TJoined]:
    """Run the cycle to completion.

    Aggregates the event stream into a :class:`CycleResult`. If the cycle
    aborts (empty Producer, phase timeout) the result has
    ``aborted_reason`` set and ``CycleAbortedError`` is raised so callers
    can short-circuit without inspecting the result.

    Use :func:`stream_cycle` directly if you want events without the raise.

    Raises:
        CycleAbortedError: cycle ended via a ``cycle_aborted`` event.
        asyncio.CancelledError: re-raised after a final event is recorded.
    """
    trace: list[_Event] = []
    accumulated: list[TJoined] = []
    last_decision = Decision(should_continue=False, reasoning="cycle never ran")
    aborted_reason: str | None = None

    async for event in _step_cycle(
        producer=producer,
        joiner=joiner,
        controller=controller,
        ctx=ctx,
        accumulated=accumulated,
    ):
        trace.append(event)
        if event.name == "controller":
            # Capture the latest controller decision so the result reflects
            # the actual stopping decision, not the initial placeholder.
            last_decision = Decision(
                should_continue=event.data.get("should_continue", False),
                reasoning=event.data.get("reasoning", ""),
                summary=ctx.summary,
            )
        elif event.name == "cycle_aborted":
            aborted_reason = str(event.data.get("reason", "unknown"))

    if aborted_reason is not None:
        logger.info("run_cycle_aborted", depth=ctx.depth, reason=aborted_reason)
        result = CycleResult(
            items=accumulated,
            decision=last_decision,
            ctx=ctx,
            trace=trace,
            aborted_reason=aborted_reason,
        )
        raise CycleAbortedError(aborted_reason) from _ResultCarrierError(result)

    return CycleResult(items=accumulated, decision=last_decision, ctx=ctx, trace=trace)


class _ResultCarrierError(Exception):
    """Internal exception wrapper used as ``__cause__`` so callers that
    catch :class:`CycleAbortedError` can still introspect the partial
    :class:`CycleResult` via ``exc.__cause__.result``.

    Not part of the public API.
    """

    def __init__(self, result: CycleResult[Any]) -> None:
        super().__init__(f"partial result with {len(result.items)} items")
        self.result = result


async def stream_cycle[TCand, TJoined](
    *,
    producer: ProducerFn[TCand],
    joiner: JoinerFn[TCand, TJoined],
    controller: ControllerFn[TJoined],
    ctx: AgentContext,
) -> AsyncIterator[_Event]:
    """Yield each progress event as it happens.

    Designed for the SSE endpoint that pushes live progress to the frontend.
    Never raises into the consumer's loop except for ``CancelledError``;
    abort conditions surface as a final ``cycle_aborted`` event with a
    ``reason`` data field, after which the iterator simply ends.

    Callers that want a "the cycle aborted" hard signal should use
    :func:`run_cycle` instead, which raises :class:`CycleAbortedError`.
    """
    accumulated: list[TJoined] = []
    async for event in _step_cycle(
        producer=producer,
        joiner=joiner,
        controller=controller,
        ctx=ctx,
        accumulated=accumulated,
    ):
        yield event
