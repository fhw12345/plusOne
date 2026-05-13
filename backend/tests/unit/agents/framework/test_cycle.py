"""Tests for the cycle main loop."""

from __future__ import annotations

import asyncio

import pytest

from plus_one.core.agents.framework.cycle import run_cycle, stream_cycle
from plus_one.core.agents.framework.errors import CycleAbortedError
from plus_one.core.agents.framework.types import AgentContext, Decision, PhaseResult

# === Test doubles =========================================================


class _Producer:
    """Records every call; returns a configurable sequence of outputs."""

    def __init__(self, outputs: list[list[str]]) -> None:
        self.outputs = outputs
        self.call_count = 0

    async def __call__(self, ctx: AgentContext) -> PhaseResult[list[str]]:
        i = min(self.call_count, len(self.outputs) - 1)
        self.call_count += 1
        return PhaseResult(payload=list(self.outputs[i]), notes=f"depth={ctx.depth}")


class _Joiner:
    """Maps each candidate to ``"joined:<cand>"``."""

    def __init__(self) -> None:
        self.call_count = 0

    async def __call__(self, candidates: list[str], ctx: AgentContext) -> PhaseResult[list[str]]:
        self.call_count += 1
        return PhaseResult(payload=[f"joined:{c}" for c in candidates])


class _Controller:
    """Returns the next configured decision in ``decisions``."""

    def __init__(self, decisions: list[Decision]) -> None:
        self.decisions = decisions
        self.call_count = 0

    async def __call__(self, items: list[str], ctx: AgentContext) -> PhaseResult[Decision]:
        decision = self.decisions[min(self.call_count, len(self.decisions) - 1)]
        self.call_count += 1
        return PhaseResult(payload=decision)


class _SlowProducer:
    """Producer that sleeps longer than the test's phase_timeout."""

    async def __call__(self, ctx: AgentContext) -> PhaseResult[list[str]]:
        await asyncio.sleep(1.0)
        return PhaseResult(payload=["unreachable"])


# === run_cycle ============================================================


@pytest.mark.unit
async def test_run_cycle_single_iteration() -> None:
    producer = _Producer([["a", "b"]])
    joiner = _Joiner()
    controller = _Controller([Decision(should_continue=False, reasoning="enough", summary="s1")])

    result = await run_cycle(
        producer=producer,
        joiner=joiner,
        controller=controller,
        ctx=AgentContext(query="q"),
    )

    assert result.items == ["joined:a", "joined:b"]
    assert result.decision.should_continue is False
    assert result.decision.reasoning == "enough"
    assert result.aborted_reason is None
    assert producer.call_count == 1
    assert joiner.call_count == 1
    assert controller.call_count == 1


@pytest.mark.unit
async def test_run_cycle_multiple_iterations_accumulates() -> None:
    producer = _Producer([["a"], ["b"], ["c"]])
    joiner = _Joiner()
    controller = _Controller(
        [
            Decision(should_continue=True, reasoning="more"),
            Decision(should_continue=True, reasoning="more"),
            Decision(should_continue=False, reasoning="done"),
        ]
    )

    result = await run_cycle(
        producer=producer,
        joiner=joiner,
        controller=controller,
        ctx=AgentContext(query="q", max_depth=10),
    )

    assert result.items == ["joined:a", "joined:b", "joined:c"]
    assert producer.call_count == 3


@pytest.mark.unit
async def test_run_cycle_stops_at_depth_cap() -> None:
    producer = _Producer([["a"]])
    joiner = _Joiner()
    # Always says continue — only the depth cap can stop it.
    controller = _Controller([Decision(should_continue=True, reasoning="more")])

    await run_cycle(
        producer=producer,
        joiner=joiner,
        controller=controller,
        ctx=AgentContext(query="q", max_depth=2),
    )

    # max_depth=2 means: iter 0 (depth -> 1), iter 1 (depth -> 2 -> cap hit, stop).
    assert producer.call_count == 2


@pytest.mark.unit
async def test_run_cycle_aborts_on_empty_producer() -> None:
    producer = _Producer([[]])
    joiner = _Joiner()
    controller = _Controller([Decision(should_continue=False)])

    with pytest.raises(CycleAbortedError, match="empty producer"):
        await run_cycle(
            producer=producer,
            joiner=joiner,
            controller=controller,
            ctx=AgentContext(query="q"),
        )


