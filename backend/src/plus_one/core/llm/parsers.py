"""Three-tier fallback parser for LLM JSON output.

We *want* the LLM to return clean JSON matching our Pydantic schema. We *expect*
it to sometimes return:

  1. Pure JSON                              -> parse directly
  2. JSON in ```json ... ``` code block     -> strip fences, parse
  3. JSON embedded in prose                 -> brace-matching extraction
  4. Garbage / refusal                      -> raise

We never silently hand back a half-parsed object — if all tiers fail, we raise
:class:`LLMParseError` so the caller can decide (retry, log, escalate).
"""

from __future__ import annotations

import json
import re
from typing import TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


class LLMParseError(ValueError):
    """Raised when LLM output cannot be coerced into the target schema."""

    def __init__(self, raw: str, model: type[BaseModel], attempts: list[str]) -> None:
        super().__init__(
            f"Could not parse LLM output into {model.__name__}. "
            f"Attempts: {attempts}. Raw output (truncated): {raw[:200]!r}"
        )
        self.raw = raw
        self.model = model
        self.attempts = attempts


_CODE_FENCE = re.compile(r"```(?:json)?\s*(.+?)```", re.DOTALL)


def _strategy_direct(text: str, model: type[T]) -> T:
    """Tier 1: assume the whole text is JSON."""
    return model.model_validate_json(text.strip())


def _strategy_code_fence(text: str, model: type[T]) -> T:
    """Tier 2: extract JSON from a markdown code fence."""
    match = _CODE_FENCE.search(text)
    if not match:
        raise ValueError("no code fence found")
    return model.model_validate_json(match.group(1).strip())


def _strategy_brace_match(text: str, model: type[T]) -> T:
    """Tier 3: find the first balanced ``{...}`` (or ``[...]``) and parse."""
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        if start == -1:
            continue
        depth = 0
        for i in range(start, len(text)):
            ch = text[i]
            if ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    candidate = text[start : i + 1]
                    try:
                        data = json.loads(candidate)
                    except json.JSONDecodeError:
                        break
                    return model.model_validate(data)
    raise ValueError("no balanced braces found")


def parse_with_fallback(text: str, model: type[T]) -> T:
    """Try parse strategies in order; raise :class:`LLMParseError` if all fail."""
    attempts: list[str] = []
    for strategy_name, strategy in (
        ("direct", _strategy_direct),
        ("code_fence", _strategy_code_fence),
        ("brace_match", _strategy_brace_match),
    ):
        try:
            return strategy(text, model)
        except (ValueError, ValidationError, json.JSONDecodeError) as e:
            attempts.append(f"{strategy_name}: {type(e).__name__}")

    raise LLMParseError(raw=text, model=model, attempts=attempts)
