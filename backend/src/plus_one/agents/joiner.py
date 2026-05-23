"""Joiner agent — fetches multi-source evidence per candidate and classifies.

Conforms to ``JoinerFn[Candidate, JoinedItem]``. For each Candidate, it
fans out parallel tool calls (Reddit, XHS, Foursquare), then asks
the LLM to roll the results into a Classification + Evidence list.

Per ADR-005, ``joiner_agent`` is a heavy-reasoning role (Claude Opus
4.7 by default).
"""

from __future__ import annotations

import asyncio
from typing import Any, cast
from uuid import UUID  # noqa: TC003 — runtime use as Pydantic field annotation

from pydantic import BaseModel, ConfigDict, Field

from plus_one.agents._divergence import divergence_score
from plus_one.agents._scoring import render_person_roster, validate_match_scores
from plus_one.agents.preferences import render_preferences_section
from plus_one.agents.producer import Candidate
from plus_one.agents.prompts import load_prompt
from plus_one.agents.types import Classification, Evidence
from plus_one.core.agents.framework.tools import Tool, ToolCall, ToolRegistry, run_tool_calls
from plus_one.core.agents.framework.types import AgentContext, PhaseResult
from plus_one.core.llm import Message
from plus_one.core.llm import factory as llm_factory
from plus_one.core.tools import (
    FoursquarePlacesSearchTool,
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
    # Per-language classifications computed from the source subsets
    # (`reddit` → en, `xiaohongshu` → zh). ``None`` is the explicit "no
    # evidence on this side" sentinel; the UI disagreement gate requires
    # both sides non-null. See PRD batch2i §4.1.
    classification_en: Classification | None = None
    classification_zh: Classification | None = None
    # Deterministic divergence score in [0, 1]. Always overwritten in
    # ``joiner`` after the LLM call from ``divergence_score(en, zh)`` —
    # the LLM never authors this value. See PRD batch2i §4.3 / §4.4.
    divergence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    # Batch-2p: per-person match scores in [0.0, 1.0]. Keyed by user.id
    # (for the requesting user) and companion.id (for each selected
    # companion). ``None`` = not scored (old reports, candidates where
    # scoring did not apply, or no party identity available). The LLM
    # may emit string UUID keys; Pydantic coerces.
    match_scores: dict[UUID, float] | None = Field(default=None)


class JoinerPayload(BaseModel):
    """What the joiner phase returns inside ``PhaseResult.payload``.

    Batch-2q widens the payload from a bare ``list[JoinedItem]`` to a
    small structured object carrying the report-level ``tl_dr`` alongside
    the items. Callers that only consume items can read ``payload.items``;
    the report-save path picks up ``payload.tl_dr``.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    items: list[JoinedItem] = Field(default_factory=list)
    tl_dr: str | None = Field(default=None)


class _JoinerOutput(BaseModel):
    items: list[JoinedItem] = Field(default_factory=list, max_length=30)
    # Optional one-paragraph synthesis written at the very end of the
    # joiner call. See batch-2q PRD §4.1.
    tl_dr: str | None = Field(default=None)


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
        or getattr(hit, "external_url", None)
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
    reg.register(cast("Tool[Any, Any]", FoursquarePlacesSearchTool()))
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
            tool="places_search",
            args={"query": base, "location_hint": query, "limit": 5},
        ),
    ]


async def joiner(candidates: list[Candidate], ctx: AgentContext) -> PhaseResult[JoinerPayload]:
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
    # Use .replace (not .format) for the placeholders so the literal JSON
    # braces in the prompt's output-format block stay untouched. Producer
    # uses .format because its braces are already doubled; the Joiner
    # prompt would need every JSON brace re-doubled to switch, so we
    # keep the call simple and surgical (PRD §7).
    system = (
        load_prompt("joiner", "v3")
        .replace(
            "{preferences}",
            render_preferences_section(ctx.user_profile, ctx.selected_companions),
        )
        .replace(
            "{person_roster}",
            render_person_roster(ctx.user_profile, ctx.selected_companions),
        )
    )
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

    # Build the set of allowed person ids for match_scores validation.
    allowed_ids: set[UUID] = set()
    if ctx.user_profile.id is not None:
        allowed_ids.add(ctx.user_profile.id)
    for companion in ctx.selected_companions:
        if companion.id is not None:
            allowed_ids.add(companion.id)

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
        # Always overwrite divergence_score deterministically — the LLM
        # may or may not have emitted it; we are the single source of
        # truth (PRD batch2i §4.4).
        score = divergence_score(item.classification_en, item.classification_zh)
        # Batch-2p: sanitise per-person match_scores against the known
        # party. Drops hallucinated UUIDs, fills missing required keys
        # with the neutral default, clamps values to [0, 1].
        sanitised_scores = validate_match_scores(item.match_scores, allowed_ids)
        updates: dict[str, object] = {}
        if item.candidate is not original:
            updates["candidate"] = original
        if score != item.divergence_score:
            updates["divergence_score"] = score
        if sanitised_scores != item.match_scores:
            updates["match_scores"] = sanitised_scores
        repaired_item = item.model_copy(update=updates) if updates else item
        repaired.append(repaired_item)

    payload = JoinerPayload(items=repaired, tl_dr=parsed.tl_dr)
    return PhaseResult(
        payload=payload,
        notes=(
            f"candidates_in={len(candidates)} joined_out={len(repaired)} "
            f"dropped_unknown={dropped} "
            f"in_tokens={response.usage.input_tokens} "
            f"out_tokens={response.usage.output_tokens}"
        ),
    )
