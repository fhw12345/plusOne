"""Integration test for trip_runner translation hook.

Verifies that after ``_save_report`` succeeds, ``_run_translations_and_update``
runs (when the env switch is on) and persists ``content.translations``
into the Report row. Stubs the translator function directly so we don't
exercise the LLM.
"""

from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager
from typing import Any

import pytest

from plus_one.agents.joiner import JoinedItem
from plus_one.agents.producer import Candidate
from plus_one.services import trip_runner


class _ReportHolder:
    """Stand-in for the Report row mutated by _run_translations_and_update."""

    def __init__(self) -> None:
        self.content: dict[str, Any] = {"items": []}


class _StubSession:
    def __init__(self, report: _ReportHolder | None) -> None:
        self._report = report

    async def get(self, *_a: Any, **_kw: Any) -> Any:
        return self._report

    def add(self, _obj: object) -> None:
        return None

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def execute(self, _stmt: object) -> Any:
        return None


def _item(name: str) -> JoinedItem:
    return JoinedItem(
        candidate=Candidate(name=name, area="Tokyo"),
        classification="local_gem",
        confidence=0.8,
    )


@pytest.mark.integration
async def test_run_translations_and_update_persists_translations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When called directly, the helper writes translations onto Report.content."""
    monkeypatch.setenv("PLUS_ONE_TRANSLATE_ENABLED", "1")
    monkeypatch.setenv("PLUS_ONE_TRANSLATE_LANGS", "en,zh")

    report_holder = _ReportHolder()

    @asynccontextmanager
    async def fake_session_scope():
        yield _StubSession(report_holder)

    monkeypatch.setattr(trip_runner, "session_scope", fake_session_scope)

    async def fake_translate_items(
        items: list[JoinedItem], src_lang: str, dst_lang: str
    ) -> list[dict[str, Any]]:
        return [
            {
                "candidate": {"name": f"{i.candidate.name}-{dst_lang}", "area": "Tokyo"},
                "classification": "local_gem",
                "confidence": 0.8,
                "evidence": [],
                "summary": f"summary-{dst_lang}",
            }
            for i in items
        ]

    monkeypatch.setattr(trip_runner, "translate_items", fake_translate_items)

    items = [_item("Menya Itto"), _item("Tsuta")]
    await trip_runner._run_translations_and_update(uuid.uuid4(), items)

    assert "translations" in report_holder.content
    assert set(report_holder.content["translations"].keys()) == {"en", "zh"}
    # Batch-2q widened per-lang shape from bare-array to {items, tl_dr}.
    en_block = report_holder.content["translations"]["en"]
    zh_block = report_holder.content["translations"]["zh"]
    assert isinstance(en_block, dict)
    assert len(en_block["items"]) == 2
    assert en_block["items"][0]["candidate"]["name"] == "Menya Itto-en"
    assert zh_block["items"][1]["candidate"]["name"] == "Tsuta-zh"
    # No tl_dr was supplied → key absent (we never write empty TL;DRs).
    assert "tl_dr" not in en_block
    assert "tl_dr" not in zh_block


@pytest.mark.integration
async def test_run_translations_and_update_translates_tl_dr_when_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """batch-2q: per-lang shape becomes {items, tl_dr} when tl_dr present."""
    monkeypatch.setenv("PLUS_ONE_TRANSLATE_ENABLED", "1")
    monkeypatch.setenv("PLUS_ONE_TRANSLATE_LANGS", "en,zh")

    report_holder = _ReportHolder()

    @asynccontextmanager
    async def fake_session_scope():
        yield _StubSession(report_holder)

    monkeypatch.setattr(trip_runner, "session_scope", fake_session_scope)

    async def fake_translate_items(
        items: list[JoinedItem], src_lang: str, dst_lang: str
    ) -> list[dict[str, Any]]:
        return [
            {
                "candidate": {"name": f"{i.candidate.name}-{dst_lang}", "area": "Tokyo"},
                "classification": "local_gem",
                "confidence": 0.8,
                "evidence": [],
                "summary": f"summary-{dst_lang}",
            }
            for i in items
        ]

    async def fake_translate_tl_dr(text: str, src_lang: str, dst_lang: str) -> str:
        return f"{text} [{dst_lang}]"

    monkeypatch.setattr(trip_runner, "translate_items", fake_translate_items)
    monkeypatch.setattr(trip_runner, "translate_tl_dr", fake_translate_tl_dr)

    items = [_item("Menya Itto")]
    await trip_runner._run_translations_and_update(
        uuid.uuid4(), items, "kyoto's still a place where good tea matters."
    )

    en_block = report_holder.content["translations"]["en"]
    zh_block = report_holder.content["translations"]["zh"]
    assert en_block["tl_dr"].endswith("[en]")
    assert zh_block["tl_dr"].endswith("[zh]")
    assert len(en_block["items"]) == 1


@pytest.mark.integration
async def test_translate_disabled_skips_translations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``PLUS_ONE_TRANSLATE_ENABLED=0`` short-circuits the runner hook."""
    monkeypatch.setenv("PLUS_ONE_TRANSLATE_ENABLED", "0")
    assert trip_runner._translate_enabled() is False


