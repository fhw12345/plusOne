"""Tests for the domain agents (Producer / Joiner / Controller).

These exercise the agents through the framework's protocols using the
mock_llm fixture. No real LLM, no real DB, no real network.
"""

from __future__ import annotations

import json
import sys
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

from plus_one.agents.controller import controller
from plus_one.agents.joiner import JoinedItem, joiner
from plus_one.agents.producer import Candidate, producer
from plus_one.agents.types import Classification, Evidence
from plus_one.core.agents.framework.types import AgentContext

if TYPE_CHECKING:
    from plus_one.core.llm.testing import MockLLMProvider
    from plus_one.core.tools.place_images import PlaceImageInput

joiner_mod = sys.modules[joiner.__module__]


# === Producer ============================================================


@pytest.mark.unit
async def test_producer_returns_candidates_from_mock_llm(
    mock_llm: MockLLMProvider,
) -> None:
    payload = {
        "candidates": [
            {
                "name": "Menya Itto",
                "area": "Shinkoiwa",
                "style": "tonkotsu",
                "rationale": "Cult favorite among locals",
            },
            {
                "name": "Ichiran Shibuya",
                "area": "Shibuya",
                "style": "tonkotsu chain",
                "rationale": "Likely tourist trap; worth flagging",
            },
        ]
    }
    mock_llm.queue_response(
        role="producer_agent",
        text=json.dumps(payload),
        parsed_data=payload,
    )

    ctx = AgentContext(query="Tokyo tonkotsu ramen")
    result = await producer(ctx)

    assert len(result.payload) == 2
    assert result.payload[0].name == "Menya Itto"
    assert result.payload[1].area == "Shibuya"
    # Notes should mention the routed skills.
    assert "ramen_basics" in result.notes


@pytest.mark.unit
async def test_producer_handles_empty_llm_payload_gracefully(
    mock_llm: MockLLMProvider,
) -> None:
    mock_llm.queue_response(
        role="producer_agent",
        text='{"candidates": []}',
        parsed_data={"candidates": []},
    )
    result = await producer(AgentContext(query="anything"))
    assert result.payload == []


# === Joiner ==============================================================


@pytest.mark.unit
async def test_joiner_classifies_candidates(mock_llm: MockLLMProvider) -> None:
    cand = Candidate(name="Menya Itto", area="Shinkoiwa", style="tonkotsu", rationale="cult fav")
    output = {
        "items": [
            {
                "candidate": cand.model_dump(),
                "classification": "local_gem",
                "classification_en": "local_gem",
                "classification_zh": "local_gem",
                "confidence": 0.85,
                "evidence": [
                    {
                        "source": "reddit",
                        "url": "https://reddit.com/r/ramen/abc",
                        "snippet": "Best tonkotsu in Tokyo, 90 min wait worth it",
                        "sentiment": 0.9,
                    }
                ],
                "summary": "Strongly recommended by locals.",
            }
        ]
    }
    mock_llm.queue_response(
        role="joiner_agent",
        text=json.dumps(output),
        parsed_data=output,
    )

    result = await joiner([cand], AgentContext(query="Tokyo ramen"))

    assert len(result.payload.items) == 1
    item = result.payload.items[0]
    assert item.classification == "local_gem"
    assert item.classification_en == "local_gem"
    assert item.classification_zh == "local_gem"
    assert item.confidence == 0.85
    # Per-lang agreement → divergence_score is exactly 0.0 (Python-side
    # overwrite of whatever the LLM emitted for the field).
    assert item.divergence_score == 0.0
    assert len(item.evidence) == 1
    assert isinstance(item.evidence[0], Evidence)


