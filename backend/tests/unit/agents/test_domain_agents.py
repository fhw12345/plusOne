"""Tests for the domain agents (Producer / Joiner / Controller).

These exercise the agents through the framework's protocols using the
mock_llm fixture. No real LLM, no real DB, no real network.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from plus_one.agents.controller import controller
from plus_one.agents.joiner import JoinedItem, joiner
from plus_one.agents.producer import Candidate, producer
from plus_one.agents.types import Classification, Evidence
from plus_one.core.agents.framework.types import AgentContext

if TYPE_CHECKING:
    from plus_one.core.llm.testing import MockLLMProvider


# === Producer ============================================================


@pytest.mark.unit
async def test_producer_returns_candidates_from_mock_llm(
    mock_llm: MockLLMProvider,
) -> None:
    payload = {
        "candidates": [
            {
                "name": "Menya Itto",
                "area": "Shinkoiwa",
                "style": "tonkotsu",
                "rationale": "Cult favorite among locals",
            },
            {
                "name": "Ichiran Shibuya",
                "area": "Shibuya",
                "style": "tonkotsu chain",
                "rationale": "Likely tourist trap; worth flagging",
            },
        ]
    }
    mock_llm.queue_response(
        role="producer_agent",
        text=json.dumps(payload),
        parsed_data=payload,
    )

    ctx = AgentContext(query="Tokyo tonkotsu ramen")
    result = await producer(ctx)

    assert len(result.payload) == 2
    assert result.payload[0].name == "Menya Itto"
    assert result.payload[1].area == "Shibuya"
    # Notes should mention the routed skills.
    assert "ramen_basics" in result.notes


@pytest.mark.unit
async def test_producer_handles_empty_llm_payload_gracefully(
    mock_llm: MockLLMProvider,
) -> None:
    mock_llm.queue_response(
        role="producer_agent",
        text='{"candidates": []}',
        parsed_data={"candidates": []},
    )
    result = await producer(AgentContext(query="anything"))
    assert result.payload == []


# === Joiner ==============================================================


@pytest.mark.unit
async def test_joiner_classifies_candidates(mock_llm: MockLLMProvider) -> None:
    cand = Candidate(name="Menya Itto", area="Shinkoiwa", style="tonkotsu", rationale="cult fav")
    output = {
        "items": [
            {
                "candidate": cand.model_dump(),
                "classification": "local_gem",
                "confidence": 0.85,
                "evidence": [
                    {
                        "source": "reddit",
                        "url": "https://reddit.com/r/ramen/abc",
                        "snippet": "Best tonkotsu in Tokyo, 90 min wait worth it",
                        "sentiment": 0.9,
                    }
                ],
                "summary": "Strongly recommended by locals.",
            }
        ]
    }
    mock_llm.queue_response(
        role="joiner_agent",
        text=json.dumps(output),
        parsed_data=output,
    )

    result = await joiner([cand], AgentContext(query="Tokyo ramen"))

    assert len(result.payload) == 1
    item = result.payload[0]
    assert item.classification == "local_gem"
    assert item.confidence == 0.85
    assert len(item.evidence) == 1
    assert isinstance(item.evidence[0], Evidence)


@pytest.mark.unit
async def test_joiner_handles_empty_candidate_list(
    mock_llm: MockLLMProvider,
) -> None:
    mock_llm.queue_response(
        role="joiner_agent",
        text='{"items": []}',
        parsed_data={"items": []},
    )
    result = await joiner([], AgentContext(query="x"))
    assert result.payload == []


@pytest.mark.unit
async def test_joiner_repairs_llm_paraphrased_candidate_name(
    mock_llm: MockLLMProvider,
) -> None:
    """Reviewer B3: if the LLM paraphrases the candidate name, we replace
    it with the original Producer Candidate so name/area/style cannot
    silently drift between Producer and the report."""
    cand = Candidate(name="Menya Itto", area="Shinkoiwa", style="tonkotsu", rationale="r")
    output = {
        "items": [
            {
                # LLM "helpfully" added a paren — original was "Menya Itto"
                "candidate": {
                    "name": "Menya Itto",  # case preserved on echo
                    "area": "WRONG",  # LLM mangled area
                    "style": "WRONG",
                    "rationale": "WRONG",
                },
                "classification": "local_gem",
                "confidence": 0.8,
                "evidence": [],
                "summary": "ok",
            }
        ]
    }
    mock_llm.queue_response(
        role="joiner_agent",
        text=json.dumps(output),
        parsed_data=output,
    )
    result = await joiner([cand], AgentContext(query="Tokyo"))
    assert len(result.payload) == 1
    # Restored from the original Candidate
    assert result.payload[0].candidate.area == "Shinkoiwa"
    assert result.payload[0].candidate.style == "tonkotsu"


@pytest.mark.unit
async def test_joiner_drops_hallucinated_candidates(
    mock_llm: MockLLMProvider,
) -> None:
    """LLM returned a candidate name that wasn't in the Producer's list.
    Drop it rather than fabricate a Candidate from thin air."""
    cand = Candidate(name="Menya Itto", rationale="r")
    output = {
        "items": [
            {
                "candidate": {"name": "Menya Itto", "rationale": "r"},
                "classification": "local_gem",
                "confidence": 0.8,
                "evidence": [],
                "summary": "ok",
            },
            {
                "candidate": {"name": "Made-up Place", "rationale": "r"},
                "classification": "local_gem",
                "confidence": 0.9,
                "evidence": [],
                "summary": "fake",
            },
        ]
    }
    mock_llm.queue_response(
        role="joiner_agent",
        text=json.dumps(output),
        parsed_data=output,
    )
    result = await joiner([cand], AgentContext(query="Tokyo"))
    assert len(result.payload) == 1
    assert result.payload[0].candidate.name == "Menya Itto"
    assert "dropped_unknown=1" in result.notes


# === Controller ==========================================================


def _joined(name: str, classification: Classification, confidence: float = 0.7) -> JoinedItem:
    """Tiny helper to build a JoinedItem for controller tests."""
    return JoinedItem(
        candidate=Candidate(name=name, rationale="r"),
        classification=classification,
        confidence=confidence,
    )


@pytest.mark.unit
async def test_controller_rule_stops_when_thresholds_met(
    mock_llm: MockLLMProvider,
) -> None:
    items = [_joined(f"gem_{i}", "local_gem") for i in range(5)] + [
        _joined(f"trap_{i}", "tourist_trap") for i in range(3)
    ]
    ctx = AgentContext(query="x", max_depth=4)

    result = await controller(items, ctx)
    assert result.payload.should_continue is False
    assert "sufficient" in result.payload.reasoning
    # Rule path: no LLM call.
    assert mock_llm.calls_for_role("controller_agent") == []


@pytest.mark.unit
async def test_controller_rule_continues_when_too_many_insufficient(
    mock_llm: MockLLMProvider,
) -> None:
    items = [_joined(f"x_{i}", "insufficient") for i in range(6)] + [_joined("g", "local_gem")]
    ctx = AgentContext(query="x", max_depth=4)

    result = await controller(items, ctx)
    assert result.payload.should_continue is True
    assert "insufficient" in result.payload.reasoning
    assert mock_llm.calls_for_role("controller_agent") == []


@pytest.mark.unit
async def test_controller_falls_back_to_llm_for_ambiguous_state(
    mock_llm: MockLLMProvider,
) -> None:
    """No threshold fires → LLM is asked."""
    items = [
        _joined("g1", "local_gem"),
        _joined("t1", "tourist_trap"),
        _joined("n1", "neutral"),
    ]
    payload = {
        "should_continue": True,
        "reasoning": "Coverage is mixed and confidences are low.",
        "summary": "Found 1 gem, 1 trap, 1 neutral so far.",
    }
    mock_llm.queue_response(
        role="controller_agent",
        text=json.dumps(payload),
        parsed_data=payload,
    )

    ctx = AgentContext(query="x", max_depth=4)
    result = await controller(items, ctx)
    assert result.payload.should_continue is True
    assert result.payload.summary.startswith("Found")
    assert len(mock_llm.calls_for_role("controller_agent")) == 1


@pytest.mark.unit
async def test_controller_does_not_short_circuit_on_depth_alone(
    mock_llm: MockLLMProvider,
) -> None:
    """Reviewer B2: depth-cap is the cycle main loop's job. The Controller
    should make its decision based on coverage, not duplicate the depth
    check (which previously fired off-by-one and discarded a valid round
    of joined results). At depth = max_depth - 1 with ambiguous coverage,
    Controller still asks the LLM."""
    items = [
        _joined("g1", "local_gem"),
        _joined("t1", "tourist_trap"),
    ]
    payload = {
        "should_continue": False,
        "reasoning": "Coverage looks good for this query.",
        "summary": "1 gem, 1 trap.",
    }
    mock_llm.queue_response(
        role="controller_agent",
        text=json.dumps(payload),
        parsed_data=payload,
    )

    ctx = AgentContext(query="x", max_depth=4)
    ctx.depth = 3  # cycle main loop will cap on next iteration
    result = await controller(items, ctx)
    # Now the LLM is consulted (not short-circuited) — coverage is genuinely
    # ambiguous at this depth.
    assert len(mock_llm.calls_for_role("controller_agent")) == 1
    assert result.payload.should_continue is False
