"""Joiner agent: fetches multi-source evidence per candidate and classifies."""

from __future__ import annotations

import asyncio
import os
import re
from typing import Any, cast
from uuid import UUID  # noqa: TC003 - runtime use as Pydantic field annotation

import structlog
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from plus_one.agents._divergence import divergence_score
from plus_one.agents._scoring import render_person_roster, validate_match_scores
from plus_one.agents.preferences import render_preferences_section
from plus_one.agents.producer import Candidate
from plus_one.agents.prompts import load_prompt
from plus_one.agents.types import Classification, Evidence
from plus_one.core.agents.framework.tools import Tool, ToolCall, ToolRegistry, run_tool_calls
from plus_one.core.agents.framework.types import AgentContext, PhaseResult
from plus_one.core.llm import Message
from plus_one.core.llm import factory as llm_factory
from plus_one.core.llm.parsers import extract_json_with_fallback
from plus_one.core.llm.provider import Response, Usage
from plus_one.core.tools import (
    FoursquarePlacesSearchTool,
    RedditSearchTool,
    XHSSearchTool,
)
from plus_one.core.tools.place_images import PlaceImageInput, PlaceImageResolver
from plus_one.core.tools.xiaohongshu import assess_xhs_authenticity

logger = structlog.get_logger()


class JoinedItem(BaseModel):
    """Producer Candidate enriched with classification + evidence."""

    model_config = ConfigDict(frozen=True)

    candidate: Candidate
    classification: Classification
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: tuple[Evidence, ...] = Field(default=())
    summary: str = Field(default="", max_length=500)
    classification_en: Classification | None = None
    classification_zh: Classification | None = None
    divergence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    match_scores: dict[UUID, float] | None = Field(default=None)
    image_url: str | None = Field(default=None)
    image_source: str | None = Field(default=None)
    long_description: str = Field(default="", max_length=2400)


class ImageRef(BaseModel):
    """Resolved card image plus where it came from."""

    model_config = ConfigDict(frozen=True)

    url: str
    source: str


class JoinerPayload(BaseModel):
    """Structured joiner payload with items plus report-level TL;DR."""

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    items: list[JoinedItem] = Field(default_factory=list)
    tl_dr: str | None = Field(default=None)


class _JoinerOutput(BaseModel):
    items: list[JoinedItem] = Field(default_factory=list, max_length=30)
    tl_dr: str | None = Field(default=None)


class _RawJoinerOutput(BaseModel):
    """Lenient top-level joiner shape; individual items are repaired below."""

    model_config = ConfigDict(extra="allow")

    items: list[Any] = Field(default_factory=list, max_length=30)
    tl_dr: Any = Field(default=None)

    @model_validator(mode="before")
    @classmethod
    def _accept_common_shapes(cls, data: Any) -> Any:
        if isinstance(data, list):
            return {"items": data}
        if not isinstance(data, dict):
            return data
        if "items" in data:
            return data
        for key in ("results", "recommendations", "places", "cards", "joined_items"):
            value = data.get(key)
            if isinstance(value, list):
                copy = dict(data)
                copy["items"] = value
                return copy
        return data


_MAX_HITS_PER_SOURCE = 5
_MAX_SNIPPET_CHARS = 240
_MAX_FALLBACK_EVIDENCE = 3
_RAW_LOG_CHARS = 1000
_DEFAULT_JOINER_LLM_TIMEOUT_S = 45.0
_NAME_MATCH_THRESHOLD = 0.55
_MIN_XHS_AUTHENTICITY_SCORE = 0.35
_MIN_NAME_TOKEN_CHARS = 3

_POSITIVE_TERMS = (
    "gem",
    "real deal",
    "worth",
    "best",
    "favorite",
    "favourite",
    "resident",
    "local",
    "locals",
    "recommend",
    "recommended",
    "本地",
    "推荐",
    "排队",
    "水平",
    "好吃",
    "值得",
)
_TOURIST_TERMS = (
    "tourist",
    "chain",
    "airport",
    "instagram",
    "overrated",
    "skip",
    "mass-market",
    "打卡",
    "游客",
    "连锁",
    "不要",
    "不推荐",
    "不值得",
    "避雷",
    "踩雷",
    "排雷",
    "不好吃",
    "失望",
    "拉垮",
    "一般",
    "生气",
)

