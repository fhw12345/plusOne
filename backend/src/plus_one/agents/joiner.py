"""Joiner agent — fetches multi-source evidence per candidate and classifies.

Conforms to ``JoinerFn[Candidate, JoinedItem]``. For each Candidate, it
fans out parallel tool calls (Reddit, XHS, Google Places), then asks
the LLM to roll the results into a Classification + Evidence list.

Per ADR-005, ``joiner_agent`` is a heavy-reasoning role (Claude Opus
4.7 by default).
"""

from __future__ import annotations

import asyncio
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field

from plus_one.agents.producer import Candidate
from plus_one.agents.prompts import load_prompt
from plus_one.agents.types import Classification, Evidence
from plus_one.core.agents.framework.tools import Tool, ToolCall, ToolRegistry, run_tool_calls
from plus_one.core.agents.framework.types import AgentContext, PhaseResult
from plus_one.core.llm import Message
from plus_one.core.llm import factory as llm_factory
from plus_one.core.tools import (
    GooglePlacesSearchTool,
    RedditSearchTool,
    XHSSearchTool,
)


class JoinedItem(BaseModel):
    """Producer Candidate enriched with classification + evidence."""

    model_config = ConfigDict(frozen=True)

    candidate: Candidate
    classification: Classification
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: tuple[Evidence, ...] = Field(default=())
    summary: str = Field(default="", max_length=500)


class _JoinerOutput(BaseModel):
    items: list[JoinedItem] = Field(default_factory=list, max_length=30)


# How many hits per source per candidate to serialize into the LLM prompt.
# Capping keeps the payload bounded while still giving the LLM enough URLs
# to cite — see Reviewer B1 fix.
_MAX_HITS_PER_SOURCE = 5
_MAX_SNIPPET_CHARS = 240


def _format_hit(source: str, hit: object) -> str:
    """Render one tool-result hit as a single line for the LLM prompt.

    Each tool returns Pydantic objects with somewhat different shapes
    (RedditPost has subreddit + score, Place has rating + address). We
    normalize to ``- [<source>][<url>] <title>: <snippet>`` so the LLM
    has one consistent format to read.
    """
    url = (
        getattr(hit, "permalink", None)
        or getattr(hit, "url", None)
        or getattr(hit, "google_maps_url", None)
        or "(no url)"
    )
    title = getattr(hit, "title", None) or getattr(hit, "name", "") or ""
    body = getattr(hit, "body", None) or getattr(hit, "formatted_address", "") or ""
    snippet = str(body)[:_MAX_SNIPPET_CHARS]
    return f"- [{source}][{url}] {title}: {snippet}"


def _default_registry() -> ToolRegistry:
    """Build a ToolRegistry with the three Plus One tools.

    Constructed per-call so each cycle gets a fresh registry — keeps
    tests trivial and avoids cross-cycle state leaks. Tool instances
    themselves are stateless beyond their fixtures_dir.
    """
    reg = ToolRegistry()
    # cast so mypy stops complaining about Protocol ClassVar vs instance-attribute
    # mismatch — the runtime ``isinstance(tool, Tool)`` check (covered in
    # tests/unit/tools/test_tools.py) passes.
    reg.register(cast("Tool[Any, Any]", RedditSearchTool()))
    reg.register(cast("Tool[Any, Any]", XHSSearchTool()))
    reg.register(cast("Tool[Any, Any]", GooglePlacesSearchTool()))
    return reg


def _build_tool_calls(candidate: Candidate, query: str) -> list[ToolCall]:
    """Plan the per-candidate tool fan-out.

    Three parallel calls per candidate covering English / Chinese /
    factual sources. The framework dispatcher runs them concurrently
    because all three tools self-report ``is_concurrency_safe=True``.
    """
    base = candidate.name
    if candidate.style:
        base = f"{base} {candidate.style}"
    return [
        ToolCall(
            tool="reddit_search",
            args={"query": base, "subreddits": ["JapanTravel", "ramen"], "limit": 10},
        ),
        ToolCall(tool="xhs_search", args={"query": f"{base} 推荐", "limit": 10}),
        ToolCall(
            tool="google_places_search",
            args={"query": base, "location_hint": query, "limit": 5},
        ),
    ]


async def joiner(candidates: list[Candidate], ctx: AgentContext) -> PhaseResult[list[JoinedItem]]:
    """Run the Joiner phase: fetch evidence + classify each candidate."""
    registry = _default_registry()

    # Fan out evidence-gathering across all candidates in parallel.
    fetch_tasks = [run_tool_calls(registry, _build_tool_calls(c, ctx.query)) for c in candidates]
    all_results = await asyncio.gather(*fetch_tasks)

    # Hand the raw fetches + candidates to the LLM for classification.
    # Per-source, serialize the top hits with URL + title + snippet so the
    # LLM has actual evidence to cite (Reviewer B1: prompt forbids
    # inventing URLs, so the payload must contain the URLs to cite).
    llm = llm_factory.get_llm_provider("joiner_agent")
    system = load_prompt("joiner", "v1")
    user_payload_lines: list[str] = [f"User query: {ctx.query}", ""]
    for candidate, results in zip(candidates, all_results, strict=True):
        user_payload_lines.append(f"## {candidate.name} ({candidate.area or 'unknown'})")
        for r in results:
            label = r.tool
            if not r.ok or not r.output:
                user_payload_lines.append(f"### {label}: empty/{r.error or 'no data'}")
                continue
            user_payload_lines.append(f"### {label} ({len(r.output)} hits)")
            for hit in r.output[:_MAX_HITS_PER_SOURCE]:
                user_payload_lines.append(_format_hit(label, hit))
        user_payload_lines.append("")

    response = await llm.complete(
        system=system,
        messages=[Message(role="user", content="\n".join(user_payload_lines))],
        response_model=_JoinerOutput,
    )

    parsed = response.parsed if response.parsed is not None else _JoinerOutput()

    # Reviewer B3: the prompt asks the LLM to "echo back the candidate
    # object as given," but Pydantic accepts whatever it returns. Replace
    # each parsed candidate with the original Producer Candidate (matched
    # by case-insensitive name) so name/area/style cannot silently drift
    # between the Producer's output and the report. Items whose name we
    # can't match are dropped (the LLM hallucinated a candidate).
    by_name: dict[str, Candidate] = {c.name.lower(): c for c in candidates}
    repaired: list[JoinedItem] = []
    dropped = 0
    for item in parsed.items:
        original = by_name.get(item.candidate.name.lower())
        if original is None:
            dropped += 1
            continue
        repaired_item = (
            item if item.candidate is original else item.model_copy(update={"candidate": original})
        )
        repaired.append(repaired_item)

    return PhaseResult(
        payload=repaired,
        notes=(
            f"candidates_in={len(candidates)} joined_out={len(repaired)} "
            f"dropped_unknown={dropped} "
            f"in_tokens={response.usage.input_tokens} "
            f"out_tokens={response.usage.output_tokens}"
        ),
    )
