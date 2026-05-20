"""Prompt-section helper: render user + companion preferences for the LLM.

Lives next to the domain agents but stays pure — no LLM call, no DB call,
just `(profile, companions) -> str`. Wired into Producer + Joiner via the
``{preferences}`` placeholder in their v1 prompts.

Design notes (PRD §7):

  * Empty profile + empty companions → returns the literal
    ``"(none specified)"``. This is the deliberate opt-in graceful
    behavior: the prompt structure stays stable across cycles so eval
    baselines don't show per-test churn, but the LLM receives no signal.
  * Joins use ``", "`` for loves/hates and ``"; "`` for the love/hate
    pair within one companion line — keeps the formatting unambiguous
    even when love/hate items themselves contain commas (rare but
    possible: e.g. "fish, except salmon").
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from plus_one.core.agents.framework.types import (
        CompanionForContext,
        UserProfileForContext,
    )


def render_preferences_section(
    profile: UserProfileForContext,
    companions: list[CompanionForContext],
) -> str:
    """Render the prompt block injected into Producer + Joiner system prompts.

    Returns ``"(none specified)"`` when neither the user profile nor any
    companion has loves/hates — keeps the prompt section non-empty so
    the template structure stays stable.
    """
    lines: list[str] = []
    if profile.loves or profile.hates:
        lines.append("User preferences:")
        if profile.loves:
            lines.append(f"  loves: {', '.join(profile.loves)}")
        if profile.hates:
            lines.append(f"  hates: {', '.join(profile.hates)}")

    relevant_companions = [c for c in companions if c.loves or c.hates]
    if relevant_companions:
        if lines:
            lines.append("")
        lines.append("Companion preferences:")
        for c in relevant_companions:
            parts: list[str] = []
            if c.loves:
                parts.append(f"loves {', '.join(c.loves)}")
            if c.hates:
                parts.append(f"hates {', '.join(c.hates)}")
            lines.append(f"  {c.name}: {'; '.join(parts)}")

    if not lines:
        # Explicit no-op marker. Keeps the prompt template structure
        # stable across all users (empty / populated alike); the LLM
        # treats it as "no preference signal."
        return "(none specified)"
    return "\n".join(lines)