_NAME_STOPWORDS = {
    "and",
    "bar",
    "cafe",
    "ginza",
    "honten",
    "ichigaya",
    "japan",
    "japanese",
    "menya",
    "noodle",
    "ramen",
    "restaurant",
    "shibuya",
    "shinjuku",
    "shop",
    "sushi",
    "the",
    "tokyo",
}
_DESTINATION_ALIASES: dict[str, tuple[str, ...]] = {
    "tokyo": ("tokyo", "東京", "东京", "東京都"),
    "kyoto": ("kyoto", "京都"),
    "osaka": ("osaka", "大阪"),
    "shanghai": ("shanghai", "上海"),
    "beijing": ("beijing", "北京"),
    "guangzhou": ("guangzhou", "广州", "廣州"),
    "sapporo": ("sapporo", "札幌"),
    "hakone": ("hakone", "箱根"),
    "vancouver": ("vancouver", "温哥华", "溫哥華"),
    "irvine": ("irvine", "尔湾", "爾灣"),
    "bay area": ("bay area", "湾区", "灣區", "北湾", "北灣"),
    "singapore": ("singapore", "新加坡"),
    "seoul": ("seoul", "서울", "首尔", "首爾"),
    "taipei": ("taipei", "台北", "臺北"),
    "hong kong": ("hong kong", "香港"),
    "london": ("london", "伦敦", "倫敦"),
    "paris": ("paris", "巴黎"),
    "bangkok": ("bangkok", "曼谷"),
}
_FOOD_TERMS = (
    "ramen",
    "tsukemen",
    "soba",
    "noodle",
    "拉面",
    "拉麵",
    "蘸面",
    "沾面",
    "麺",
    "麵",
    "美食",
)


def _format_hit(source: str, hit: object) -> str:
    """Render one tool-result hit as a single line for the LLM prompt."""
    url = (
        getattr(hit, "permalink", None)
        or getattr(hit, "url", None)
        or getattr(hit, "external_url", None)
        or "(no url)"
    )
    title = getattr(hit, "title", None) or getattr(hit, "name", "") or ""
    body = getattr(hit, "body", None) or getattr(hit, "formatted_address", "") or ""
    snippet = str(body)[:_MAX_SNIPPET_CHARS]
    if source == "xiaohongshu":
        score = getattr(hit, "authenticity_score", None)
        local = ",".join(getattr(hit, "local_signals", ()) or ())
        promo = ",".join(getattr(hit, "promotion_signals", ()) or ())
        quality = f" authenticity={score if score is not None else 'unknown'}"
        if local:
            quality += f" local_signals={local[:120]}"
        if promo:
            quality += f" promo_signals={promo[:120]}"
        snippet = f"{quality}; {snippet}"
    return f"- [{source}][{url}] {title}: {snippet}"


def _tool_source_label(tool_name: str) -> str:
    """Map framework tool ids to the source labels the Joiner prompt expects."""
    return _normalise_source(tool_name) or tool_name


def _default_registry() -> ToolRegistry:
    """Build a fresh ToolRegistry with the Plus One evidence tools."""
    reg = ToolRegistry()
    reg.register(cast("Tool[Any, Any]", RedditSearchTool()))
    reg.register(cast("Tool[Any, Any]", XHSSearchTool()))
    reg.register(cast("Tool[Any, Any]", FoursquarePlacesSearchTool()))
    return reg


def _build_tool_calls(candidate: Candidate, query: str) -> list[ToolCall]:
    """Plan the per-candidate tool fan-out."""
    base = candidate.name
    if candidate.style:
        base = f"{base} {candidate.style}"
    location_hint = _location_hint_from_query(query)
    search_base = f"{base} {location_hint}" if location_hint else base
    return [
        ToolCall(
            tool="reddit_search",
            args={"query": search_base, "subreddits": ["JapanTravel", "ramen"], "limit": 10},
        ),
        ToolCall(tool="xhs_search", args={"query": f"{search_base} 推荐", "limit": 10}),
        ToolCall(
            tool="places_search", args={"query": base, "location_hint": location_hint, "limit": 5}
        ),
    ]


def _location_hint_from_query(query: str) -> str:
    """Extract the destination portion from the agent-visible query."""
    location = query.split("|", 1)[0].strip()
    location = " ".join(location.split())
    return location[:100]