@pytest.mark.integration
async def test_translate_enabled_default_true(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PLUS_ONE_TRANSLATE_ENABLED", raising=False)
    assert trip_runner._translate_enabled() is True


@pytest.mark.integration
async def test_translate_enabled_various_falsy_values(monkeypatch: pytest.MonkeyPatch) -> None:
    for val in ("0", "false", "False", "no"):
        monkeypatch.setenv("PLUS_ONE_TRANSLATE_ENABLED", val)
        assert trip_runner._translate_enabled() is False, val


@pytest.mark.integration
async def test_translate_langs_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PLUS_ONE_TRANSLATE_LANGS", raising=False)
    assert trip_runner._translate_langs() == ("en", "zh")


@pytest.mark.integration
async def test_translate_langs_custom(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLUS_ONE_TRANSLATE_LANGS", "en, fr,  ja")
    assert trip_runner._translate_langs() == ("en", "fr", "ja")


@pytest.mark.integration
async def test_translation_batch_timeout_skips_slow_language(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PLUS_ONE_TRANSLATE_LANGS", "zh")
    monkeypatch.setenv("PLUS_ONE_TRANSLATE_TIMEOUT_S", "1")

    called = False

    @asynccontextmanager
    async def fake_session_scope():
        nonlocal called
        called = True
        yield _StubSession(_ReportHolder())

    async def slow_translate_items(
        items: list[JoinedItem], src_lang: str, dst_lang: str
    ) -> list[dict[str, Any]]:
        del items, src_lang, dst_lang
        await asyncio.sleep(2)
        return []

    monkeypatch.setattr(trip_runner, "session_scope", fake_session_scope)
    monkeypatch.setattr(trip_runner, "translate_items", slow_translate_items)

    await trip_runner._run_translations_and_update(uuid.uuid4(), [_item("Menya Itto")])

    assert called is False


@pytest.mark.integration
async def test_run_translations_empty_items_no_op(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty items list short-circuits without DB access."""
    called = False

    @asynccontextmanager
    async def fake_session_scope():
        nonlocal called
        called = True
        yield _StubSession(None)

    monkeypatch.setattr(trip_runner, "session_scope", fake_session_scope)

    await trip_runner._run_translations_and_update(uuid.uuid4(), [])
    assert called is False


@pytest.mark.integration
async def test_run_translations_missing_report_logs_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the Report row vanished (race / test stub), the helper warns + exits."""

    @asynccontextmanager
    async def fake_session_scope():
        yield _StubSession(None)  # session.get(Report, id) returns None

    monkeypatch.setattr(trip_runner, "session_scope", fake_session_scope)

    async def fake_translate_items(
        items: list[JoinedItem], src_lang: str, dst_lang: str
    ) -> list[dict[str, Any]]:
        return [i.model_dump(mode="json") for i in items]

    monkeypatch.setattr(trip_runner, "translate_items", fake_translate_items)

    # Should not raise.
    await trip_runner._run_translations_and_update(uuid.uuid4(), [_item("X")])
