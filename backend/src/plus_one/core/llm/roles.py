"""Per-role model assignment for Plus One.

Every LLM call in this codebase declares its *role*, not a model name.
A role is mapped to a concrete Maestro model id via env vars (with defaults
that match the product's reasoning needs). This means we can:

  - Re-balance cost vs quality without code changes (just env)
  - Use cross-vendor diversity where it matters (e.g. disagreement detector
    uses a non-Claude judge so it isn't self-correlated)
  - Run A/B comparisons by swapping one role's model

Roles are deliberately Plus One-specific (not generic ``simple_chat``-style)
so each is named after the *job it does*.
"""

from __future__ import annotations

import os
from typing import Final

# ---------------------------------------------------------------------------
# Role -> default Maestro model
# ---------------------------------------------------------------------------
#
# Choices rationale:
#
# - **producer_agent**  — generates candidate places/regions; needs broad world
#   knowledge + creative recall. Claude Opus 4.7 (long context).
# - **joiner_agent**    — cross-validates candidates against fetched sources;
#   reasoning-heavy + structured output. Claude Opus 4.7.
# - **controller_agent** — rule-first with LLM fallback on ambiguous "keep
#   looping?" decisions. Lighter weight is fine; uses Claude Haiku 4.5.
# - **skill_router**    — embedding/keyword-style selection of relevant skills
#   for a query. Cheap, fast. Claude Haiku 4.5.
# - **disagreement_detector** — judges whether Chinese-source claim X and
#   English-source claim Y are about the same entity & whether they conflict.
#   Cross-vendor (Gemini) to avoid self-correlated reasoning with Producer/Joiner.
# - **eval_judge**      — pairwise comparison of our report vs baseline for
#   the eval suite. Cross-vendor (GPT-5.5) — different family than the
#   producer so we don't grade ourselves.
# - **bullshit_filter** — scores Reddit/XHS posts for sponsored-content signal.
#   GPT-5.5 (good at structured extraction).
# - **conversational**  — handles follow-up refinement chat after report
#   generation. Claude Haiku 4.5 (fast, cheap).
# - **summarizer**      — compresses chain-of-thought / long contexts.
#   Gemini Flash (cheap + long-context).
# - **fallback**        — when role is unknown. Maps to conversational.

ROLES: Final[dict[str, str]] = {
    "producer_agent": os.getenv("MODEL_PRODUCER_AGENT", "claude-opus-4.7"),
    "joiner_agent": os.getenv("MODEL_JOINER_AGENT", "claude-opus-4.7"),
    "controller_agent": os.getenv("MODEL_CONTROLLER_AGENT", "claude-haiku-4.5"),
    "skill_router": os.getenv("MODEL_SKILL_ROUTER", "claude-haiku-4.5"),
    "disagreement_detector": os.getenv(
        "MODEL_DISAGREEMENT_DETECTOR", "gemini-3.1-pro-preview"
    ),
    "eval_judge": os.getenv("MODEL_EVAL_JUDGE", "gpt-5.5"),
    "bullshit_filter": os.getenv("MODEL_BULLSHIT_FILTER", "gpt-5.5"),
    "conversational": os.getenv("MODEL_CONVERSATIONAL", "claude-haiku-4.5"),
    "summarizer": os.getenv("MODEL_SUMMARIZER", "gemini-3-flash-preview"),
}

FALLBACK_ROLE: Final[str] = "conversational"


def resolve_model(role: str) -> str:
    """Return the configured Maestro model id for ``role``.

    Unknown roles fall back to the ``conversational`` role's model.
    """
    if role in ROLES:
        return ROLES[role]
    return ROLES[FALLBACK_ROLE]


def list_roles() -> list[str]:
    """Return all registered role names."""
    return list(ROLES.keys())