async def joiner(candidates: list[Candidate], ctx: AgentContext) -> PhaseResult[JoinerPayload]:
    """Run the Joiner phase: fetch evidence + classify each candidate."""
    registry = _default_registry()
    fetch_tasks = [run_tool_calls(registry, _build_tool_calls(c, ctx.query)) for c in candidates]
    all_results = await asyncio.gather(*fetch_tasks)
    all_results = [
        _filter_results_for_candidate(candidate, results, ctx.query)
        for candidate, results in zip(candidates, all_results, strict=True)
    ]
    image_by_name = await _resolve_candidate_images(candidates, all_results, ctx.query)

    response = await _classify_with_llm(candidates, all_results, ctx)
    parsed = response.parsed if response.parsed is not None else _RawJoinerOutput()
    _log_joiner_response(response.text, parsed, len(candidates))
    parsed_items, invalid_items = _coerce_joined_items(parsed.items)
    repaired, dropped = _repair_items(parsed_items, candidates, ctx, image_by_name)
    fallback_items = 0
    if candidates and not repaired:
        repaired = _fallback_items(candidates, all_results, ctx, image_by_name)
        fallback_items = len(repaired)
        logger.warning(
            "joiner_empty_output_fallback",
            candidates=len(candidates),
            fallback_items=fallback_items,
        )
    tl_dr = _normalise_tl_dr(parsed.tl_dr) or _synthesise_tl_dr(repaired, ctx.query)

    return PhaseResult(
        payload=JoinerPayload(items=repaired, tl_dr=tl_dr),
        notes=(
            f"candidates_in={len(candidates)} joined_out={len(repaired)} "
            f"dropped_unknown={dropped} invalid_items={invalid_items} "
            f"fallback_items={fallback_items} "
            f"in_tokens={response.usage.input_tokens} "
            f"out_tokens={response.usage.output_tokens}"
        ),
    )


async def _classify_with_llm(
    candidates: list[Candidate],
    all_results: list[list[Any]],
    ctx: AgentContext,
) -> Any:
    llm = llm_factory.get_llm_provider("joiner_agent")
    system = (
        load_prompt("joiner", "v4")
        .replace(
            "{preferences}",
            render_preferences_section(ctx.user_profile, ctx.selected_companions),
        )
        .replace(
            "{person_roster}",
            render_person_roster(ctx.user_profile, ctx.selected_companions),
        )
    )
    try:
        return await asyncio.wait_for(
            llm.complete(
                system=system,
                messages=[
                    Message(
                        role="user",
                        content=_render_user_payload(candidates, all_results, ctx.query),
                    )
                ],
                response_model=_RawJoinerOutput,
            ),
            timeout=_joiner_llm_timeout_s(),
        )
    except TimeoutError:
        logger.warning("joiner_llm_timeout", timeout_s=_joiner_llm_timeout_s())
        return Response[_RawJoinerOutput](
            text='{"items": [], "tl_dr": null}',
            parsed=_RawJoinerOutput(),
            usage=Usage(input_tokens=0, output_tokens=0),
            model="timeout",
            provider="fallback",
        )


def _joiner_llm_timeout_s() -> float:
    raw = os.getenv("PLUS_ONE_JOINER_LLM_TIMEOUT_S", str(_DEFAULT_JOINER_LLM_TIMEOUT_S))
    try:
        return max(1.0, float(raw))
    except ValueError:
        return _DEFAULT_JOINER_LLM_TIMEOUT_S


def _log_joiner_response(raw_text: str, parsed: _RawJoinerOutput, candidates_in: int) -> None:
    keys = _top_level_keys(raw_text)
    logger.info(
        "joiner_llm_output",
        candidates=candidates_in,
        parsed_items=len(parsed.items),
        top_level_keys=keys,
        raw_preview=raw_text[:_RAW_LOG_CHARS],
    )


def _top_level_keys(raw_text: str) -> list[str]:
    try:
        data = extract_json_with_fallback(raw_text)
    except Exception:
        return []
    if isinstance(data, dict):
        return sorted(str(k) for k in data)[:20]
    if isinstance(data, list):
        return ["<array>"]
    return [f"<{type(data).__name__}>"]


def _coerce_joined_items(raw_items: list[Any]) -> tuple[list[JoinedItem], int]:
    items: list[JoinedItem] = []
    invalid = 0
    for index, raw in enumerate(raw_items):
        item = _coerce_joined_item(raw, index)
        if item is None:
            invalid += 1
        else:
            items.append(item)
    return items, invalid


