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
from typing import Any

from pydantic import BaseModel, ValidationError


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


def _json_loads(text: str) -> Any:
    return json.loads(text, strict=False)


def _balanced_json_slice(text: str, opener_filter: str) -> str | None:
    pairs = {"{": "}", "[": "]"}
    closers = {v: k for k, v in pairs.items()}
    for start, ch in enumerate(text):
        if ch not in opener_filter:
            continue
        stack: list[str] = []
        in_string = False
        escaped = False
        for i in range(start, len(text)):
            cur = text[i]
            if in_string:
                if escaped:
                    escaped = False
                elif cur == "\\":
                    escaped = True
                elif cur == '"':
                    in_string = False
                continue
            if cur == '"':
                in_string = True
            elif cur in pairs:
                stack.append(cur)
            elif cur in closers:
                if not stack or stack[-1] != closers[cur]:
                    break
                stack.pop()
                if not stack:
                    return text[start : i + 1]
    return None


def extract_json_with_fallback(text: str) -> Any:
    """Extract a JSON value from raw LLM text without schema validation."""
    attempts: list[str] = []
    stripped = text.strip()
    try:
        return _json_loads(stripped)
    except json.JSONDecodeError as exc:
        attempts.append(f"direct: {type(exc).__name__}")

    match = _CODE_FENCE.search(text)
    if match:
        try:
            return _json_loads(match.group(1).strip())
        except json.JSONDecodeError as exc:
            attempts.append(f"code_fence: {type(exc).__name__}")
    else:
        attempts.append("code_fence: ValueError")

    for opener_filter in ("{", "["):
        candidate = _balanced_json_slice(text, opener_filter)
        if candidate is None:
            attempts.append("brace_match: ValueError")
            continue
        try:
            return _json_loads(candidate)
        except json.JSONDecodeError as exc:
            attempts.append(f"brace_match: {type(exc).__name__}")

    raise ValueError(f"Could not extract JSON from LLM output. Attempts: {attempts}")


def _strategy_direct[T: BaseModel](text: str, model: type[T]) -> T:
    """Tier 1: assume the whole text is JSON."""
    return model.model_validate_json(text.strip())


def _strategy_code_fence[T: BaseModel](text: str, model: type[T]) -> T:
    """Tier 2: extract JSON from a markdown code fence."""
    match = _CODE_FENCE.search(text)
    if not match:
        raise ValueError("no code fence found")
    return model.model_validate_json(match.group(1).strip())


def _strategy_brace_match[T: BaseModel](text: str, model: type[T]) -> T:
    """Tier 3: find the first balanced ``{...}`` (or ``[...]``) and parse."""
    for opener_filter in ("{", "["):
        candidate = _balanced_json_slice(text, opener_filter)
        if candidate is None:
            continue
        data = _json_loads(candidate)
        return model.model_validate(data)
    raise ValueError("no balanced braces found")


def parse_with_fallback[T: BaseModel](text: str, model: type[T]) -> T:
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
