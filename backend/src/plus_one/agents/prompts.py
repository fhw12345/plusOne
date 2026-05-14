"""Prompt loading helper.

Prompts live as plain markdown alongside the agents so they're versioned
in git, diffable in PRs, and reviewable without leaving the editor. The
naming convention is ``prompts/<role>/v<N>.md`` so a future A/B comparison
between v1 and v2 of any prompt is just a config flip.
"""

from __future__ import annotations

from pathlib import Path

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def load_prompt(role: str, version: str) -> str:
    """Read ``prompts/<role>/<version>.md``. Raises FileNotFoundError if missing."""
    path = _PROMPTS_DIR / role / f"{version}.md"
    return path.read_text(encoding="utf-8")