def _coerce_joined_item(raw: dict[str, Any], index: int) -> JoinedItem | None:
    if not isinstance(raw, dict):
        logger.warning("joiner_item_dropped", index=index, reason="not_object")
        return None
    data = dict(raw)
    candidate = _normalise_candidate(data.get("candidate"), data)
    if candidate is None:
        logger.warning("joiner_item_dropped", index=index, reason="missing_candidate")
        return None
    data["candidate"] = candidate
    data["classification"] = _normalise_classification(data.get("classification"))
    data["classification_en"] = _normalise_optional_classification(data.get("classification_en"))
    data["classification_zh"] = _normalise_optional_classification(data.get("classification_zh"))
    data["confidence"] = _clamp_float(data.get("confidence"), default=0.0)
    data["summary"] = _trim_text(data.get("summary"), 500)
    data["long_description"] = _trim_text(
        data.get("long_description") or data.get("summary"),
        2400,
    )
    data["evidence"] = _normalise_evidence(data.get("evidence"))
    data["match_scores"] = _normalise_match_scores(data.get("match_scores"))
    try:
        return JoinedItem.model_validate(data)
    except ValidationError as exc:
        logger.warning(
            "joiner_item_dropped",
            index=index,
            reason="validation_error",
            error=str(exc)[:500],
        )
        return None


def _normalise_tl_dr(raw: object) -> str | None:
    text = _trim_text(raw, 1000)
    return text or None


def _synthesise_tl_dr(items: list[JoinedItem], query: str) -> str | None:
    """Deterministic report-level summary when the LLM omits ``tl_dr``.

    This is intentionally plain product copy, not a second classifier. It
    summarizes the already-classified cards so the trip detail has a real
    top-level takeaway even when the joiner timed out or fell back.
    """
    if not items:
        return None
    destination = _location_hint_from_query(query)
    gems = [item.candidate.name for item in items if item.classification == "local_gem"]
    traps = [item.candidate.name for item in items if item.classification == "tourist_trap"]
    mixed = [item.candidate.name for item in items if item.classification == "neutral"]
    thin = [item.candidate.name for item in items if item.classification == "insufficient"]

    lines: list[str] = []
    place = destination or "this trip"
    if gems:
        lines.append(
            f"{place} has {len(gems)} stronger pick{'s' if len(gems) != 1 else ''}: {_join_names(gems[:3])}."
        )
    else:
        lines.append(f"{place} does not have a clean must-go signal yet.")
    if traps:
        lines.append(
            f"Be careful with {_join_names(traps[:3])}; the sources show tourist-trap or skip signals."
        )
    if mixed:
        lines.append(
            f"Treat {_join_names(mixed[:3])} as optional, not anchors; evidence is mixed or mostly confirms popularity."
        )
    if thin:
        lines.append(
            f"I would not plan around {_join_names(thin[:2])} until better evidence appears."
        )
    return " ".join(lines)[:1000]


def _join_names(names: list[str]) -> str:
    clean = [name for name in names if name]
    if not clean:
        return "the weaker picks"
    if len(clean) == 1:
        return clean[0]
    return ", ".join(clean[:-1]) + f" and {clean[-1]}"


def _normalise_candidate(raw: object, fallback: dict[str, Any]) -> dict[str, object] | None:
    if isinstance(raw, dict):
        candidate = dict(raw)
    elif isinstance(raw, str):
        candidate = {"name": raw}
    elif isinstance(fallback.get("name"), str):
        candidate = {"name": fallback["name"]}
    else:
        return None
    name = _trim_text(candidate.get("name"), 200)
    if not name:
        return None
    candidate["name"] = name
    if candidate.get("area") is not None:
        candidate["area"] = _trim_text(candidate.get("area"), 100) or None
    if candidate.get("style") is not None:
        candidate["style"] = _trim_text(candidate.get("style"), 100) or None
    candidate["rationale"] = _trim_text(candidate.get("rationale"), 500)
    return candidate


def _normalise_classification(raw: object) -> Classification:
    if not isinstance(raw, str):
        return "insufficient"
    key = raw.strip().lower().replace("-", "_").replace(" ", "_")
    aliases: dict[str, Classification] = {
        "local_gem": "local_gem",
        "local": "local_gem",
        "gem": "local_gem",
        "tourist_trap": "tourist_trap",
        "trap": "tourist_trap",
        "neutral": "neutral",
        "mixed": "neutral",
        "insufficient": "insufficient",
        "unknown": "insufficient",
    }
    return aliases.get(key, "insufficient")


def _normalise_optional_classification(raw: object) -> Classification | None:
    if raw is None:
        return None
    if isinstance(raw, str) and raw.strip().lower() in {"", "null", "none", "n/a"}:
        return None
    return _normalise_classification(raw)


def _normalise_evidence(raw: object) -> list[dict[str, object]]:
    if not isinstance(raw, list):
        return []
    evidence: list[dict[str, object]] = []
    for entry in raw[:5]:
        if not isinstance(entry, dict):
            continue
        source = _normalise_source(entry.get("source"))
        if source is None:
            continue
        url = _trim_text(entry.get("url"), 1000) or "(no url)"
        snippet = _trim_text(entry.get("snippet"), 500)
        sentiment = None if source == "foursquare" else _clamp_float(entry.get("sentiment"), None)
        evidence.append(
            {
                "source": source,
                "url": url,
                "snippet": snippet,
                "sentiment": sentiment,
            }
        )
    return evidence


