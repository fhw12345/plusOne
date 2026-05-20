"""Unit tests for the translator agent."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from plus_one.agents.joiner import JoinedItem
from plus_one.agents.producer import Candidate
from plus_one.agents.translator import translate_items


def _make_item(name: str, summary: str = "original summary") -> JoinedItem:
    return JoinedItem(
        candidate=Candidate(name=name, area="Tokyo"),
        classification="local_gem",
        confidence=0.8,
        evidence=(),
        summary=summary,
    )


@pytest.mark.unit
async def test_empty_items_returns_empty_no_llm_calls(mock_llm) -> None:
    out = await translate_items([], "original", "en")
    assert out == []
    assert mock_llm.call_count == 0


@pytest.mark.unit
async def test_translate_invokes_llm_once_per_item(mock_llm) -> None:
    items = [_make_item("A"), _make_item("B"), _make_item("C")]
    for i in range(3):
        mock_llm.queue_response(
            role="translator_agent",
            text="{}",
            parsed_data={
                "candidate": {"name": f"翻译 {i}", "area": "东京"},
                "classification": "local_gem",
                "confidence": 0.8,
                "evidence": [],
                "summary": "翻译过的摘要",
            },
        )

    out = await translate_items(items, "original", "zh")
    assert len(out) == 3
    assert mock_llm.call_count == 3
    # All calls routed to the translator_agent role
    assert all(c["role"] == "translator_agent" for c in mock_llm.calls)
    # Each output is a dict (JSON-safe), not a JoinedItem
    assert all(isinstance(o, dict) for o in out)
    assert {o["candidate"]["name"] for o in out} == {"翻译 0", "翻译 1", "翻译 2"}


@pytest.mark.unit
async def test_failed_item_falls_back_to_original(mock_llm, monkeypatch) -> None:
    """When the LLM raises for one item, original payload is preserved."""
    items = [_make_item("Good"), _make_item("Bad"), _make_item("Also Good")]

    # Two good queued responses; the middle item will fail because we
    # patch ``complete`` to raise on the second call only.
    for i in (0, 1):
        mock_llm.queue_response(
            role="translator_agent",
            text="{}",
            parsed_data={
                "candidate": {"name": f"ok-{i}", "area": "Tokyo"},
                "classification": "local_gem",
                "confidence": 0.8,
                "evidence": [],
                "summary": "translated",
            },
        )

    call_log: list[int] = []
    original_complete = mock_llm.complete

    async def maybe_raise_complete(**kwargs: Any) -> Any:
        call_log.append(1)
        if len(call_log) == 2:
            raise RuntimeError("LLM exploded mid-translation")
        return await original_complete(**kwargs)

    monkeypatch.setattr(mock_llm, "complete", maybe_raise_complete)

    # Force sequential ordering by capping the semaphore via test-only
    # patch: re-use the public API but our concurrency is internal. To
    # deterministically assert "second one fails", set concurrency to 1.
    from plus_one.agents import translator as translator_mod

    monkeypatch.setattr(translator_mod, "_TRANSLATOR_CONCURRENCY", 1)

    out = await translate_items(items, "original", "en")
    assert len(out) == 3
    # First and third succeeded → start with "ok-"; second is the failed
    # one and falls back to the original payload (name="Bad")
    assert out[0]["candidate"]["name"].startswith("ok-")
    assert out[1]["candidate"]["name"] == "Bad"  # fallback to original
    assert out[2]["candidate"]["name"].startswith("ok-")


@pytest.mark.unit
async def test_no_parsed_output_falls_back_to_original(mock_llm) -> None:
    """When the LLM returns text but no parsed model, fall back to original."""
    items = [_make_item("Solo")]
    # Don't queue a response → mock returns the default which has no parsed_data
    out = await translate_items(items, "original", "en")
    assert len(out) == 1
    assert out[0]["candidate"]["name"] == "Solo"


@pytest.mark.unit
async def test_concurrency_bounded_by_semaphore(mock_llm, monkeypatch) -> None:
    """At most 5 LLM calls should be in flight at once."""
    items = [_make_item(f"item-{i}") for i in range(20)]

    in_flight = 0
    peak = 0
    lock = asyncio.Lock()

    original_complete = mock_llm.complete

    async def tracking_complete(**kwargs: Any) -> Any:
        nonlocal in_flight, peak
        async with lock:
            in_flight += 1
            peak = max(peak, in_flight)
        try:
            # yield to allow other tasks to enter
            await asyncio.sleep(0.01)
            return await original_complete(**kwargs)
        finally:
            async with lock:
                in_flight -= 1

    monkeypatch.setattr(mock_llm, "complete", tracking_complete)

    # Each call uses the default (empty) response → fallback path; we
    # don't care about the output here, only the concurrency observation.
    await translate_items(items, "original", "zh")
    assert peak <= 5, f"semaphore should cap at 5, peaked at {peak}"
    assert peak >= 2, "with 20 items we should observe at least 2 concurrent"


@pytest.mark.unit
async def test_input_items_not_mutated(mock_llm) -> None:
    """Original items list must be returned unmutated."""
    items = [_make_item("Original", summary="do-not-touch")]
    mock_llm.queue_response(
        role="translator_agent",
        text="{}",
        parsed_data={
            "candidate": {"name": "Translated", "area": "Tokyo"},
            "classification": "local_gem",
            "confidence": 0.8,
            "evidence": [],
            "summary": "translated summary",
        },
    )
    out = await translate_items(items, "original", "zh")
    # Output reflects translation
    assert out[0]["summary"] == "translated summary"
    # Original Pydantic objects are immutable (frozen=True) so direct
    # mutation isn't even possible, but assert structurally too.
    assert items[0].summary == "do-not-touch"
    assert items[0].candidate.name == "Original"
