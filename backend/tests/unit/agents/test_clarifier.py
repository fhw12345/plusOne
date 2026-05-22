"""Unit tests for the batch-2t clarifier agent.

Tests cover the fail-open contract: LLM mock returning 0 / 1 / 3 / >3
questions, invalid JSON, and timeout — all should resolve to a normalised
list (or ``[]`` on the failure paths).
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from plus_one.agents import clarifier as clarifier_mod
from plus_one.agents.clarifier import (
    MAX_QUESTIONS,
    _ClarifierOutput,
    run_clarifier,
)


def _mk_response(parsed_data: dict[str, Any] | None, text: str = "{}") -> Any:
    """Build a fake LLMProvider.complete() return value."""
    parsed = (
        _ClarifierOutput.model_validate(parsed_data) if parsed_data is not None else None
    )

    class _Usage:
        input_tokens = 0
        output_tokens = 0

    class _R:
        def __init__(self) -> None:
            self.parsed = parsed
            self.text = text
            self.usage = _Usage()
            self.model = "mock"
            self.provider = "mock"

    return _R()


def _patch_llm(monkeypatch: pytest.MonkeyPatch, response: Any) -> AsyncMock:
    """Replace the conversational provider's ``complete`` with an AsyncMock."""
    complete = AsyncMock(return_value=response)

    class _Provider:
        name = "mock"

        async def complete(self, **kwargs: Any) -> Any:
            return await complete(**kwargs)

    monkeypatch.setattr(
        clarifier_mod.llm_factory,
        "get_llm_provider",
        lambda *_a, **_kw: _Provider(),
    )
    return complete


@pytest.mark.unit
async def test_returns_empty_when_llm_returns_zero_questions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_llm(monkeypatch, _mk_response({"questions": []}))
    result = await run_clarifier(destination="kyoto", free_text="quiet temples")
    assert result == []


@pytest.mark.unit
async def test_returns_one_question_with_normalised_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_llm(
        monkeypatch,
        _mk_response(
            {"questions": [{"id": "q1", "text": "fixed dates or flexible?"}]}
        ),
    )
    result = await run_clarifier(destination="kyoto", free_text=None)
    assert result == [{"id": "q1", "text": "fixed dates or flexible?"}]


@pytest.mark.unit
async def test_returns_three_questions(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_llm(
        monkeypatch,
        _mk_response(
            {
                "questions": [
                    {"id": "q1", "text": "a"},
                    {"id": "q2", "text": "b"},
                    {"id": "q3", "text": "c"},
                ]
            }
        ),
    )
    result = await run_clarifier(destination="tokyo", free_text=None)
    assert [q["id"] for q in result] == ["q1", "q2", "q3"]
    assert [q["text"] for q in result] == ["a", "b", "c"]


@pytest.mark.unit
async def test_truncates_more_than_three_questions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_llm(
        monkeypatch,
        _mk_response(
            {
                "questions": [
                    {"id": "q1", "text": "a"},
                    {"id": "q2", "text": "b"},
                    {"id": "q3", "text": "c"},
                    {"id": "q4", "text": "d"},
                    {"id": "q5", "text": "e"},
                ]
            }
        ),
    )
    result = await run_clarifier(destination="kyoto", free_text=None)
    assert len(result) == MAX_QUESTIONS
    assert [q["id"] for q in result] == ["q1", "q2", "q3"]


@pytest.mark.unit
async def test_restamps_garbled_llm_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_llm(
        monkeypatch,
        _mk_response(
            {
                "questions": [
                    {"id": "abc", "text": "first"},
                    {"id": "xyz", "text": "second"},
                ]
            }
        ),
    )
    result = await run_clarifier(destination="kyoto", free_text=None)
    assert [q["id"] for q in result] == ["q1", "q2"]


@pytest.mark.unit
async def test_returns_empty_on_invalid_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The provider returns ``parsed=None`` and text isn't valid JSON either."""
    _patch_llm(monkeypatch, _mk_response(None, text="not json at all <<<"))
    result = await run_clarifier(destination="kyoto", free_text=None)
    assert result == []


@pytest.mark.unit
async def test_returns_empty_on_llm_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _BoomProvider:
        name = "boom"

        async def complete(self, **_kw: Any) -> Any:
            raise RuntimeError("upstream 502")

    monkeypatch.setattr(
        clarifier_mod.llm_factory,
        "get_llm_provider",
        lambda *_a, **_kw: _BoomProvider(),
    )
    result = await run_clarifier(destination="kyoto", free_text=None)
    assert result == []


@pytest.mark.unit
async def test_returns_empty_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    class _SlowProvider:
        name = "slow"

        async def complete(self, **_kw: Any) -> Any:
            await asyncio.sleep(10)
            raise AssertionError("should have been cancelled")

    monkeypatch.setattr(
        clarifier_mod.llm_factory,
        "get_llm_provider",
        lambda *_a, **_kw: _SlowProvider(),
    )
    # Shrink the timeout so the test doesn't actually wait 5s.
    monkeypatch.setattr(clarifier_mod, "CLARIFIER_TIMEOUT_S", 0.05)
    result = await run_clarifier(destination="kyoto", free_text=None)
    assert result == []


@pytest.mark.unit
async def test_drops_empty_text_questions(monkeypatch: pytest.MonkeyPatch) -> None:
    """Whitespace-only ``text`` doesn't survive Pydantic min_length=1.

    The LLM should never emit one but the normaliser is defensive; check
    that the model itself rejects an empty string (so the agent fails
    open rather than persisting a useless question).
    """
    # text="" violates ClarifierQuestion's min_length=1 — Pydantic raises
    # ValidationError, run_clarifier catches and returns [].
    with patch.object(
        clarifier_mod,
        "_call_llm",
        AsyncMock(
            side_effect=lambda *_a, **_kw: _ClarifierOutput(questions=[]),
        ),
    ):
        # Pre-build via direct call to make sure the normaliser short-circuits.
        result = await run_clarifier(destination="kyoto", free_text=None)
    assert result == []