def _normalise_source(raw: object) -> str | None:
    if not isinstance(raw, str):
        return None
    key = raw.strip().lower().replace("-", "_").replace(" ", "_")
    if key in {"reddit", "reddit_search", "xiaohongshu", "foursquare"}:
        if key == "reddit_search":
            return "reddit"
        return key
    if key in {"xhs", "xhs_search", "redbook", "little_red_book"}:
        return "xiaohongshu"
    if key in {"places", "places_search", "place", "foursquare_places"}:
        return "foursquare"
    return None


def _normalise_match_scores(raw: object) -> dict[str, float] | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        return None
    scores: dict[str, float] = {}
    for key, value in raw.items():
        if value is None:
            continue
        try:
            scores[str(key)] = _clamp_float(value, default=0.5)
        except (TypeError, ValueError):
            continue
    return scores or None


def _clamp_float(raw: object, default: float | None) -> float | None:
    try:
        value = float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def _trim_text(raw: object, limit: int) -> str:
    if raw is None:
        return ""
    text = str(raw).strip()
    return text[:limit]


def _render_user_payload(
    candidates: list[Candidate], all_results: list[list[Any]], query: str
) -> str:
    lines: list[str] = [f"User query: {query}", ""]
    for candidate, results in zip(candidates, all_results, strict=True):
        lines.append(f"## {candidate.name} ({candidate.area or 'unknown'})")
        for result in results:
            label = _tool_source_label(result.tool)
            if not result.ok or not result.output:
                lines.append(f"### {label}: empty/{result.error or 'no data'}")
                continue
            lines.append(f"### {label} ({len(result.output)} hits)")
            for hit in result.output[:_MAX_HITS_PER_SOURCE]:
                lines.append(_format_hit(label, hit))
        lines.append("")
    return "\n".join(lines)


def _filter_results_for_candidate(
    candidate: Candidate,
    results: list[Any],
    query: str,
) -> list[Any]:
    filtered: list[Any] = []
    for result in results:
        if not result.ok or not result.output:
            filtered.append(result)
            continue
        kept = [
            hit
            for hit in result.output
            if _hit_matches_candidate(candidate, hit, query, source=_tool_source_label(result.tool))
        ]
        if len(kept) != len(result.output):
            logger.info(
                "joiner_evidence_filtered",
                candidate=candidate.name,
                tool=result.tool,
                kept=len(kept),
                dropped=len(result.output) - len(kept),
            )
        filtered.append(result.model_copy(update={"output": kept}))
    return filtered


def _hit_matches_candidate(candidate: Candidate, hit: object, query: str, *, source: str) -> bool:
    text = _hit_text(hit)
    if not text:
        return False

    destination = _location_hint_from_query(query)
    if _mentions_other_destination(text, destination):
        return False
    if source == "foursquare":
        return _foursquare_hit_matches_candidate(candidate, hit, destination)

    name_score = _candidate_name_score(candidate.name, text)
    return name_score >= _NAME_MATCH_THRESHOLD or (
        name_score > 0 and _mentions_destination(text, destination)
    )


def _foursquare_hit_matches_candidate(candidate: Candidate, hit: object, destination: str) -> bool:
    place_name = str(getattr(hit, "name", ""))
    address = str(getattr(hit, "formatted_address", ""))
    if _mentions_other_destination(" ".join([place_name, address]), destination):
        return False
    return _candidate_name_score(candidate.name, place_name) >= _NAME_MATCH_THRESHOLD


def _hit_text(hit: object) -> str:
    parts = [
        getattr(hit, "title", None),
        getattr(hit, "name", None),
        getattr(hit, "body", None),
        getattr(hit, "formatted_address", None),
    ]
    return " ".join(str(part) for part in parts if part)


def _candidate_name_score(name: str, text: str) -> float:
    name_norm = _normalise_match_text(name)
    text_norm = _normalise_match_text(text)
    if not name_norm or not text_norm:
        return 0.0
    if name_norm in text_norm:
        return 1.0
    tokens = _name_tokens(name)
    if not tokens:
        return 0.0
    hits = sum(1 for token in tokens if token in text_norm)
    if hits == 1 and any(_is_distinctive_token(token) and token in text_norm for token in tokens):
        return _NAME_MATCH_THRESHOLD
    return hits / len(tokens)


