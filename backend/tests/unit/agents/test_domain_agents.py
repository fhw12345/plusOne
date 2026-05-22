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
                "classification_en": "local_gem",
                "classification_zh": "local_gem",
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

    assert len(result.payload.items) == 1
    item = result.payload.items[0]
    assert item.classification == "local_gem"
    assert item.classification_en == "local_gem"
    assert item.classification_zh == "local_gem"
    assert item.confidence == 0.85
    # Per-lang agreement → divergence_score is exactly 0.0 (Python-side
    # overwrite of whatever the LLM emitted for the field).
    assert item.divergence_score == 0.0
    assert len(item.evidence) == 1
    assert isinstance(item.evidence[0], Evidence)


@pytest.mark.unit
async def test_joiner_computes_divergence_for_disagreement_case(
    mock_llm: MockLLMProvider,
) -> None:
    """LLM may emit a bogus divergence_score; Python-side recompute wins."""
    cand = Candidate(name="Menya Itto", rationale="r")
    output = {
        "items": [
            {
                "candidate": cand.model_dump(),
                "classification": "local_gem",
                "classification_en": "local_gem",
                "classification_zh": "tourist_trap",
                "confidence": 0.7,
                "evidence": [],
                "summary": "EN raves, ZH says trap",
                # Deliberately wrong — must be overwritten to 1.0.
                "divergence_score": 0.1,
            }
        ]
    }
    mock_llm.queue_response(
        role="joiner_agent",
        text=json.dumps(output),
        parsed_data=output,
    )

    result = await joiner([cand], AgentContext(query="Tokyo"))
    assert len(result.payload.items) == 1
    item = result.payload.items[0]
    assert item.classification_en == "local_gem"
    assert item.classification_zh == "tourist_trap"
    assert item.divergence_score == 1.0


@pytest.mark.unit
async def test_joiner_handles_null_per_language_classification(
    mock_llm: MockLLMProvider,
) -> None:
    """When one side has no per-language signal the LLM must emit null;
    divergence_score must stay 0.0 because the disagreement gate requires
    both sides non-null."""
    cand = Candidate(name="Menya Itto", rationale="r")
    output = {
        "items": [
            {
                "candidate": cand.model_dump(),
                "classification": "local_gem",
                "classification_en": "local_gem",
                "classification_zh": None,
                "confidence": 0.6,
                "evidence": [],
                "summary": "no xhs hits",
            }
        ]
    }
    mock_llm.queue_response(
        role="joiner_agent",
        text=json.dumps(output),
        parsed_data=output,
    )

    result = await joiner([cand], AgentContext(query="Tokyo"))
    assert len(result.payload.items) == 1
    item = result.payload.items[0]
    assert item.classification_en == "local_gem"
    assert item.classification_zh is None
    assert item.divergence_score == 0.0


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
    assert result.payload.items == []


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
    assert len(result.payload.items) == 1
    # Restored from the original Candidate
    assert result.payload.items[0].candidate.area == "Shinkoiwa"
    assert result.payload.items[0].candidate.style == "tonkotsu"


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
    assert len(result.payload.items) == 1
    assert result.payload.items[0].candidate.name == "Menya Itto"
    assert "dropped_unknown=1" in result.notes


# === Joiner v3 (batch-2p + batch-2q) ====================================


@pytest.mark.unit
async def test_joiner_v3_prompt_loads_without_unbalanced_braces(
    mock_llm: MockLLMProvider,
) -> None:
    """v3.md must parse via the load_prompt path with the two `.replace`
    placeholders, including the literal JSON braces in the output-format
    block (the joiner uses ``.replace`` precisely so those stay safe).
    """
    cand = Candidate(name="Menya Itto", rationale="r")
    mock_llm.queue_response(
        role="joiner_agent",
        text='{"items": [], "tl_dr": null}',
        parsed_data={"items": [], "tl_dr": None},
    )
    result = await joiner([cand], AgentContext(query="Tokyo"))
    assert result.payload.items == []
    assert result.payload.tl_dr is None


