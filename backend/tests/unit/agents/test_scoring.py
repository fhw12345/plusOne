"""Unit tests for ``plus_one.agents._scoring`` (batch-2p)."""

from __future__ import annotations

import uuid

import pytest

from plus_one.agents._scoring import render_person_roster, validate_match_scores
from plus_one.core.agents.framework.types import CompanionForContext, UserProfileForContext


@pytest.mark.unit
def test_render_person_roster_solo_user_emits_one_line() -> None:
    user_id = uuid.uuid4()
    profile = UserProfileForContext(id=user_id, loves=("ramen",), hates=("seafood",))
    out = render_person_roster(profile, [])
    assert out == f"- person_id={user_id} name=you loves=[ramen] hates=[seafood]"


@pytest.mark.unit
def test_render_person_roster_empty_profile_no_id_uses_unknown_marker() -> None:
    """Even with no id and empty loves/hates we still emit the user line.

    Joiner prompt expects the roster to always have at least one entry —
    an empty block would let the LLM rationalise its way out of emitting
    match_scores.
    """
    out = render_person_roster(UserProfileForContext(), [])
    assert out == "- person_id=unknown name=you loves=[] hates=[]"


@pytest.mark.unit
def test_render_person_roster_matches_prd_example() -> None:
    """Mirror of batch-2p PRD §4.1 example block (one user + two companions)."""
    user_id = uuid.uuid4()
    alice_id = uuid.uuid4()
    bob_id = uuid.uuid4()
    profile = UserProfileForContext(id=user_id, loves=("ramen",), hates=("seafood",))
    companions = [
        CompanionForContext(id=alice_id, name="alice", loves=("spicy food", "seafood")),
        CompanionForContext(id=bob_id, name="bob"),
    ]
    out = render_person_roster(profile, companions)
    expected = (
        f"- person_id={user_id} name=you loves=[ramen] hates=[seafood]\n"
        f"- person_id={alice_id} name=alice loves=[spicy food, seafood] hates=[]\n"
        f"- person_id={bob_id} name=bob loves=[] hates=[]"
    )
    assert out == expected


@pytest.mark.unit
def test_validate_match_scores_drops_unknown_keys_and_fills_missing() -> None:
    user_id = uuid.uuid4()
    alice_id = uuid.uuid4()
    bogus = uuid.uuid4()
    allowed = {user_id, alice_id}
    scores = {user_id: 0.8, bogus: 0.9}
    out = validate_match_scores(scores, allowed)
    assert out is not None
    assert set(out.keys()) == allowed
    assert out[user_id] == 0.8
    # Missing alice filled with neutral default 0.5.
    assert out[alice_id] == 0.5


@pytest.mark.unit
def test_validate_match_scores_clamps_out_of_range_values() -> None:
    user_id = uuid.uuid4()
    out = validate_match_scores({user_id: 1.7}, {user_id})
    assert out is not None
    assert out[user_id] == 1.0
    out2 = validate_match_scores({user_id: -0.4}, {user_id})
    assert out2 is not None
    assert out2[user_id] == 0.0


@pytest.mark.unit
def test_validate_match_scores_accepts_string_keys() -> None:
    """LLM may emit string UUID keys (JSON has no UUID type)."""
    user_id = uuid.uuid4()
    out = validate_match_scores({str(user_id): 0.6}, {user_id})
    assert out is not None
    assert out[user_id] == 0.6


@pytest.mark.unit
def test_validate_match_scores_returns_none_for_empty_allowed_set() -> None:
    """No party identity → no possible scores → None."""
    user_id = uuid.uuid4()
    assert validate_match_scores({user_id: 0.7}, set()) is None
    assert validate_match_scores(None, set()) is None


@pytest.mark.unit
def test_validate_match_scores_with_none_input_fills_defaults() -> None:
    """LLM omitted match_scores entirely → fill every allowed id with 0.5."""
    user_id = uuid.uuid4()
    alice_id = uuid.uuid4()
    out = validate_match_scores(None, {user_id, alice_id})
    assert out == {user_id: 0.5, alice_id: 0.5}


@pytest.mark.unit
def test_validate_match_scores_ignores_non_numeric_values() -> None:
    user_id = uuid.uuid4()
    alice_id = uuid.uuid4()
    out = validate_match_scores({user_id: "not-a-number", alice_id: 0.4}, {user_id, alice_id})
    assert out is not None
    # user_id falls back to the neutral default since the value couldn't parse.
    assert out[user_id] == 0.5
    assert out[alice_id] == 0.4