def _name_tokens(name: str) -> list[str]:
    normalised = _normalise_match_text(name)
    return [
        token
        for token in normalised.split()
        if len(token) >= _MIN_NAME_TOKEN_CHARS and token not in _NAME_STOPWORDS
    ]


def _normalise_match_text(text: str) -> str:
    lowered = text.lower()
    lowered = re.sub(r"[^\w\u3040-\u30ff\u3400-\u9fff]+", " ", lowered)
    return " ".join(lowered.split())


def _is_distinctive_token(token: str) -> bool:
    return any(char.isdigit() for char in token)


def _destination_aliases(destination: str) -> tuple[str, ...]:
    lower = destination.lower()
    aliases: list[str] = []
    for key, values in _DESTINATION_ALIASES.items():
        if key in lower or any(value.lower() in lower for value in values):
            aliases.extend(values)
    if not aliases and destination.strip():
        aliases.append(destination.strip())
    unique: list[str] = []
    for alias in aliases:
        key = alias.lower()
        if key and key not in unique:
            unique.append(key)
    return tuple(unique)


def _mentions_destination(text: str, destination: str) -> bool:
    lower = text.lower()
    aliases = _destination_aliases(destination)
    return bool(aliases) and any(alias in lower for alias in aliases)


def _mentions_other_destination(text: str, destination: str) -> bool:
    lower = text.lower()
    own_aliases = set(_destination_aliases(destination))
    lower_without_own = lower
    for alias in sorted(own_aliases, key=len, reverse=True):
        lower_without_own = lower_without_own.replace(alias, " ")
    for values in _DESTINATION_ALIASES.values():
        aliases = {value.lower() for value in values}
        if aliases & own_aliases:
            continue
        if any(alias in lower_without_own for alias in aliases):
            return True
    return False


def _repair_items(
    items: list[JoinedItem],
    candidates: list[Candidate],
    ctx: AgentContext,
    image_by_name: dict[str, ImageRef | None],
) -> tuple[list[JoinedItem], int]:
    allowed_ids = _allowed_person_ids(ctx)
    by_name: dict[str, Candidate] = {c.name.lower(): c for c in candidates}
    repaired: list[JoinedItem] = []
    dropped = 0
    for item in items:
        original = by_name.get(item.candidate.name.lower())
        if original is None:
            dropped += 1
            continue
        updates = _repair_item_updates(item, original, allowed_ids, image_by_name)
        repaired.append(item.model_copy(update=updates) if updates else item)
    return repaired, dropped


def _allowed_person_ids(ctx: AgentContext) -> set[UUID]:
    allowed_ids: set[UUID] = set()
    if ctx.user_profile.id is not None:
        allowed_ids.add(ctx.user_profile.id)
    for companion in ctx.selected_companions:
        if companion.id is not None:
            allowed_ids.add(companion.id)
    return allowed_ids


def _repair_item_updates(
    item: JoinedItem,
    original: Candidate,
    allowed_ids: set[UUID],
    image_by_name: dict[str, ImageRef | None],
) -> dict[str, object]:
    updates: dict[str, object] = {}
    score = divergence_score(item.classification_en, item.classification_zh)
    sanitised_scores = validate_match_scores(item.match_scores, allowed_ids)
    if item.candidate is not original:
        updates["candidate"] = original
    if score != item.divergence_score:
        updates["divergence_score"] = score
    if sanitised_scores != item.match_scores:
        updates["match_scores"] = sanitised_scores
    img = image_by_name.get(item.candidate.name.lower())
    if img is not None and not item.image_url:
        updates["image_url"] = img.url
        updates["image_source"] = img.source
    return updates


def _fallback_items(
    candidates: list[Candidate],
    all_results: list[list[Any]],
    ctx: AgentContext,
    image_by_name: dict[str, ImageRef | None],
) -> list[JoinedItem]:
    allowed_ids = _allowed_person_ids(ctx)
    items: list[JoinedItem] = []
    for candidate, results in zip(candidates, all_results, strict=True):
        evidence = _fallback_evidence(results)
        classification, confidence, classification_en, classification_zh = _fallback_verdict(
            evidence
        )
        summary = _fallback_summary(classification, evidence)
        image = image_by_name.get(candidate.name.lower())
        item = JoinedItem(
            candidate=candidate,
            classification=classification,
            classification_en=classification_en,
            classification_zh=classification_zh,
            confidence=confidence,
            evidence=tuple(evidence),
            summary=summary,
            long_description=_fallback_long_description(summary, evidence),
            match_scores=validate_match_scores(None, allowed_ids),
            image_url=image.url if image else None,
            image_source=image.source if image else None,
        )
        items.append(item)
    return items


