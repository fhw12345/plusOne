"""Tests for Decision / AgentContext / PhaseResult."""

from __future__ import annotations

import pytest

from plus_one.core.agents.framework.types import AgentContext, Decision, PhaseResult


@pytest.mark.unit
def test_agent_context_defaults() -> None:
    ctx = AgentContext(query="hello")
    assert ctx.depth == 0
    assert ctx.max_depth == 4
    assert ctx.summary == ""
    assert ctx.scratch == {}
    assert not ctx.at_depth_cap()


@pytest.mark.unit
def test_agent_context_at_depth_cap() -> None:
    ctx = AgentContext(query="x", max_depth=3)
    ctx.depth = 2
    assert not ctx.at_depth_cap()
    ctx.depth = 3
    assert ctx.at_depth_cap()
    ctx.depth = 4
    assert ctx.at_depth_cap()


@pytest.mark.unit
def test_decision_defaults() -> None:
    d = Decision(should_continue=True)
    assert d.should_continue is True
    assert d.reasoning == ""
    assert d.summary == ""
    assert d.next_focus is None


@pytest.mark.unit
def test_phase_result_carries_payload() -> None:
    r: PhaseResult[list[int]] = PhaseResult(payload=[1, 2, 3], notes="hello")
    assert r.payload == [1, 2, 3]
    assert r.notes == "hello"


@pytest.mark.unit
def test_max_depth_must_be_positive() -> None:
    with pytest.raises(ValueError, match="greater than or equal to 1"):
        AgentContext(query="x", max_depth=0)
