"""Producer agent — generates candidate places from a user query.

Conforms to ``ProducerFn[Candidate]`` so it can be passed straight to
``run_cycle(producer=producer, ...)``. Uses the ``producer_agent`` LLM
role (Claude Opus 4.7 by default per ADR-005) and routes Plus One
skills via the SkillRegistry to inject relevant methodology into the
system prompt.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from plus_one.agents.preferences import render_preferences_section
from plus_one.agents.prompts import load_prompt
from plus_one.core.agents.framework.skills import SkillRegistry
from plus_one.core.agents.framework.types import AgentContext, PhaseResult
from plus_one.core.llm import Message
from plus_one.core.llm import factory as llm_factory


class Candidate(BaseModel):
    """One place / region / experience the Joiner should evaluate next."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1, max_length=200)
    area: str | None = Field(default=None, max_length=100)
    style: str | None = Field(
        default=None,
        max_length=100,
        description="Free-text descriptor: 'tonkotsu ramen', 'kissaten coffee', etc.",
    )
    rationale: str = Field(
        default="",
        max_length=500,
        description="Why the Producer surfaced this candidate",
    )


class _ProducerOutput(BaseModel):
    """Schema enforced on the LLM response."""

    candidates: list[Candidate] = Field(default_factory=list, max_length=20)


# Lazy-loaded registry — built once per process, then re-used.
_skills_dir = Path(__file__).resolve().parent.parent / "skills"
_skill_registry: SkillRegistry | None = None


def _get_skill_registry() -> SkillRegistry:
    # Process-wide cache of the loaded registry. Module-global is the
    # cleanest mechanism for "build once, reuse forever" without forcing
    # a singleton class on the framework.
    global _skill_registry  # noqa: PLW0603 — intentional one-time cache
    if _skill_registry is None:
        reg = SkillRegistry()
        reg.load_directory(_skills_dir)
        _skill_registry = reg
    return _skill_registry


def _build_system_prompt(ctx: AgentContext, skill_bodies: list[str]) -> str:
    """Compose the producer's system prompt from template + selected skills."""
    template = load_prompt("producer", "v1")
    skills_section = (
        "\n\n---\n\n".join(skill_bodies) if skill_bodies else "(no relevant skills loaded)"
    )
    preferences_section = render_preferences_section(
        ctx.user_profile, ctx.selected_companions
    )
    return template.format(
        skills=skills_section,
        prior_summary=ctx.summary or "(none)",
        preferences=preferences_section,
    )


async def producer(ctx: AgentContext) -> PhaseResult[list[Candidate]]:
    """Run the Producer phase against ``ctx.query``."""
    registry = _get_skill_registry()
    matched = registry.route(ctx.query, top_k=3)
    skill_bodies = [s.body for s in matched]

    llm = llm_factory.get_llm_provider("producer_agent")
    system = _build_system_prompt(ctx, skill_bodies)
    response = await llm.complete(
        system=system,
        messages=[Message(role="user", content=ctx.query)],
        response_model=_ProducerOutput,
    )

    parsed = response.parsed if response.parsed is not None else _ProducerOutput()
    return PhaseResult(
        payload=list(parsed.candidates),
        notes=(
            f"skills={[s.name for s in matched]} "
            f"in_tokens={response.usage.input_tokens} "
            f"out_tokens={response.usage.output_tokens}"
        ),
    )