def _fallback_evidence(results: list[Any]) -> list[Evidence]:
    evidence: list[Evidence] = []
    for result in results:
        if not result.ok or not result.output:
            continue
        source = _normalise_source(str(result.tool))
        if source is None:
            continue
        for hit in result.output:
            if source == "xiaohongshu" and not _xhs_hit_is_reliable(hit):
                continue
            url = (
                getattr(hit, "permalink", None)
                or getattr(hit, "url", None)
                or getattr(hit, "external_url", None)
                or "(no url)"
            )
            title = getattr(hit, "title", None) or getattr(hit, "name", "") or ""
            body = getattr(hit, "body", None) or getattr(hit, "formatted_address", "") or ""
            snippet = _trim_text(f"{title}: {body}", 500)
            evidence.append(
                Evidence(
                    source=source,  # type: ignore[arg-type]
                    url=str(url),
                    snippet=snippet,
                    sentiment=None if source == "foursquare" else _fallback_sentiment(snippet),
                )
            )
            if len(evidence) >= _MAX_FALLBACK_EVIDENCE:
                return evidence
    return evidence


def _fallback_verdict(
    evidence: list[Evidence],
) -> tuple[Classification, float, Classification | None, Classification | None]:
    if not evidence:
        return "insufficient", 0.0, None, None

    fused = _verdict_from_evidence(evidence)
    en = _verdict_from_evidence(
        [ev for ev in evidence if ev.source == "reddit"], allow_neutral=False
    )
    zh = _verdict_from_evidence(
        [ev for ev in evidence if ev.source == "xiaohongshu"], allow_neutral=False
    )
    source_count = len({ev.source for ev in evidence})
    confidence = 0.5 + min(0.25, 0.06 * len(evidence) + 0.04 * max(0, source_count - 1))
    if _has_mixed_sentiment(evidence):
        confidence = min(confidence, 0.62)
    if fused == "insufficient":
        confidence = 0.0
    return (
        fused,
        confidence,
        en if en != "insufficient" else None,
        zh if zh != "insufficient" else None,
    )


def _xhs_hit_is_reliable(hit: object) -> bool:
    if bool(getattr(hit, "is_promotional", False)):
        return False
    if getattr(hit, "authenticity_score", None) is None:
        assessed = assess_xhs_authenticity(
            {
                "author": getattr(hit, "author", ""),
                "title": getattr(hit, "title", ""),
                "body": getattr(hit, "body", ""),
                "images": getattr(hit, "images", ()),
            }
        )
        return bool(
            not assessed["is_promotional"] and assessed["score"] >= _MIN_XHS_AUTHENTICITY_SCORE
        )
    try:
        return float(getattr(hit, "authenticity_score", 0.0)) >= _MIN_XHS_AUTHENTICITY_SCORE
    except (TypeError, ValueError):
        return False


def _verdict_from_evidence(
    evidence: list[Evidence],
    *,
    allow_neutral: bool = True,
) -> Classification:
    if not evidence:
        return "insufficient"
    text = " ".join(ev.snippet for ev in evidence).lower()
    positive = _signal_count(text, _POSITIVE_TERMS)
    tourist = _signal_count(text, _TOURIST_TERMS)
    if tourist > 0 and positive > 0:
        return "neutral" if allow_neutral else "tourist_trap"
    if tourist > 0:
        return "tourist_trap"
    if positive > 0:
        return "local_gem"
    if allow_neutral and any(ev.source == "foursquare" for ev in evidence):
        return "neutral"
    return "insufficient"


def _fallback_sentiment(text: str) -> float:
    lower = text.lower()
    positive = _signal_count(lower, _POSITIVE_TERMS)
    tourist = _signal_count(lower, _TOURIST_TERMS)
    if tourist > positive:
        return -0.4
    if positive > tourist:
        return 0.4
    return 0.0


def _signal_count(text: str, terms: tuple[str, ...]) -> int:
    return sum(1 for term in terms if term in text)


def _has_mixed_sentiment(evidence: list[Evidence]) -> bool:
    sentiments = [ev.sentiment for ev in evidence if ev.sentiment is not None]
    if any(s > 0 for s in sentiments) and any(s < 0 for s in sentiments):
        return True
    text = " ".join(ev.snippet for ev in evidence).lower()
    return _signal_count(text, _POSITIVE_TERMS) > 0 and _signal_count(text, _TOURIST_TERMS) > 0


