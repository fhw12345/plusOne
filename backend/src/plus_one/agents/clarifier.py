"""Clarifier agent - emits 0-3 short follow-up questions before the cycle.

Runs synchronously inside the ``POST /api/trips`` handler (PRD batch-2t
sec 4.1) under a hard 5s timeout. On timeout, LLM error, or invalid
output the agent **fails open** - it returns an empty list so the trip
falls straight through into the normal ``run_trip`` path. The clarifier
is a "would this make the plan better?" gate, not a hard dependency.

Conforms to a plain ``async def`` rather than the PhaseResult protocol
because the clarifier is not part of the iterative cycle - it runs once,
before the producer/joiner/controller loop begins.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import structlog
from pydantic import BaseModel, Field, ValidationError

from plus_one.agents.prompts import load_prompt
from plus_one.core.llm import Message
from plus_one.core.llm import factory as llm_factory

logger = structlog.get_logger()

# Hard budget for the clarifier LLM call. PRD §4.1: ≤5s; ``run_clarifier``
# returns an empty list on timeout so the trip can fall through.
CLARIFIER_TIMEOUT_S = 5.0

# Max questions the clarifier may emit — anything beyond is truncated.
MAX_QUESTIONS = 3


class ClarifierQuestion(BaseModel):
    """One follow-up question — ``id`` is ``q1``/``q2``/``q3``."""

    id: str = Field(min_length=1, max_length=8)
    text: str = Field(min_length=1, max_length=200)


class _ClarifierOutput(BaseModel):
    """Strict shape the LLM is asked to emit."""

    questions: list[ClarifierQuestion] = Field(default_factory=list)


def _build_user_payload(
    *,
    destination: str,
    free_text: str | None,
    companion_preferences: list[dict[str, Any]],
    date_start: str | None,
    date_end: str | None,
    budget_amount: int | None,
    budget_currency: str | None,
) -> str:
    """Render the inputs into a single user-message block.

    Kept deliberately small — the prompt itself enforces voice and
    output schema; this just lists what the user provided so the LLM
    can decide whether anything ambiguous needs nailing down.
    """
    lines: list[str] = [f"destination: {destination}"]
    if free_text and free_text.strip():
        lines.append(f"free_text: {free_text.strip()}")
    else:
        lines.append("free_text: (empty)")

    if date_start or date_end:
        lines.append(f"date_start: {date_start or '(none)'}")
        lines.append(f"date_end: {date_end or '(none)'}")
    else:
        lines.append("dates: (not provided)")

    if budget_amount is not None or budget_currency:
        amt = str(budget_amount) if budget_amount is not None else "(none)"
        cur = budget_currency or "(none)"
        lines.append(f"budget: {amt} {cur}")
    else:
        lines.append("budget: (not provided)")

    if companion_preferences:
        lines.append("")
        lines.append("companion_preferences:")
        for entry in companion_preferences:
            name = entry.get("name") or "(unnamed)"
            loves = entry.get("loves") or []
            hates = entry.get("hates") or []
            constraints = entry.get("constraints") or []
            lines.append(
                f"- {name} | loves: {list(loves)} | "
                f"hates: {list(hates)} | constraints: {list(constraints)}"
            )
    else:
        lines.append("companion_preferences: (none)")

    return "\n".join(lines)


def _normalise_questions(
    questions: list[ClarifierQuestion],
) -> list[dict[str, str]]:
    """Truncate to ``MAX_QUESTIONS`` and force ids ``q1``..``q{n}``.

    The prompt asks for ``q1``..``q3`` but we re-stamp defensively so a
    misnamed id from the LLM never leaks downstream and breaks the
    `/clarify` answer-matching contract.
    """
    out: list[dict[str, str]] = []
    for i, q in enumerate(questions[:MAX_QUESTIONS]):
        text = q.text.strip()
        if not text:
            continue
        out.append({"id": f"q{i + 1}", "text": text})
    return out


async def _call_llm(system: str, user_payload: str) -> _ClarifierOutput:
    """Run the LLM call. Separated so the timeout wrapper can cancel it."""
    llm = llm_factory.get_llm_provider("conversational")
    response = await llm.complete(
        system=system,
        messages=[Message(role="user", content=user_payload)],
        response_model=_ClarifierOutput,
        temperature=0.3,
    )
    if response.parsed is not None:
        return response.parsed
    # Three-tier parser already ran inside the provider; fall back to a
    # direct JSON parse in case the response text is valid JSON the
    # structured-output path didn't recognise.
    raw = json.loads(response.text)
    return _ClarifierOutput.model_validate(raw)


async def run_clarifier(
    *,
    destination: str,
    free_text: str | None,
    companion_preferences: list[dict[str, Any]] | None = None,
    date_start: str | None = None,
    date_end: str | None = None,
    budget_amount: int | None = None,
    budget_currency: str | None = None,
) -> list[dict[str, str]]:
    """Return 0-3 clarifying questions.

    Each item is ``{"id": "q1", "text": "..."}``. Always fails open: on
    timeout, LLM error, invalid JSON, or empty output, returns ``[]`` so
    the caller can fall straight through to the normal cycle path.
    """
    preferences = companion_preferences or []
    try:
        system = load_prompt("clarifier", "v1")
    except FileNotFoundError:
        logger.warning("clarifier_skipped", reason="prompt_missing")
        return []

    user_payload = _build_user_payload(
        destination=destination,
        free_text=free_text,
        companion_preferences=preferences,
        date_start=date_start,
        date_end=date_end,
        budget_amount=budget_amount,
        budget_currency=budget_currency,
    )

    try:
        parsed = await asyncio.wait_for(
            _call_llm(system, user_payload), timeout=CLARIFIER_TIMEOUT_S
        )
    except TimeoutError:
        logger.info("clarifier_skipped", reason="timeout")
        return []
    except (ValidationError, ValueError, TypeError) as exc:
        logger.info("clarifier_skipped", reason="invalid_output", error=str(exc))
        return []
    except Exception as exc:
        logger.info("clarifier_skipped", reason="llm_error", error=str(exc))
        return []

    normalised = _normalise_questions(parsed.questions)
    if not normalised:
        logger.info("clarifier_skipped", reason="empty")
    return normalised


__all__ = ["CLARIFIER_TIMEOUT_S", "MAX_QUESTIONS", "ClarifierQuestion", "run_clarifier"]
