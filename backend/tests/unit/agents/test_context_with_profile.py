"""Tests for the new AgentContext profile fields + render_preferences_section.

These verify (a) backward compatibility — AgentContext(query=...) without
the new kwargs still works, and (b) the prompt-section helper produces
the exact strings the PRD §7 calls for.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from plus_one.agents.preferences import render_preferences_section
from plus_one.agents.producer import _build_system_prompt, producer
from plus_one.core.agents.framework.types import (
    AgentContext,
    CompanionForContext,
    UserProfileForContext,
)

if TYPE_CHECKING:
    from plus_one.core.llm.testing import MockLLMProvider


@pytest.mark.unit
def test_agent_context_backward_compatible_no_profile_kwargs() -> None:
    """Existing call sites that construct AgentContext(query="x") still work."""
    ctx = AgentContext(query="x")
    assert ctx.user_profile.loves == ()
    assert ctx.user_profile.hates == ()
    assert ctx.selected_companions == []


@pytest.mark.unit
def test_user_profile_and_companion_for_context_are_frozen() -> None:
    """Frozen models — read-only signal, never mutated by phases."""
    from pydantic import ValidationError

    profile = UserProfileForContext(loves=("ramen",), hates=())
    companion = CompanionForContext(name="Anna", loves=("matcha",))
    with pytest.raises(ValidationError):
        profile.loves = ("changed",)  # type: ignore[misc]
    with pytest.raises(ValidationError):
        companion.name = "other"  # type: ignore[misc]


@pytest.mark.unit
def test_render_preferences_empty_profile_and_companions_returns_marker() -> None:
    """Empty input → literal '(none specified)' marker (PRD §7)."""
    out = render_preferences_section(UserProfileForContext(), [])
    assert out == "(none specified)"


@pytest.mark.unit
def test_render_preferences_only_companions_with_no_loves_or_hates_returns_marker() -> None:
    """Companions with no loves/hates contribute nothing → marker."""
    out = render_preferences_section(
        UserProfileForContext(),
        [CompanionForContext(name="Anna"), CompanionForContext(name="Bob")],
    )
    assert out == "(none specified)"


@pytest.mark.unit
def test_render_preferences_matches_prd_example() -> None:
    """Verbatim PRD §7 example block."""
    profile = UserProfileForContext(loves=("ramen", "kissaten"), hates=("long queues",))
    companions = [CompanionForContext(name="Anna", loves=("matcha",), hates=("seafood",))]
    expected = (
        "User preferences:\n"
        "  loves: ramen, kissaten\n"
        "  hates: long queues\n"
        "\n"
        "Companion preferences:\n"
        "  Anna: loves matcha; hates seafood"
    )
    assert render_preferences_section(profile, companions) == expected


@pytest.mark.unit
def test_render_preferences_profile_only() -> None:
    profile = UserProfileForContext(loves=("ramen",))
    out = render_preferences_section(profile, [])
    assert out == "User preferences:\n  loves: ramen"


@pytest.mark.unit
def test_render_preferences_hates_only_for_companion() -> None:
    out = render_preferences_section(
        UserProfileForContext(),
        [CompanionForContext(name="Bob", hates=("crowds",))],
    )
    assert out == "Companion preferences:\n  Bob: hates crowds"


@pytest.mark.unit
def test_producer_prompt_includes_populated_preferences_section() -> None:
    """The producer system prompt embeds the rendered preferences block."""
    ctx = AgentContext(
        query="Tokyo ramen",
        user_profile=UserProfileForContext(loves=("ramen",), hates=("queues",)),
        selected_companions=[CompanionForContext(name="Anna", loves=("matcha",))],
    )
    system = _build_system_prompt(ctx, skill_bodies=[])
    assert "## User and companion preferences" in system
    assert "User preferences:" in system
    assert "loves: ramen" in system
    assert "Anna: loves matcha" in system


@pytest.mark.unit
def test_producer_prompt_empty_profile_contains_none_specified_marker() -> None:
    """No profile + no companions → section present, content is the marker."""
    ctx = AgentContext(query="Tokyo")
    system = _build_system_prompt(ctx, skill_bodies=[])
    assert "## User and companion preferences" in system
    assert "(none specified)" in system


@pytest.mark.unit
async def test_producer_run_uses_profile_kwargs(mock_llm: MockLLMProvider) -> None:
    """End-to-end run through producer() honors the new ctx fields."""
    payload = {"candidates": []}
    mock_llm.queue_response(
        role="producer_agent", text=json.dumps(payload), parsed_data=payload
    )
    ctx = AgentContext(
        query="Tokyo",
        user_profile=UserProfileForContext(loves=("ramen",)),
    )
    result = await producer(ctx)
    assert result.payload == []
    # The system prompt actually sent to the mock should include our loves.
    call = mock_llm.calls_for_role("producer_agent")[-1]
    assert "loves: ramen" in call["system"]