def _fallback_summary(classification: Classification, evidence: list[Evidence]) -> str:
    source_names = ", ".join(sorted({ev.source for ev in evidence})) or "available sources"
    if _has_mixed_sentiment(evidence):
        return f"{source_names} are split: there is visible hype, but also complaints worth taking seriously."
    if classification == "local_gem":
        return f"{source_names} point to real positive signal, not just name recognition."
    if classification == "tourist_trap":
        return f"{source_names} raise enough tourist, chain, or skip signals to be cautious."
    if classification == "neutral":
        return f"{source_names} confirm the place, but the evidence does not separate it from the obvious picks."
    return "Not enough reliable source evidence to classify this pick yet."


def _fallback_long_description(summary: str, evidence: list[Evidence]) -> str:
    snippets = [_trim_text(ev.snippet, 180) for ev in evidence[:2] if ev.snippet]
    if not snippets:
        return summary
    return f"{summary} " + " ".join(snippets)


async def _resolve_candidate_images(
    candidates: list[Candidate],
    all_results: list[list[Any]],
    query: str,
) -> dict[str, ImageRef | None]:
    """Build a candidate-name to image URL map for itinerary card art."""
    resolver = PlaceImageResolver()
    location_hint = _location_hint_from_query(query)
    tasks = [
        _resolve_candidate_image(candidate, results, location_hint, resolver)
        for candidate, results in zip(candidates, all_results, strict=True)
    ]
    image_refs = await asyncio.gather(*tasks)
    return {
        candidate.name.lower(): image_ref
        for candidate, image_ref in zip(candidates, image_refs, strict=True)
    }


async def _resolve_candidate_image(
    candidate: Candidate,
    results: list[Any],
    query: str,
    resolver: PlaceImageResolver,
) -> ImageRef | None:
    category = _image_category_hint(candidate, results)
    for result in results:
        if result.tool == "places_search" and result.ok and result.output:
            first = result.output[0]
            photo_url = getattr(first, "photo_url", None)
            if photo_url:
                return ImageRef(url=str(photo_url), source="foursquare")
            break
    xhs_image = _first_xhs_image(results)
    if xhs_image:
        return ImageRef(url=xhs_image, source="xhs")
    image = await resolver.resolve(
        PlaceImageInput(name=candidate.name, location_hint=query, category=category)
    )
    if image is None:
        fallback_category = _fallback_image_category(category)
        if fallback_category is not None:
            image = await resolver.resolve(
                PlaceImageInput(
                    name=candidate.name,
                    location_hint=query,
                    category=fallback_category,
                )
            )
    return ImageRef(url=image.image_url, source=image.source) if image is not None else None


def _fallback_image_category(category: str) -> str | None:
    """Retry public image search with a broader food term when style is too narrow."""
    lower = category.lower()
    if "ramen" in lower and lower.strip() != "ramen":
        return "ramen"
    return None


def _image_category_hint(candidate: Candidate, results: list[Any]) -> str:
    """Build a stable image-search hint without losing producer context."""
    haystack = " ".join([candidate.name, candidate.style or "", candidate.rationale or ""]).lower()
    ramen_markers = (
        "ramen",
        "tsukemen",
        "tantanmen",
        "tan tan",
        "tonkotsu",
        "shoyu",
        "shio",
        "niboshi",
        "soba",
        "noodle",
    )
    parts: list[str] = []
    if any(marker in haystack for marker in ramen_markers):
        parts.append("ramen")

    if candidate.style:
        parts.append(candidate.style)

    for result in results:
        if result.tool != "places_search" or not result.ok or not result.output:
            continue
        for place in result.output[:3]:
            categories = getattr(place, "categories", ()) or ()
            parts.extend(str(category) for category in categories)
        break

    return _compact_hint(parts, max_chars=64)


def _compact_hint(parts: list[str], *, max_chars: int) -> str:
    seen: set[str] = set()
    words: list[str] = []
    for part in parts:
        for raw in str(part).replace(",", " ").split():
            word = raw.strip()
            key = word.lower()
            if not word or key in seen:
                continue
            candidate = " ".join([*words, word])
            if len(candidate) > max_chars:
                return " ".join(words)
            seen.add(key)
            words.append(word)
    return " ".join(words)


def _first_xhs_image(results: list[Any]) -> str | None:
    """Return the first image attached to a successful XHS result."""
    for result in results:
        if result.tool != "xhs_search" or not result.ok or not result.output:
            continue
        for post in result.output:
            images = getattr(post, "images", ()) or ()
            for image_url in images:
                image = str(image_url).strip()
                if image:
                    return image
    return None