@pytest.mark.unit
async def test_joiner_v3_passes_through_match_scores(
    mock_llm: MockLLMProvider,
) -> None:
    """LLM emits a fully-populated match_scores map keyed by the trip's
    party; joiner accepts it unchanged (after the clamp/fill pass)."""
    import uuid as _uuid

    from plus_one.core.agents.framework.types import (
        CompanionForContext,
        UserProfileForContext,
    )

    user_id = _uuid.uuid4()
    alice_id = _uuid.uuid4()
    cand = Candidate(name="Menya Itto", rationale="r")
    output = {
        "tl_dr": "tokyo's a place for counters not chains. nishikoiwa's the move.",
        "items": [
            {
                "candidate": cand.model_dump(),
                "classification": "local_gem",
                "confidence": 0.8,
                "evidence": [],
                "summary": "ok",
                "match_scores": {str(user_id): 0.8, str(alice_id): 0.3},
            }
        ],
    }
    mock_llm.queue_response(role="joiner_agent", text="{}", parsed_data=output)
    ctx = AgentContext(
        query="Tokyo",
        user_profile=UserProfileForContext(id=user_id, loves=("ramen",)),
        selected_companions=[CompanionForContext(id=alice_id, name="alice")],
    )
    result = await joiner([cand], ctx)
    item = result.payload.items[0]
    assert item.match_scores is not None
    assert item.match_scores[user_id] == 0.8
    assert item.match_scores[alice_id] == 0.3
    assert result.payload.tl_dr is not None
    assert result.payload.tl_dr.startswith("tokyo")


@pytest.mark.unit
async def test_joiner_v3_drops_hallucinated_score_keys_and_fills_missing(
    mock_llm: MockLLMProvider,
) -> None:
    """LLM hallucinates a UUID + omits a real one + emits out-of-range. We
    drop the hallucination, fill the missing key with 0.5, and clamp."""
    import uuid as _uuid

    from plus_one.core.agents.framework.types import (
        CompanionForContext,
        UserProfileForContext,
    )

    user_id = _uuid.uuid4()
    alice_id = _uuid.uuid4()
    bogus_id = _uuid.uuid4()
    cand = Candidate(name="Menya Itto", rationale="r")
    output = {
        "items": [
            {
                "candidate": cand.model_dump(),
                "classification": "local_gem",
                "confidence": 0.8,
                "evidence": [],
                "summary": "ok",
                # user gets out-of-range, alice is missing, bogus is hallucinated.
                "match_scores": {str(user_id): 1.7, str(bogus_id): 0.5},
            }
        ]
    }
    mock_llm.queue_response(role="joiner_agent", text="{}", parsed_data=output)
    ctx = AgentContext(
        query="Tokyo",
        user_profile=UserProfileForContext(id=user_id),
        selected_companions=[CompanionForContext(id=alice_id, name="alice")],
    )
    result = await joiner([cand], ctx)
    item = result.payload.items[0]
    assert item.match_scores is not None
    assert set(item.match_scores.keys()) == {user_id, alice_id}
    assert item.match_scores[user_id] == 1.0  # clamped
    assert item.match_scores[alice_id] == 0.5  # filled default


@pytest.mark.unit
async def test_joiner_v3_no_party_identity_skips_match_scores(
    mock_llm: MockLLMProvider,
) -> None:
    """When ctx has no user/companion ids (unit-test style), match_scores
    must coerce to None — there's nothing to key against."""
    cand = Candidate(name="Menya Itto", rationale="r")
    output = {
        "items": [
            {
                "candidate": cand.model_dump(),
                "classification": "local_gem",
                "confidence": 0.8,
                "evidence": [],
                "summary": "ok",
                "match_scores": {"00000000-0000-4000-8000-000000000001": 0.7},
            }
        ]
    }
    mock_llm.queue_response(role="joiner_agent", text="{}", parsed_data=output)
    result = await joiner([cand], AgentContext(query="Tokyo"))
    item = result.payload.items[0]
    assert item.match_scores is None


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
