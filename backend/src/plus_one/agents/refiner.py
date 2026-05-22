"""Refiner agent — produces a new joined items list from a previous report + user hint.

This is intentionally simpler than the producer→joiner pipeline: a
refine cycle does not re-fetch evidence from Reddit / XHS / Google
Places. It runs a single LLM call that consumes the previous report's
items + the user's nudge, and emits a new full items list.

Output shape mirrors `JoinedItem` from `agents/joiner.py`, so the same
`Report.content["items"]` shape downstream code already handles works
unchanged for refine reports.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from plus_one.agents.joiner import (
    JoinedItem,  # noqa: TC001 — used as a Pydantic field type at runtime
)
from plus_one.agents.prompts import load_prompt
from plus_one.core.llm import Message
from plus_one.core.llm import factory as llm_factory


class RefinerOutput(BaseModel):
    """Schema enforced on the refiner LLM response.

    `items` is the full new items list (not a delta). `tl_dr` is optional —
    if the joiner v2/v3 prompt has shipped a TL;DR block by the time
    this batch lands, the refiner will emit it too; otherwise it stays
    empty and downstream code treats the absence as "no tl_dr".
    """

    items: list[JoinedItem] = Field(default_factory=list, max_length=40)
    tl_dr: str = Field(default="", max_length=600)


# Bound the prompt payload so a long previous report doesn't blow the
# context window. 40 items at ~500 chars summary is well under any
# Anthropic / GPT model's input cap; this is a defensive ceiling.
_MAX_PREV_ITEMS = 40


def _dump_previous_items(items: object) -> str:
    """Render the previous report's items list as compact JSON for the prompt.

    Falls back to an empty list if the input is malformed — the prompt
    handles "previous list is empty" by just acting on the hint alone.
    Typed as ``object`` so we can accept the raw JSONB payload from the
    DB without trusting its shape.
    """
    if not isinstance(items, list):
        return "[]"
    trimmed = items[:_MAX_PREV_ITEMS]
    return json.dumps(trimmed, ensure_ascii=False, indent=2, default=str)


async def refine(
    previous_items: list[dict[str, Any]],
    previous_tl_dr: str,
    hint: str,
) -> tuple[list[JoinedItem], str, int, int]:
    """Run one refine pass.

    Args:
        previous_items: The previous Report's `content["items"]` payload
            (raw JSONB dicts — the API hands us whatever was persisted).
        previous_tl_dr: The previous Report's `content.get("tl_dr", "")`.
            Empty string is fine when batch-2q hasn't landed yet.
        hint: The user's verbatim refinement instruction.

    Returns:
        Tuple of (new items list, new tl_dr, input_tokens, output_tokens).
        On parse failure, returns ([], "", 0, 0) — the caller will treat
        the empty list as a no-op refine and surface that to the user.
    """
    llm = llm_factory.get_llm_provider("joiner_agent")
    system = load_prompt("refiner", "v1")

    user_payload = "\n".join(
        [
            "## previous_items_json",
            "```json",
            _dump_previous_items(previous_items),
            "```",
            "",
            "## previous_tl_dr",
            previous_tl_dr or "(none)",
            "",
            "## hint",
            "```",
            hint,
            "```",
        ]
    )

    response = await llm.complete(
        system=system,
        messages=[Message(role="user", content=user_payload)],
        response_model=RefinerOutput,
    )

    parsed = response.parsed if response.parsed is not None else RefinerOutput()
    return (
        parsed.items,
        parsed.tl_dr,
        response.usage.input_tokens,
        response.usage.output_tokens,
    )
