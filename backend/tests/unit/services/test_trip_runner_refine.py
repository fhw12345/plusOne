"""Unit tests for trip_runner.run_refine (batch-2u).

Patches the refiner agent + DB session so we exercise the runner's
state machine + SSE event ordering without touching Postgres or an LLM.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from plus_one.agents.joiner import JoinedItem
from plus_one.agents.producer import Candidate
from plus_one.services import trip_runner


def _joined(name: str) -> JoinedItem:
    return JoinedItem(
        candidate=Candidate(name=name),
        classification="neutral",
        confidence=0.5,
        evidence=(),
        summary="",
    )


@pytest.fixture
def fake_db(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Stub the runner's DB touch-points.

    Captures every `_save_refine_report` invocation and serves a fake
    previous report for the in-coroutine `session.get(Report, ...)`
    call. Returns a dict the test can inspect.
    """
    state: dict[str, Any] = {
        "saved": [],
        "status_updates": [],
        "previous_content": {"items": [{"candidate": {"name": "Kiyomizu"}}], "tl_dr": "kyoto."},
    }

    async def fake_save(
        report_id: UUID,
        trip_id: UUID,
        items: list[JoinedItem],
        trace: list[dict[str, object]],
        input_tokens: int,
        output_tokens: int,
        previous_report_id: UUID,
        hint: str,
        tl_dr: str = "",
    ) -> UUID:
        state["saved"].append(
            {
                "report_id": report_id,
                "trip_id": trip_id,
                "items": items,
                "trace": trace,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "previous_report_id": previous_report_id,
                "hint": hint,
                "tl_dr": tl_dr,
            }
        )
        return report_id

    async def fake_set_status(trip_id: UUID, status: str) -> None:
        state["status_updates"].append((trip_id, status))

    monkeypatch.setattr(trip_runner, "_save_refine_report", fake_save)
    monkeypatch.setattr(trip_runner, "_set_status", fake_set_status)

    # Stub session_scope to serve the previous Report.
    class _FakeReport:
        def __init__(self, content: dict[str, Any]) -> None:
            self.content = content

    class _FakeSession:
        async def get(self, model: Any, pk: UUID) -> Any:
            return _FakeReport(state["previous_content"])

    class _FakeSessionCtx:
        async def __aenter__(self) -> _FakeSession:
            return _FakeSession()

        async def __aexit__(self, *args: Any) -> None:
            return None

    def _make_session_ctx() -> _FakeSessionCtx:
        return _FakeSessionCtx()

    monkeypatch.setattr(trip_runner, "session_scope", _make_session_ctx)

    # Disable post-cycle translations.
    async def no_translate(*args: Any, **kwargs: Any) -> None:
        return None

    monkeypatch.setattr(trip_runner, "_run_translations_and_update", no_translate)
    monkeypatch.setenv("PLUS_ONE_TRANSLATE_ENABLED", "0")

    return state


async def _collect_events(trip_id: UUID) -> list[dict[str, Any]]:
    return [ev async for ev in trip_runner.subscribe(trip_id)]


async def _run_refine_and_collect(
    trip_id: UUID,
    previous_id: UUID,
    hint: str,
    user_id: UUID,
    pre_report_id: UUID,
) -> list[dict[str, Any]]:
    """Schedule the consumer task, yield control so it can attach to the
    queue, then run the refine and await both. Without the initial
    ``await asyncio.sleep(0)`` the consumer never gets a chance to call
    ``_queues.get()`` before run_refine drops the queue in its finally,
    and the iterator yields zero events.
    """
    trip_runner.register(trip_id)
    consumer = asyncio.create_task(_collect_events(trip_id))
    await asyncio.sleep(0)  # let consumer start
    await trip_runner.run_refine(trip_id, previous_id, hint, user_id, pre_report_id)
    return await consumer