@pytest.mark.unit
async def test_joiner_fills_image_url_from_place_image_fixture(
    mock_llm: MockLLMProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PLUS_ONE_TOOLS_MODE", "fixture")
    cand = Candidate(
        name="Ichiran Shibuya",
        area="Shibuya",
        style="tonkotsu chain",
        rationale="well-known ramen chain",
    )
    output = {
        "items": [
            {
                "candidate": cand.model_dump(),
                "classification": "tourist_trap",
                "confidence": 0.7,
                "evidence": [],
                "summary": "Famous and convenient, but not a hidden local pick.",
            }
        ]
    }
    mock_llm.queue_response(role="joiner_agent", text=json.dumps(output), parsed_data=output)

    class _Image:
        image_url = "https://img.example/ichiran.jpg"
        source = "fixture"

    async def fake_resolve_image(self: object, args: object) -> _Image:
        del self, args
        return _Image()

    monkeypatch.setattr(joiner_mod.PlaceImageResolver, "resolve", fake_resolve_image)

    result = await joiner([cand], AgentContext(query="Tokyo tonkotsu ramen"))

    assert len(result.payload.items) == 1
    assert result.payload.items[0].image_url == "https://img.example/ichiran.jpg"
    assert result.payload.items[0].image_source == "fixture"


@pytest.mark.unit
async def test_joiner_uses_xhs_image_before_place_image_lookup(
    mock_llm: MockLLMProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cand = Candidate(
        name="M50 Creative Park",
        area="Shanghai",
        style="contemporary art",
        rationale="warehouse gallery cluster",
    )
    output = {
        "items": [
            {
                "candidate": cand.model_dump(),
                "classification": "local_gem",
                "confidence": 0.72,
                "evidence": [],
                "summary": "A strong art stop with recent XHS visual evidence.",
            }
        ]
    }
    mock_llm.queue_response(role="joiner_agent", text=json.dumps(output), parsed_data=output)

    async def fake_run_tool_calls(*args: object, **kwargs: object) -> list[object]:
        del args, kwargs
        from plus_one.core.agents.framework.tools import ToolResult

        return [
            ToolResult(tool="reddit_search", output=[]),
            ToolResult(
                tool="xhs_search",
                output=[
                    SimpleNamespace(
                        url="https://www.xiaohongshu.com/explore/xhs_1",
                        title="M50 展览",
                        body="最近拍照和看展都不错。",
                        images=("https://sns-webpic-qc.xhscdn.com/m50-photo!webp",),
                    )
                ],
            ),
            ToolResult(tool="places_search", output=[]),
        ]

    async def explode_resolve_image(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise AssertionError("XHS image should avoid place image lookup")

    monkeypatch.setattr(joiner_mod, "run_tool_calls", fake_run_tool_calls)
    monkeypatch.setattr(joiner_mod.PlaceImageResolver, "resolve", explode_resolve_image)

    result = await joiner([cand], AgentContext(query="Shanghai art"))

    assert result.payload.items[0].image_url == "https://sns-webpic-qc.xhscdn.com/m50-photo!webp"
    assert result.payload.items[0].image_source == "xhs"


@pytest.mark.unit
async def test_joiner_image_hint_keeps_candidate_food_style(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cand = Candidate(
        name="Menya Itto",
        area="Tokyo",
        style="tsukemen thick fish pork broth",
        rationale="ramen shop with dense soup",
    )

    from plus_one.core.agents.framework.tools import ToolResult

    results = [
        ToolResult(
            tool="places_search",
            output=[SimpleNamespace(photo_url=None, categories=("Indian", "Japanese Curry"))],
        )
    ]
    seen: list[object] = []

    class _Image:
        image_url = "https://img.example/menya-itto.jpg"
        source = "place_image"

    class _Resolver:
        async def resolve(self, args: object) -> _Image:
            seen.append(args)
            return _Image()

    image = await joiner_mod._resolve_candidate_image(cand, results, "Tokyo", _Resolver())

    assert image is not None
    assert image.url == "https://img.example/menya-itto.jpg"
    assert image.source == "place_image"
    assert seen
    args = seen[0]
    assert args.category.startswith("ramen")
    assert "tsukemen" in args.category
    assert "Indian" in args.category
    assert "dense soup" not in args.category


@pytest.mark.unit
async def test_joiner_retries_broad_ramen_image_category() -> None:
    cand = Candidate(
        name="Nakiryu",
        area="Tokyo",
        style="Shoyu / tantanmen, Michelin",
        rationale="Michelin ramen away from the main tourist cores",
    )
    from plus_one.core.agents.framework.tools import ToolResult

    results = [ToolResult(tool="places_search", output=[])]
    seen: list[object] = []

    class _Image:
        image_url = "https://img.example/nakiryu.jpg"
        source = "openverse:flickr"

    class _Resolver:
        async def resolve(self, args: PlaceImageInput) -> _Image | None:
            seen.append(args)
            if args.category == "ramen":
                return _Image()
            return None

    image = await joiner_mod._resolve_candidate_image(cand, results, "Tokyo", _Resolver())

    assert image is not None
    assert image.url == "https://img.example/nakiryu.jpg"
    assert [args.category for args in seen] == [
        "ramen Shoyu / tantanmen Michelin",
        "ramen",
    ]


@pytest.mark.unit
async def test_joiner_computes_divergence_for_disagreement_case(
    mock_llm: MockLLMProvider,
) -> None:
    """LLM may emit a bogus divergence_score; Python-side recompute wins."""
    cand = Candidate(name="Menya Itto", rationale="r")
    output = {
        "items": [
            {
                "candidate": cand.model_dump(),
                "classification": "local_gem",
                "classification_en": "local_gem",
                "classification_zh": "tourist_trap",
                "confidence": 0.7,
                "evidence": [],
                "summary": "EN raves, ZH says trap",
                # Deliberately wrong — must be overwritten to 1.0.
                "divergence_score": 0.1,
            }
        ]
    }
    mock_llm.queue_response(
        role="joiner_agent",
        text=json.dumps(output),
        parsed_data=output,
    )

    result = await joiner([cand], AgentContext(query="Tokyo"))
    assert len(result.payload.items) == 1
    item = result.payload.items[0]
    assert item.classification_en == "local_gem"
    assert item.classification_zh == "tourist_trap"
    assert item.divergence_score == 1.0


@pytest.mark.unit
async def test_joiner_handles_null_per_language_classification(
    mock_llm: MockLLMProvider,
) -> None:
    """When one side has no per-language signal the LLM must emit null;
    divergence_score must stay 0.0 because the disagreement gate requires
    both sides non-null."""
    cand = Candidate(name="Menya Itto", rationale="r")
    output = {
        "items": [
            {
                "candidate": cand.model_dump(),
                "classification": "local_gem",
                "classification_en": "local_gem",
                "classification_zh": None,
                "confidence": 0.6,
                "evidence": [],
                "summary": "no xhs hits",
            }
        ]
    }
    mock_llm.queue_response(
        role="joiner_agent",
        text=json.dumps(output),
        parsed_data=output,
    )

    result = await joiner([cand], AgentContext(query="Tokyo"))
    assert len(result.payload.items) == 1
    item = result.payload.items[0]
    assert item.classification_en == "local_gem"
    assert item.classification_zh is None
    assert item.divergence_score == 0.0


@pytest.mark.unit
async def test_joiner_handles_empty_candidate_list(
    mock_llm: MockLLMProvider,
) -> None:
    mock_llm.queue_response(
        role="joiner_agent",
        text='{"items": []}',
        parsed_data={"items": []},
    )
    result = await joiner([], AgentContext(query="x"))
    assert result.payload.items == []


@pytest.mark.unit
async def test_joiner_repairs_llm_paraphrased_candidate_name(
    mock_llm: MockLLMProvider,
) -> None:
    """Reviewer B3: if the LLM paraphrases the candidate name, we replace
    it with the original Producer Candidate so name/area/style cannot
    silently drift between Producer and the report."""
    cand = Candidate(name="Menya Itto", area="Shinkoiwa", style="tonkotsu", rationale="r")
    output = {
        "items": [
            {
                # LLM "helpfully" added a paren — original was "Menya Itto"
                "candidate": {
                    "name": "Menya Itto",  # case preserved on echo
                    "area": "WRONG",  # LLM mangled area
                    "style": "WRONG",
                    "rationale": "WRONG",
                },
                "classification": "local_gem",
                "confidence": 0.8,
                "evidence": [],
                "summary": "ok",
            }
        ]
    }
    mock_llm.queue_response(
        role="joiner_agent",
        text=json.dumps(output),
        parsed_data=output,
    )
    result = await joiner([cand], AgentContext(query="Tokyo"))
    assert len(result.payload.items) == 1
    # Restored from the original Candidate
    assert result.payload.items[0].candidate.area == "Shinkoiwa"
    assert result.payload.items[0].candidate.style == "tonkotsu"


@pytest.mark.unit
async def test_joiner_drops_hallucinated_candidates(
    mock_llm: MockLLMProvider,
) -> None:
    """LLM returned a candidate name that wasn't in the Producer's list.
    Drop it rather than fabricate a Candidate from thin air."""
    cand = Candidate(name="Menya Itto", rationale="r")
    output = {
        "items": [
            {
                "candidate": {"name": "Menya Itto", "rationale": "r"},
                "classification": "local_gem",
                "confidence": 0.8,
                "evidence": [],
                "summary": "ok",
            },
            {
                "candidate": {"name": "Made-up Place", "rationale": "r"},
                "classification": "local_gem",
                "confidence": 0.9,
                "evidence": [],
                "summary": "fake",
            },
        ]
    }
    mock_llm.queue_response(
        role="joiner_agent",
        text=json.dumps(output),
        parsed_data=output,
    )
    result = await joiner([cand], AgentContext(query="Tokyo"))
    assert len(result.payload.items) == 1
    assert result.payload.items[0].candidate.name == "Menya Itto"
    assert "dropped_unknown=1" in result.notes


@pytest.mark.unit
async def test_joiner_accepts_recommendations_alias_from_llm(
    mock_llm: MockLLMProvider,
) -> None:
    cand = Candidate(name="Menya Itto", rationale="r")
    item = {
        "candidate": cand.model_dump(),
        "classification": "local_gem",
        "confidence": 0.8,
        "evidence": [],
        "summary": "ok",
    }
    mock_llm.queue_response(
        role="joiner_agent",
        text=json.dumps({"recommendations": [item]}),
        parsed_data={"recommendations": [item]},
    )

    result = await joiner([cand], AgentContext(query="Tokyo"))

    assert len(result.payload.items) == 1
    assert result.payload.items[0].candidate.name == "Menya Itto"


@pytest.mark.unit
async def test_joiner_accepts_top_level_array_from_llm(
    mock_llm: MockLLMProvider,
) -> None:
    cand = Candidate(name="Menya Itto", rationale="r")
    item = {
        "candidate": cand.model_dump(),
        "classification": "local_gem",
        "confidence": 0.8,
        "evidence": [],
        "summary": "ok",
    }
    mock_llm.queue_response(
        role="joiner_agent",
        text=json.dumps([item]),
        parsed_data=[item],
    )

    result = await joiner([cand], AgentContext(query="Tokyo"))

    assert len(result.payload.items) == 1
    assert result.payload.items[0].classification == "local_gem"


# === Joiner v3 (batch-2p + batch-2q) ====================================


@pytest.mark.unit
async def test_joiner_v3_prompt_loads_without_unbalanced_braces(
    mock_llm: MockLLMProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """v3.md must parse via the load_prompt path with the two `.replace`
    placeholders, including the literal JSON braces in the output-format
    block (the joiner uses ``.replace`` precisely so those stay safe).
    """
    monkeypatch.setenv("PLUS_ONE_TOOLS_MODE", "fixture")
    cand = Candidate(name="Menya Itto", rationale="r")
    mock_llm.queue_response(
        role="joiner_agent",
        text='{"items": [], "tl_dr": null}',
        parsed_data={"items": [], "tl_dr": None},
    )
    result = await joiner([cand], AgentContext(query="Tokyo"))
    assert len(result.payload.items) == 1
    assert result.payload.items[0].classification == "insufficient"
    assert "fallback_items=1" in result.notes
    assert result.payload.tl_dr is not None


@pytest.mark.unit
async def test_joiner_empty_llm_fallback_uses_tool_evidence(
    mock_llm: MockLLMProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When Maestro returns zero usable joiner items, fallback cards must
    still be grounded in fetched tool evidence instead of empty placeholders.
    """
    cand = Candidate(name="Menya Itto", area="Shinkoiwa", style="tsukemen", rationale="r")
    mock_llm.queue_response(
        role="joiner_agent",
        text='{"items": [], "tl_dr": null}',
        parsed_data={"items": [], "tl_dr": None},
    )

    async def fake_images(*args: object, **kwargs: object) -> dict[str, object | None]:
        del args, kwargs
        return {"menya itto": joiner_mod.ImageRef(url="https://img.example/itto.jpg", source="test")}

    async def fake_run_tool_calls(*args: object, **kwargs: object) -> list[object]:
        del args, kwargs
        from plus_one.core.agents.framework.tools import ToolResult

        return [
            ToolResult(
                tool="reddit_search",
                output=[
                    SimpleNamespace(
                        permalink="https://reddit.example/itto",
                        title="Best tsukemen in Tokyo",
                        body="Menya Itto is the real deal, a local favorite and worth the wait.",
                    )
                ],
            ),
            ToolResult(
                tool="xhs_search",
                output=[
                        SimpleNamespace(
                            url="https://www.xiaohongshu.com/explore/xhs_1",
                            title="东京 Menya Itto 拉面推荐",
                            body="Menya Itto 本地人排队, 很值得去, 推荐避开周末。",
                        )
                    ],
                ),
            ToolResult(
                tool="places_search",
                output=[],
            ),
        ]

    monkeypatch.setattr(joiner_mod, "_resolve_candidate_images", fake_images)
    monkeypatch.setattr(joiner_mod, "run_tool_calls", fake_run_tool_calls)

    result = await joiner([cand], AgentContext(query="Tokyo ramen"))

    item = result.payload.items[0]
    assert item.classification == "local_gem"
    assert item.classification_en == "local_gem"
    assert item.classification_zh == "local_gem"
    assert item.confidence > 0
    assert len(item.evidence) >= 2
    assert {ev.source for ev in item.evidence} >= {"reddit", "xiaohongshu"}
    assert item.summary
    assert "Rule fallback" not in item.summary
    assert item.image_url == "https://img.example/itto.jpg"
    assert item.image_source == "test"
    assert "fallback_items=1" in result.notes


@pytest.mark.unit
async def test_joiner_filters_wrong_city_and_wrong_place_evidence(
    mock_llm: MockLLMProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cand = Candidate(name="Menya Itto", area="Tokyo", style="tsukemen", rationale="r")
    mock_llm.queue_response(
        role="joiner_agent",
        text='{"items": [], "tl_dr": null}',
        parsed_data={"items": [], "tl_dr": None},
    )

    async def fake_images(*args: object, **kwargs: object) -> dict[str, object | None]:
        del args, kwargs
        return {}

    async def fake_run_tool_calls(*args: object, **kwargs: object) -> list[object]:
        del args, kwargs
        from plus_one.core.agents.framework.tools import ToolResult

        return [
            ToolResult(tool="reddit_search", output=[]),
            ToolResult(
                tool="xhs_search",
                output=[
                    SimpleNamespace(
                        url="https://www.xiaohongshu.com/explore/osaka",
                        title="大阪 Menya Itto 开业啦",
                        body="大阪新店排队很多。",
                    ),
                    SimpleNamespace(
                        url="https://www.xiaohongshu.com/explore/tokyo",
                        title="东京 Menya Itto 沾面",
                        body="东京本店工作日去, 本地朋友带路, 点了沾面, 排队30分钟, 汤底浓但是偏咸。",
                    ),
                ],
            ),
            ToolResult(
                tool="places_search",
                output=[
                    SimpleNamespace(
                        name="Menya Syo",
                        formatted_address="西新宿7-22-34, 新宿区, 東京都",
                    ),
                    SimpleNamespace(
                        name="Menya Itto",
                        formatted_address="東新小岩1-4-17, 葛飾区, 東京都",
                    ),
                ],
            ),
        ]

    monkeypatch.setattr(joiner_mod, "_resolve_candidate_images", fake_images)
    monkeypatch.setattr(joiner_mod, "run_tool_calls", fake_run_tool_calls)

    result = await joiner([cand], AgentContext(query="Tokyo ramen"))

    snippets = [ev.snippet for ev in result.payload.items[0].evidence]
    assert any("东京 Menya Itto" in snippet for snippet in snippets)
    assert any("Menya Itto" in snippet and "葛飾" in snippet for snippet in snippets)
    assert all("大阪" not in snippet for snippet in snippets)
    assert all("Menya Syo" not in snippet for snippet in snippets)


@pytest.mark.unit
async def test_joiner_mixed_fallback_is_not_go_signal(
    mock_llm: MockLLMProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cand = Candidate(name="Afuri", area="Tokyo", style="yuzu ramen", rationale="r")
    mock_llm.queue_response(
        role="joiner_agent",
        text='{"items": [], "tl_dr": null}',
        parsed_data={"items": [], "tl_dr": None},
    )

    async def fake_images(*args: object, **kwargs: object) -> dict[str, object | None]:
        del args, kwargs
        return {}

    async def fake_run_tool_calls(*args: object, **kwargs: object) -> list[object]:
        del args, kwargs
        from plus_one.core.agents.framework.tools import ToolResult

        return [
            ToolResult(tool="reddit_search", output=[]),
            ToolResult(
                tool="xhs_search",
                output=[
                    SimpleNamespace(
                        url="https://www.xiaohongshu.com/explore/afuri",
                        title="东京 Afuri 拉面真实反馈",
                        body="很多人推荐也排队, 但柚子拉面避雷, 不好吃, 汤底一般。",
                    )
                ],
            ),
            ToolResult(tool="places_search", output=[]),
        ]

    monkeypatch.setattr(joiner_mod, "_resolve_candidate_images", fake_images)
    monkeypatch.setattr(joiner_mod, "run_tool_calls", fake_run_tool_calls)

    result = await joiner([cand], AgentContext(query="Tokyo ramen"))

    item = result.payload.items[0]
    assert item.classification == "neutral"
    assert item.confidence <= 0.62
    assert "split" in item.summary


@pytest.mark.unit
async def test_joiner_synthesises_tldr_when_llm_omits_it(
    mock_llm: MockLLMProvider,
) -> None:
    cand = Candidate(name="Menya Itto", area="Tokyo", style="tsukemen", rationale="r")
    output = {
        "items": [
            {
                "candidate": cand.model_dump(),
                "classification": "local_gem",
                "confidence": 0.8,
                "evidence": [],
                "summary": "good",
            }
        ],
        "tl_dr": None,
    }
    mock_llm.queue_response(role="joiner_agent", text=json.dumps(output), parsed_data=output)

    result = await joiner([cand], AgentContext(query="Tokyo ramen"))

    assert result.payload.tl_dr is not None
    assert "Menya Itto" in result.payload.tl_dr


@pytest.mark.unit
async def test_joiner_llm_timeout_falls_back_to_tool_evidence(
    mock_llm: MockLLMProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cand = Candidate(name="Menya Itto", area="Shinkoiwa", style="tsukemen", rationale="r")
    monkeypatch.setenv("PLUS_ONE_JOINER_LLM_TIMEOUT_S", "1")

    async def slow_complete(*args: object, **kwargs: object) -> object:
        del args, kwargs
        import asyncio as _asyncio

        await _asyncio.sleep(2)
        raise AssertionError("timeout should cancel before this point")

    class SlowProvider:
        async def complete(self, **kwargs: object) -> object:
            del kwargs
            return await slow_complete()

    monkeypatch.setattr(joiner_mod.llm_factory, "get_llm_provider", lambda role: SlowProvider())

    async def fake_images(*args: object, **kwargs: object) -> dict[str, object | None]:
        del args, kwargs
        return {"menya itto": joiner_mod.ImageRef(url="https://img.example/itto.jpg", source="test")}

    async def fake_run_tool_calls(*args: object, **kwargs: object) -> list[object]:
        del args, kwargs
        from plus_one.core.agents.framework.tools import ToolResult

        return [
            ToolResult(
                tool="reddit_search",
                output=[
                    SimpleNamespace(
                        permalink="https://reddit.example/itto",
                        title="Best tsukemen in Tokyo",
                        body="Menya Itto is the real deal, a local favorite and worth the wait.",
                    )
                ],
            )
        ]

    monkeypatch.setattr(joiner_mod, "_resolve_candidate_images", fake_images)
    monkeypatch.setattr(joiner_mod, "run_tool_calls", fake_run_tool_calls)

    result = await joiner([cand], AgentContext(query="Tokyo ramen"))

    item = result.payload.items[0]
    assert item.classification == "local_gem"
    assert len(item.evidence) == 1
    assert item.image_url == "https://img.example/itto.jpg"
    assert item.image_source == "test"
    assert "fallback_items=1" in result.notes


@pytest.mark.unit
async def test_joiner_v3_passes_through_match_scores(
    mock_llm: MockLLMProvider,
) -> None:
    """LLM emits a fully-populated match_scores map keyed by the trip's
    party; joiner accepts it unchanged (after the clamp/fill pass)."""
    import uuid as _uuid

    from plus_one.core.agents.framework.types import (
        CompanionForContext,
        UserProfileForContext,
    )

    user_id = _uuid.uuid4()
    alice_id = _uuid.uuid4()
    cand = Candidate(name="Menya Itto", rationale="r")
    output = {
        "tl_dr": "tokyo's a place for counters not chains. nishikoiwa's the move.",
        "items": [
            {
                "candidate": cand.model_dump(),
                "classification": "local_gem",
                "confidence": 0.8,
                "evidence": [],
                "summary": "ok",
                "match_scores": {str(user_id): 0.8, str(alice_id): 0.3},
            }
        ],
    }
    mock_llm.queue_response(role="joiner_agent", text="{}", parsed_data=output)
    ctx = AgentContext(
        query="Tokyo",
        user_profile=UserProfileForContext(id=user_id, loves=("ramen",)),
        selected_companions=[CompanionForContext(id=alice_id, name="alice")],
    )
    result = await joiner([cand], ctx)
    item = result.payload.items[0]
    assert item.match_scores is not None
    assert item.match_scores[user_id] == 0.8
    assert item.match_scores[alice_id] == 0.3
    assert result.payload.tl_dr is not None
    assert result.payload.tl_dr.startswith("tokyo")


@pytest.mark.unit
async def test_joiner_v3_drops_hallucinated_score_keys_and_fills_missing(
    mock_llm: MockLLMProvider,
) -> None:
    """LLM hallucinates a UUID + omits a real one + emits out-of-range. We
    drop the hallucination, fill the missing key with 0.5, and clamp."""
    import uuid as _uuid

    from plus_one.core.agents.framework.types import (
        CompanionForContext,
        UserProfileForContext,
    )

    user_id = _uuid.uuid4()
    alice_id = _uuid.uuid4()
    bogus_id = _uuid.uuid4()
    cand = Candidate(name="Menya Itto", rationale="r")
    output = {
        "items": [
            {
                "candidate": cand.model_dump(),
                "classification": "local_gem",
                "confidence": 0.8,
                "evidence": [],
                "summary": "ok",
                # user gets out-of-range, alice is missing, bogus is hallucinated.
                "match_scores": {str(user_id): 1.7, str(bogus_id): 0.5},
            }
        ]
    }
    mock_llm.queue_response(role="joiner_agent", text="{}", parsed_data=output)
    ctx = AgentContext(
        query="Tokyo",
        user_profile=UserProfileForContext(id=user_id),
        selected_companions=[CompanionForContext(id=alice_id, name="alice")],
    )
    result = await joiner([cand], ctx)
    item = result.payload.items[0]
    assert item.match_scores is not None
    assert set(item.match_scores.keys()) == {user_id, alice_id}
    assert item.match_scores[user_id] == 1.0  # clamped
    assert item.match_scores[alice_id] == 0.5  # filled default


@pytest.mark.unit
async def test_joiner_v3_no_party_identity_skips_match_scores(
    mock_llm: MockLLMProvider,
) -> None:
    """When ctx has no user/companion ids (unit-test style), match_scores
    must coerce to None — there's nothing to key against."""
    cand = Candidate(name="Menya Itto", rationale="r")
    output = {
        "items": [
            {
                "candidate": cand.model_dump(),
                "classification": "local_gem",
                "confidence": 0.8,
                "evidence": [],
                "summary": "ok",
                "match_scores": {"00000000-0000-4000-8000-000000000001": 0.7},
            }
        ]
    }
    mock_llm.queue_response(role="joiner_agent", text="{}", parsed_data=output)
    result = await joiner([cand], AgentContext(query="Tokyo"))
    item = result.payload.items[0]
    assert item.match_scores is None


# === Controller ==========================================================


def _joined(name: str, classification: Classification, confidence: float = 0.7) -> JoinedItem:
    """Tiny helper to build a JoinedItem for controller tests."""
    return JoinedItem(
        candidate=Candidate(name=name, rationale="r"),
        classification=classification,
        confidence=confidence,
    )


@pytest.mark.unit
async def test_controller_rule_stops_when_thresholds_met(
    mock_llm: MockLLMProvider,
) -> None:
    items = [_joined(f"gem_{i}", "local_gem") for i in range(5)] + [
        _joined(f"trap_{i}", "tourist_trap") for i in range(3)
    ]
    ctx = AgentContext(query="x", max_depth=4)

    result = await controller(items, ctx)
    assert result.payload.should_continue is False
    assert "sufficient" in result.payload.reasoning
    # Rule path: no LLM call.
    assert mock_llm.calls_for_role("controller_agent") == []


@pytest.mark.unit
async def test_controller_rule_continues_when_too_many_insufficient(
    mock_llm: MockLLMProvider,
) -> None:
    items = [_joined(f"x_{i}", "insufficient") for i in range(6)] + [_joined("g", "local_gem")]
    ctx = AgentContext(query="x", max_depth=4)

    result = await controller(items, ctx)
    assert result.payload.should_continue is True
    assert "insufficient" in result.payload.reasoning
    assert mock_llm.calls_for_role("controller_agent") == []


@pytest.mark.unit
async def test_controller_rule_stops_after_one_round_with_enough_usable_items(
    mock_llm: MockLLMProvider,
) -> None:
    items = [_joined(f"gem_{i}", "local_gem") for i in range(3)] + [
        _joined(f"neutral_{i}", "neutral") for i in range(2)
    ]
    ctx = AgentContext(query="x", max_depth=4)

    result = await controller(items, ctx)

    assert result.payload.should_continue is False
    assert "usable coverage" in result.payload.reasoning
    assert mock_llm.calls_for_role("controller_agent") == []


@pytest.mark.unit
async def test_controller_falls_back_to_llm_for_ambiguous_state(
    mock_llm: MockLLMProvider,
) -> None:
    """No threshold fires → LLM is asked."""
    items = [
        _joined("g1", "local_gem"),
        _joined("t1", "tourist_trap"),
        _joined("n1", "neutral"),
    ]
    payload = {
        "should_continue": True,
        "reasoning": "Coverage is mixed and confidences are low.",
        "summary": "Found 1 gem, 1 trap, 1 neutral so far.",
    }
    mock_llm.queue_response(
        role="controller_agent",
        text=json.dumps(payload),
        parsed_data=payload,
    )

    ctx = AgentContext(query="x", max_depth=4)
    result = await controller(items, ctx)
    assert result.payload.should_continue is True
    assert result.payload.summary.startswith("Found")
    assert len(mock_llm.calls_for_role("controller_agent")) == 1


@pytest.mark.unit
async def test_controller_does_not_short_circuit_on_depth_alone(
    mock_llm: MockLLMProvider,
) -> None:
    """Reviewer B2: depth-cap is the cycle main loop's job. The Controller
    should make its decision based on coverage, not duplicate the depth
    check (which previously fired off-by-one and discarded a valid round
    of joined results). At depth = max_depth - 1 with ambiguous coverage,
    Controller still asks the LLM."""
    items = [
        _joined("g1", "local_gem"),
        _joined("t1", "tourist_trap"),
    ]
    payload = {
        "should_continue": False,
        "reasoning": "Coverage looks good for this query.",
        "summary": "1 gem, 1 trap.",
    }
    mock_llm.queue_response(
        role="controller_agent",
        text=json.dumps(payload),
        parsed_data=payload,
    )

    ctx = AgentContext(query="x", max_depth=4)
    ctx.depth = 3  # cycle main loop will cap on next iteration
    result = await controller(items, ctx)
    # Now the LLM is consulted (not short-circuited) — coverage is genuinely
    # ambiguous at this depth.
    assert len(mock_llm.calls_for_role("controller_agent")) == 1
    assert result.payload.should_continue is False