@pytest.mark.unit
async def test_run_cycle_aborts_on_phase_timeout() -> None:
    producer = _SlowProducer()
    joiner = _Joiner()
    controller = _Controller([Decision(should_continue=False)])

    with pytest.raises(CycleAbortedError, match="producer timeout"):
        await run_cycle(
            producer=producer,
            joiner=joiner,
            controller=controller,
            ctx=AgentContext(query="q", phase_timeout=0.05),
        )


@pytest.mark.unit
async def test_controller_summary_propagates_to_context() -> None:
    producer = _Producer([["a"]])
    joiner = _Joiner()
    controller = _Controller([Decision(should_continue=False, summary="this is the new summary")])

    ctx = AgentContext(query="q")
    await run_cycle(producer=producer, joiner=joiner, controller=controller, ctx=ctx)
    assert ctx.summary == "this is the new summary"


@pytest.mark.unit
async def test_trace_records_each_phase() -> None:
    producer = _Producer([["a"]])
    joiner = _Joiner()
    controller = _Controller([Decision(should_continue=False)])

    result = await run_cycle(
        producer=producer,
        joiner=joiner,
        controller=controller,
        ctx=AgentContext(query="q"),
    )
    names = [e.name for e in result.trace]
    assert names == ["iteration_start", "producer", "joiner", "controller", "cycle_complete"]


@pytest.mark.unit
async def test_run_cycle_cancellation_propagates() -> None:
    """Outer cancel mid-cycle re-raises CancelledError after best-effort logging."""
    producer = _SlowProducer()  # sleeps 1s
    joiner = _Joiner()
    controller = _Controller([Decision(should_continue=False)])

    async def runner() -> None:
        await run_cycle(
            producer=producer,
            joiner=joiner,
            controller=controller,
            ctx=AgentContext(query="q"),
        )

    task = asyncio.create_task(runner())
    await asyncio.sleep(0.01)  # let it enter producer
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


# === stream_cycle =========================================================


@pytest.mark.unit
async def test_stream_cycle_emits_events_in_order() -> None:
    producer = _Producer([["a"]])
    joiner = _Joiner()
    controller = _Controller([Decision(should_continue=False)])

    events = [
        e
        async for e in stream_cycle(
            producer=producer,
            joiner=joiner,
            controller=controller,
            ctx=AgentContext(query="q"),
        )
    ]
    names = [e.name for e in events]
    assert names == ["iteration_start", "producer", "joiner", "controller", "cycle_complete"]


@pytest.mark.unit
async def test_stream_cycle_yields_aborted_event_does_not_raise() -> None:
    """Per the new contract: stream_cycle yields cycle_aborted then ends.

    No CycleAbortedError is raised into the consumer's async-for loop —
    that's run_cycle's contract. This makes SSE wiring simpler.
    """
    producer = _Producer([[]])
    joiner = _Joiner()
    controller = _Controller([Decision(should_continue=False)])

    events = [
        e
        async for e in stream_cycle(
            producer=producer,
            joiner=joiner,
            controller=controller,
            ctx=AgentContext(query="q"),
        )
    ]
    names = [e.name for e in events]
    assert names == ["iteration_start", "producer", "cycle_aborted"]
    assert events[-1].data["reason"] == "empty producer"


@pytest.mark.unit
async def test_stream_cycle_and_run_cycle_use_same_event_names_for_depth_cap() -> None:
    """Reviewer F2 / Q10: both code paths must agree on the depth-cap event name."""
    producer1 = _Producer([["a"]])
    joiner1 = _Joiner()
    controller1 = _Controller([Decision(should_continue=True)])

    run_result = await run_cycle(
        producer=producer1,
        joiner=joiner1,
        controller=controller1,
        ctx=AgentContext(query="q", max_depth=1),
    )
    run_names = [e.name for e in run_result.trace]

    producer2 = _Producer([["a"]])
    joiner2 = _Joiner()
    controller2 = _Controller([Decision(should_continue=True)])
    stream_events = [
        e
        async for e in stream_cycle(
            producer=producer2,
            joiner=joiner2,
            controller=controller2,
            ctx=AgentContext(query="q", max_depth=1),
        )
    ]
    stream_names = [e.name for e in stream_events]

    assert run_names == stream_names
    assert run_names[-1] == "cycle_complete"
    assert stream_events[-1].data["reason"] == "depth cap"