@pytest.mark.unit
async def test_run_refine_writes_refine_metadata(
    fake_db: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    trip_id = uuid4()
    previous_id = uuid4()
    pre_report_id = uuid4()
    user_id = uuid4()

    refine_mock = AsyncMock(return_value=([_joined("Arashiyama Temple")], "new tldr", 12, 34))
    monkeypatch.setattr(trip_runner, "refine_phase", refine_mock)

    trip_runner.register(trip_id)
    await trip_runner.run_refine(trip_id, previous_id, "swap to arashiyama", user_id, pre_report_id)

    assert len(fake_db["saved"]) == 1
    saved = fake_db["saved"][0]
    assert saved["report_id"] == pre_report_id
    assert saved["trip_id"] == trip_id
    assert saved["previous_report_id"] == previous_id
    assert saved["hint"] == "swap to arashiyama"
    assert saved["tl_dr"] == "new tldr"
    assert saved["input_tokens"] == 12
    assert saved["output_tokens"] == 34
    assert [i.candidate.name for i in saved["items"]] == ["Arashiyama Temple"]


@pytest.mark.unit
async def test_run_refine_emits_refine_started_event(
    fake_db: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    trip_id = uuid4()
    previous_id = uuid4()
    pre_report_id = uuid4()

    refine_mock = AsyncMock(return_value=([_joined("x")], "", 1, 1))
    monkeypatch.setattr(trip_runner, "refine_phase", refine_mock)

    events = await _run_refine_and_collect(trip_id, previous_id, "my hint", uuid4(), pre_report_id)

    names = [e["name"] for e in events]
    assert names[0] == "started"
    assert names[1] == "refine_started"
    # refine_started carries previous_report_id + hint.
    refine_ev = events[1]
    assert refine_ev["previous_report_id"] == str(previous_id)
    assert refine_ev["hint"] == "my hint"
    # final event is trip_complete with the pre-allocated id.
    final = events[-1]
    assert final["name"] == "trip_complete"
    assert final["status"] == "complete"
    assert final["report_id"] == str(pre_report_id)


@pytest.mark.unit
async def test_run_refine_aborts_on_agent_failure(
    fake_db: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    trip_id = uuid4()
    pre_report_id = uuid4()

    async def boom(**kwargs: Any) -> Any:
        raise RuntimeError("llm down")

    monkeypatch.setattr(trip_runner, "refine_phase", boom)

    events = await _run_refine_and_collect(trip_id, uuid4(), "anything", uuid4(), pre_report_id)

    names = [e["name"] for e in events]
    assert "cycle_aborted" in names
    final = events[-1]
    assert final["name"] == "trip_complete"
    assert final["status"] == "aborted"
    # No report row should have been written.
    assert fake_db["saved"] == []
    # Status flipped to aborted.
    assert fake_db["status_updates"][0][1] == "running"
    assert fake_db["status_updates"][-1][1] == "aborted"


@pytest.mark.unit
async def test_run_refine_flips_status_running_then_complete(
    fake_db: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    trip_id = uuid4()
    pre_report_id = uuid4()
    refine_mock = AsyncMock(return_value=([_joined("x")], "", 0, 0))
    monkeypatch.setattr(trip_runner, "refine_phase", refine_mock)

    trip_runner.register(trip_id)
    await trip_runner.run_refine(trip_id, uuid4(), "swap", uuid4(), pre_report_id)

    flows = [s for _, s in fake_db["status_updates"]]
    assert flows[0] == "running"
    assert flows[-1] == "complete"


@pytest.mark.unit
async def test_run_refine_passes_previous_tl_dr_to_agent(
    fake_db: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    trip_id = uuid4()
    pre_report_id = uuid4()
    refine_mock = AsyncMock(return_value=([_joined("x")], "", 0, 0))
    monkeypatch.setattr(trip_runner, "refine_phase", refine_mock)

    fake_db["previous_content"] = {
        "items": [{"candidate": {"name": "Original"}}],
        "tl_dr": "old summary",
    }

    trip_runner.register(trip_id)
    await trip_runner.run_refine(trip_id, uuid4(), "swap", uuid4(), pre_report_id)

    refine_mock.assert_awaited_once()
    kwargs = refine_mock.await_args.kwargs
    assert kwargs["previous_items"] == [{"candidate": {"name": "Original"}}]
    assert kwargs["previous_tl_dr"] == "old summary"
    assert kwargs["hint"] == "swap"
