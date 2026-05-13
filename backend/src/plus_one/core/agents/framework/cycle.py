"""Cycle main loop — Producer -> Joiner -> Controller, looped until done.

The cycle is generic: it knows how to call three async callables in order,
ask the Controller "should we continue", track depth, and emit progress
events. It does NOT know about ramen, Reddit, or any Plus One specifics.

Domain agents adapt themselves to the three phase signatures::

    ProducerFn[Cand] = (AgentContext) -> PhaseResult[list[Cand]]
    JoinerFn[Cand, Joined] = (list[Cand], AgentContext) -> PhaseResult[list[Joined]]
    ControllerFn[Joined] = (list[Joined], AgentContext) -> PhaseResult[Decision]

A ``CycleResult`` packages the final joined items + final decision + the
full trace, so the caller can both render the answer and inspect what
happened.

Stop conditions (in order):
  1. Producer returned empty -> abort with reason
  2. Controller says ``should_continue=False`` -> normal exit
  3. ``ctx.depth >= ctx.max_depth`` -> hard cap exit
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Protocol

import structlog

from plus_one.core.agents.framework.errors import CycleAbortedError
from plus_one.core.agents.framework.types import AgentContext, Decision, PhaseResult

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = structlog.get_logger()


class ProgressEvent(Protocol):
    """Marker for events emitted during the cycle."""

    name: str
    depth: int


class _Event:
    """Generic, lightweight progress event."""

    __slots__ = ("data", "depth", "name")

    def __init__(self, name: str, depth: int, **data: object) -> None:
        self.name = name
        self.depth = depth
        self.data = data

    def __repr__(self) -> str:
        return f"<Event {self.name} depth={self.depth} data={self.data}>"


class CycleResult[TJoined]:
    """Final output of a cycle run."""

    __slots__ = ("ctx", "decision", "items", "trace")

    def __init__(
        self,
        items: list[TJoined],
        decision: Decision,
        ctx: AgentContext,
        trace: list[_Event],
    ) -> None:
        self.items = items
        self.decision = decision
        self.ctx = ctx
        self.trace = trace


type ProducerFn[TCand] = Callable[[AgentContext], Awaitable[PhaseResult[list[TCand]]]]
type JoinerFn[TCand, TJoined] = Callable[
    [list[TCand], AgentContext], Awaitable[PhaseResult[list[TJoined]]]
]
type ControllerFn[TJoined] = Callable[
    [list[TJoined], AgentContext], Awaitable[PhaseResult[Decision]]
]


async def run_cycle[TCand, TJoined](
    *,
    producer: ProducerFn[TCand],
    joiner: JoinerFn[TCand, TJoined],
    controller: ControllerFn[TJoined],
    ctx: AgentContext,
) -> CycleResult[TJoined]:
    """Run the Producer -> Joiner -> Controller loop until it terminates.

    Raises:
        CycleAbortedError: If Producer returns empty, with a descriptive reason.
                      Use this to distinguish "no useful result" from
                      "result is empty by design".
    """
    trace: list[_Event] = []
    accumulated: list[TJoined] = []
    last_decision = Decision(should_continue=False, reasoning="cycle never ran")

    while True:
        trace.append(_Event("iteration_start", ctx.depth))

        producer_result = await producer(ctx)
        candidates = producer_result.payload
        trace.append(
            _Event("producer", ctx.depth, n_candidates=len(candidates), notes=producer_result.notes)
        )

        if not candidates:
            # Empty Producer means "nothing more to look at, full stop".
            # Distinct from Controller saying "we have enough".
            logger.info("cycle_aborted_empty_producer", depth=ctx.depth)
            raise CycleAbortedError(f"producer returned no candidates at depth={ctx.depth}")

        joiner_result = await joiner(candidates, ctx)
        joined_items = joiner_result.payload
        accumulated.extend(joined_items)
        trace.append(
            _Event(
                "joiner",
                ctx.depth,
                n_in=len(candidates),
                n_out=len(joined_items),
                notes=joiner_result.notes,
            )
        )

        controller_result = await controller(accumulated, ctx)
        last_decision = controller_result.payload
        trace.append(
            _Event(
                "controller",
                ctx.depth,
                should_continue=last_decision.should_continue,
                reasoning=last_decision.reasoning,
            )
        )

        # Update running summary for next Producer iteration
        ctx.summary = last_decision.summary or ctx.summary

        if not last_decision.should_continue:
            logger.info(
                "cycle_done_controller_stop",
                depth=ctx.depth,
                reason=last_decision.reasoning,
            )
            break

        ctx.depth += 1
        if ctx.at_depth_cap():
            logger.info("cycle_done_depth_cap", depth=ctx.depth)
            trace.append(_Event("depth_cap_hit", ctx.depth))
            break

    return CycleResult(items=accumulated, decision=last_decision, ctx=ctx, trace=trace)


async def stream_cycle[TCand, TJoined](
    *,
    producer: ProducerFn[TCand],
    joiner: JoinerFn[TCand, TJoined],
    controller: ControllerFn[TJoined],
    ctx: AgentContext,
) -> AsyncIterator[_Event]:
    """Generator variant — yield each progress event as it happens.

    Useful for the SSE endpoint that wants to push live progress to the
    frontend without waiting for the full cycle to finish. The final event
    yielded is ``cycle_complete``; callers should collect items off the
    Joiner events themselves if needed.

    NOTE: this is a thin re-implementation rather than a wrapper around
    :func:`run_cycle` because Python doesn't let us yield from one async
    fn into another's stream cleanly without a queue.
    """
    accumulated: list[TJoined] = []

    while True:
        yield _Event("iteration_start", ctx.depth)

        producer_result = await producer(ctx)
        candidates = producer_result.payload
        yield _Event(
            "producer",
            ctx.depth,
            n_candidates=len(candidates),
            notes=producer_result.notes,
        )

        if not candidates:
            yield _Event("cycle_aborted", ctx.depth, reason="empty producer")
            raise CycleAbortedError(f"producer returned no candidates at depth={ctx.depth}")

        joiner_result = await joiner(candidates, ctx)
        joined_items = joiner_result.payload
        accumulated.extend(joined_items)
        yield _Event(
            "joiner",
            ctx.depth,
            n_in=len(candidates),
            n_out=len(joined_items),
            notes=joiner_result.notes,
        )

        controller_result = await controller(accumulated, ctx)
        decision = controller_result.payload
        yield _Event(
            "controller",
            ctx.depth,
            should_continue=decision.should_continue,
            reasoning=decision.reasoning,
        )

        ctx.summary = decision.summary or ctx.summary

        if not decision.should_continue:
            yield _Event("cycle_complete", ctx.depth, reason="controller stop")
            return

        ctx.depth += 1
        if ctx.at_depth_cap():
            yield _Event("cycle_complete", ctx.depth, reason="depth cap")
            return
