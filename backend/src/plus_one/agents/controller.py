"""Controller agent — rule-first decision with LLM fallback.

Conforms to ``ControllerFn[JoinedItem]``. Implements the agent-framework-
patterns.md rule:

  > 70% of "should we continue" decisions don't need an LLM.

Three deterministic stop signals fire before any LLM call:
  1. Depth cap reached (handled by the cycle main loop, but we honor it
     here too so that a Controller-only test sees the same behaviour).
  2. No new items in this round (Joiner produced nothing classifiable
     beyond what we already had).
  3. Sufficient coverage: at least N local-gem items AND at least M
     tourist-trap items.

Only when none of those fire do we ask the LLM (cheap ``controller_agent``
role, Claude Haiku 4.5 by default per ADR-005) to make the judgment call.
"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from plus_one.agents.prompts import load_prompt
from plus_one.core.agents.framework.types import AgentContext, Decision, PhaseResult
from plus_one.core.llm import Message
from plus_one.core.llm import factory as llm_factory

if TYPE_CHECKING:
    from plus_one.agents.joiner import JoinedItem


# Tunable thresholds for the rule-first stop signal. Kept as module-
# private constants so a future config surface can lift them; for v1
# they're hard-coded to PRD §10 success-metric targets (≥3 traps, ≥5 gems).
_MIN_LOCAL_GEMS = 5
_MIN_TOURIST_TRAPS = 3
_MIN_USEFUL_ITEMS_TO_STOP = 5


class ControllerInput(BaseModel):
    """Wrapper that carries the bare minimum the Controller needs.

    Not part of the public framework signature — exposed for tests that
    want to inject controlled state without a full cycle.
    """

    items: list[JoinedItem] = Field(default_factory=list)
    depth: int
    max_depth: int


class _LLMDecisionOutput(BaseModel):
    should_continue: bool
    reasoning: str = ""
    summary: str = ""


def _classification_counts(items: list[JoinedItem]) -> Counter[str]:
    return Counter(item.classification for item in items)


def _rule_decision(items: list[JoinedItem], ctx: AgentContext) -> Decision | None:
    """Deterministic stop signals. Return Decision to stop, or None to defer.

    Note: depth-cap enforcement is the cycle main loop's responsibility
    (single source of truth). The previous "depth_cap_imminent" rule
    here was logically wrong (off-by-one — fired on the second-to-last
    iteration, discarding the round's joined results) and duplicated
    the cycle's own check. Removed per Reviewer B2.
    """
    counts = _classification_counts(items)
    gems = counts.get("local_gem", 0)
    traps = counts.get("tourist_trap", 0)
    insufficient = counts.get("insufficient", 0)
    total = sum(counts.values())

    if total == 0:
        # Joiner produced literally nothing; the framework will catch
        # the empty-Producer abort if Producer also gives nothing next
        # round, so we ask for one more pass.
        return Decision(
            should_continue=True,
            reasoning="no joined items yet",
            summary=ctx.summary,
        )

    if gems >= _MIN_LOCAL_GEMS and traps >= _MIN_TOURIST_TRAPS:
        return Decision(
            should_continue=False,
            reasoning=f"sufficient coverage: {gems} gems, {traps} traps",
            summary=ctx.summary,
        )

    useful = total - insufficient
    if useful >= _MIN_USEFUL_ITEMS_TO_STOP:
        return Decision(
            should_continue=False,
            reasoning=f"enough usable coverage: {useful} classified items",
            summary=ctx.summary,
        )

    if insufficient > total * 0.5:
        # Lots of "I can't tell" classifications — push for more
        # candidates / better evidence.
        return Decision(
            should_continue=True,
            reasoning=f"too many insufficient ({insufficient}/{total})",
            summary=ctx.summary,
        )

    return None  # ambiguous — let the LLM judge


async def _llm_decision(items: list[JoinedItem], ctx: AgentContext) -> Decision:
    counts = _classification_counts(items)
    summary_lines = [
        f"depth={ctx.depth}/{ctx.max_depth}",
        f"items so far: {dict(counts)}",
        f"prior summary: {ctx.summary or '(none)'}",
        "",
        "Sample item names + classifications:",
    ]
    for item in items[:10]:
        summary_lines.append(
            f"- {item.candidate.name} ({item.classification}, conf={item.confidence:.2f})"
        )

    llm = llm_factory.get_llm_provider("controller_agent")
    response = await llm.complete(
        system=load_prompt("controller", "v1"),
        messages=[Message(role="user", content="\n".join(summary_lines))],
        response_model=_LLMDecisionOutput,
    )
    parsed = response.parsed
    if parsed is None:
        return Decision(
            should_continue=False,
            reasoning="LLM output unparseable; defaulting to stop",
            summary=ctx.summary,
        )
    return Decision(
        should_continue=parsed.should_continue,
        reasoning=parsed.reasoning,
        summary=parsed.summary or ctx.summary,
    )


async def controller(items: list[JoinedItem], ctx: AgentContext) -> PhaseResult[Decision]:
    """Run the Controller phase: rule-first, LLM fallback."""
    rule = _rule_decision(items, ctx)
    if rule is not None:
        return PhaseResult(payload=rule, notes="rule-first decision")
    decision = await _llm_decision(items, ctx)
    return PhaseResult(payload=decision, notes="llm fallback decision")
