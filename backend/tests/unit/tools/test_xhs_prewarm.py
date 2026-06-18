"""Unit tests for XHS prewarm helpers."""

from __future__ import annotations

import asyncio
import contextlib
from types import SimpleNamespace

import pytest

from plus_one.core.tools import _playwright_session
from plus_one.core.tools.xiaohongshu import XHSSearchTool
from plus_one.scripts.xhs_prewarm import (
    build_mvp_seed_payload,
    build_search_diagnostic,
    candidate_queries,
    classify_search_diagnostic,
    collect_report_stats,
    collect_cache_stats,
    dedupe_gap_candidate_rows,
    enrich_query_item_for_gaps,
    fetch_one,
    fetch_public_index_once,
    fetch_query_once,
    filter_relevant_posts,
    merge_reports,
    pipeline_diagnostics,
    preflight_xhs_search_gate,
    prewarm_work_items,
    resolve_public_profile_dir,
    resume_done_queries,
    sanitize_public_gate_rows,
    search_candidate_names,
    skip_reason_for_posts,
    xhs_profile_dir,
)
from plus_one.scripts import xhs_prewarm
from plus_one.scripts.xhs_mvp_seed_data import MVP_XHS_TARGET_CITIES


@pytest.mark.unit
def test_candidate_queries_prefer_chinese_alias_inside_parentheses() -> None:
    assert candidate_queries(
        "札幌 Craft beer bar Mugishutei (麦酒停) 酒吧推荐",
        "Craft beer bar Mugishutei (麦酒停)",
    ) == [
        "札幌 Craft beer bar Mugishutei (麦酒停) 酒吧推荐",
        "札幌 麦酒停 酒吧推荐",
        "札幌 麦酒停 真实体验",
        "札幌 麦酒停 本地人推荐",
    ]


@pytest.mark.unit
def test_candidate_queries_retry_short_name_for_long_english_descriptions() -> None:
    assert candidate_queries(
        "上海 Columbia Circle (Shanghai Film Studio 小红书推荐",
        "Columbia Circle (Shanghai Film Studio / Mansion 1933 area, Xinhua Road)",
    ) == [
        "上海 Columbia Circle (Shanghai Film Studio 小红书推荐",
        "上海 上生新所 小红书推荐",
        "上海 上生新所 真实体验",
        "上海 上生新所 本地人推荐",
    ]


@pytest.mark.unit
def test_candidate_queries_use_curated_aliases_before_english_name() -> None:
    assert candidate_queries(
        "东京 Menya Itto 拉面推荐",
        "Menya Itto",
    ) == [
        "东京 Menya Itto 拉面推荐",
        "东京 麺屋一燈 拉面推荐",
        "东京 面屋一灯 拉面推荐",
        "东京 麺屋一燈 拉面店推荐",
    ]


@pytest.mark.unit
def test_candidate_queries_normalise_destination_aliases() -> None:
    assert candidate_queries(
        "Shanghai Columbia Circle 小红书推荐",
        "Columbia Circle (Shanghai Film Studio site)",
    ) == [
        "Shanghai Columbia Circle 小红书推荐",
        "上海 上生新所 小红书推荐",
        "上海 上生新所 真实体验",
        "上海 上生新所 本地人推荐",
    ]


@pytest.mark.unit
def test_candidate_queries_strip_duplicate_city_from_fallback_alias() -> None:
    assert candidate_queries(
        "马拉喀什 +61 餐厅 美食推荐",
        "+61",
        max_attempts=2,
    ) == [
        "马拉喀什 +61 餐厅 美食推荐",
        "马拉喀什 +61 美食推荐",
    ]


@pytest.mark.unit
def test_candidate_queries_do_not_retry_with_plain_english_candidate_name() -> None:
    assert candidate_queries(
        "马拉喀什 烤羊街 真实体验",
        "Mechoui Alley",
        max_attempts=4,
    ) == [
        "马拉喀什 烤羊街 真实体验",
        "马拉喀什 烤羊街 本地人推荐",
    ]


@pytest.mark.unit
def test_candidate_queries_respects_single_attempt_limit() -> None:
    assert candidate_queries(
        "广州 宝华园 美食推荐",
        "Baohuayuan Sampan Congee (宝华园)",
        max_attempts=1,
    ) == ["广州 宝华园 美食推荐"]


@pytest.mark.unit
def test_search_candidate_names_puts_chinese_aliases_before_english_fallbacks() -> None:
    assert search_candidate_names("Afuri Ebisu")[:4] == [
        "阿夫利 惠比寿",
        "AFURI 惠比寿",
        "AFURI 恵比寿",
        "Afuri Ebisu",
    ]


@pytest.mark.unit
def test_enrich_query_item_for_gaps_generates_chinese_first_queries() -> None:
    item = {
        "candidate": "Afuri Harajuku",
        "category": "food",
        "destinations": ["Tokyo"],
        "aliases": [],
        "queries": ["东京 Afuri Harajuku 美食推荐"],
    }

    enriched = enrich_query_item_for_gaps(item)

    assert enriched["queries"][:6] == [
        "东京 阿夫利 原宿 美食推荐",
        "东京 AFURI 原宿 美食推荐",
        "东京 阿夫利 原宿 本地人推荐",
        "东京 AFURI 原宿 本地人推荐",
        "东京 阿夫利 原宿 真实体验",
        "东京 AFURI 原宿 真实体验",
    ]
    assert "东京 Afuri Harajuku 美食推荐" not in enriched["queries"]


@pytest.mark.unit
def test_enrich_query_item_for_gaps_tries_alias_variants_before_next_intent() -> None:
    item = {
        "candidate": "Afuri Ebisu",
        "category": "food",
        "destinations": ["Tokyo"],
        "aliases": [],
        "queries": [],
    }

    enriched = enrich_query_item_for_gaps(item)

    assert enriched["queries"][:5] == [
        "东京 阿夫利 惠比寿 美食推荐",
        "东京 AFURI 惠比寿 美食推荐",
        "东京 AFURI 恵比寿 美食推荐",
        "东京 阿夫利 惠比寿 本地人推荐",
        "东京 AFURI 惠比寿 本地人推荐",
    ]


@pytest.mark.unit
def test_enrich_query_item_for_gaps_uses_ramen_search_language() -> None:
    item = {
        "candidate": "Menya Itto",
        "category": "food",
        "destinations": ["Tokyo"],
        "aliases": [],
        "queries": ["东京 Menya Itto 美食推荐"],
    }

    enriched = enrich_query_item_for_gaps(item)

    assert enriched["queries"][:6] == [
        "东京 麺屋一燈 拉面推荐",
        "东京 面屋一灯 拉面推荐",
        "东京 麺屋一燈 拉面店推荐",
        "东京 面屋一灯 拉面店推荐",
        "东京 麺屋一燈 排队拉面",
        "东京 面屋一灯 排队拉面",
    ]
    assert "东京 Menya Itto 美食推荐" not in enriched["queries"]


@pytest.mark.unit
def test_enrich_query_item_for_gaps_uses_item_aliases_before_candidate_name() -> None:
    item = {
        "candidate": "Bao Hua Mian Jia (宝华面家)",
        "category": "food",
        "destinations": ["guangzhou"],
        "aliases": ["宝华面家"],
        "queries": [],
    }

    enriched = enrich_query_item_for_gaps(item)

    assert enriched["queries"][:4] == [
        "广州 宝华面家 美食推荐",
        "广州 宝华面店 美食推荐",
        "广州 寶華麵家 美食推荐",
        "广州 寶華麵店 美食推荐",
    ]


@pytest.mark.unit
def test_enrich_query_item_for_gaps_strips_duplicate_city_from_alias() -> None:
    item = {
        "candidate": "Al Bahriya",
        "category": "food",
        "destinations": ["Marrakech"],
        "aliases": [],
        "queries": [],
    }

    enriched = enrich_query_item_for_gaps(item)

    assert enriched["queries"][:2] == ["马拉喀什 Al Bahriya 美食推荐", "马拉喀什 Al Bahriya seafood 美食推荐"]


@pytest.mark.unit
def test_enrich_query_item_for_gaps_drops_english_original_when_chinese_alias_exists() -> None:
    item = {
        "candidate": "Afuri Harajuku",
        "category": "food",
        "destinations": ["Tokyo"],
        "aliases": [],
        "queries": ["东京 Afuri Harajuku 美食推荐"],
    }

    enriched = enrich_query_item_for_gaps(item)

    assert "东京 Afuri Harajuku 美食推荐" not in enriched["queries"]
    assert all("Tokyo" not in query for query in enriched["queries"])


@pytest.mark.unit
def test_enrich_query_item_for_gaps_uses_tea_intents_for_tea_stands() -> None:
    item = {
        "candidate": "Chairo Salon Tea Stand",
        "category": "drink",
        "destinations": ["Hakone"],
        "aliases": [],
        "queries": [],
    }

    enriched = enrich_query_item_for_gaps(item)

    assert enriched["queries"][:4] == [
        "箱根 Chairo Salon 茶屋 茶室推荐",
        "箱根 Chairo Salon 茶屋 本地人推荐",
        "箱根 Chairo Salon 茶屋 真实体验",
        "箱根 Chairo Salon 茶屋 茶道体验",
    ]
    assert all("酒吧推荐" not in query for query in enriched["queries"])


@pytest.mark.unit
def test_enrich_query_item_for_gaps_adds_contextual_aliases_for_ambiguous_kyoto_tea_names() -> None:
    item = {
        "candidate": "Ippuku-do (一福堂) / Ippuku Chaya at Ninenzaka",
        "category": "food",
        "destinations": ["Kyoto"],
        "aliases": [],
        "queries": [],
    }

    enriched = enrich_query_item_for_gaps(item)

    assert enriched["queries"][:8] == [
        "京都 一福堂 茶室推荐",
        "京都 二年坂 一福堂 茶室推荐",
        "京都 二年坂 一福堂 抹茶 茶室推荐",
        "京都 清水寺 一福堂 茶屋 茶室推荐",
        "京都 一福茶屋 茶室推荐",
        "京都 二年坂 一福茶屋 茶室推荐",
        "京都 一福堂 抹茶 茶室推荐",
        "京都 一福堂 茶屋 茶室推荐",
    ]


@pytest.mark.unit
def test_enrich_query_item_for_gaps_keeps_bar_intents_for_real_bars() -> None:
    item = {
        "candidate": "Bar Yamazaki",
        "category": "drink",
        "destinations": ["Sapporo"],
        "aliases": [],
        "queries": [],
    }

    enriched = enrich_query_item_for_gaps(item)

    assert enriched["queries"][:4] == [
        "札幌 山崎酒吧 酒吧推荐",
        "札幌 山崎酒吧 居酒屋推荐",
        "札幌 山崎酒吧 本地人推荐",
        "札幌 山崎酒吧 真实体验",
    ]


@pytest.mark.unit
def test_enrich_query_item_for_gaps_uses_food_intents_for_food_walk_attractions() -> None:
    item = {
        "candidate": "Chandni Chowk food walk (Paranthe Wali Gali)",
        "category": "attraction",
        "destinations": ["Delhi, India"],
        "aliases": [],
        "queries": [],
    }

    enriched = enrich_query_item_for_gaps(item)

    assert enriched["queries"][:6] == [
        "德里 月光集市 美食推荐",
        "德里 帕兰特瓦利街 美食推荐",
        "德里 月光集市 美食 美食推荐",
        "德里 月光集市 街头小吃",
        "德里 帕兰特瓦利街 街头小吃",
        "德里 月光集市 美食 街头小吃",
    ]
    assert all("本地人必去景点推荐" not in query for query in enriched["queries"][:8])


@pytest.mark.unit
def test_mvp_seed_payload_adds_target_cities_with_chinese_queries() -> None:
    payload = build_mvp_seed_payload([])
    by_destination = payload["by_destination"]

    assert len(payload["target_cities"]) == len(MVP_XHS_TARGET_CITIES)
    assert len(by_destination) == len(MVP_XHS_TARGET_CITIES)
    assert by_destination["首尔"] == 15
    assert by_destination["台北"] == 15
    assert by_destination["新加坡"] == 15

    seoul = next(item for item in payload["items"] if item["candidate"] == "明洞饺子")
    taipei = next(item for item in payload["items"] if item["candidate"] == "阜杭豆浆")
    assert seoul["queries"][:3] == [
        "首尔 明洞饺子 美食推荐",
        "首尔 명동교자 美食推荐",
        "首尔 明洞饺子 本地人推荐",
    ]
    assert taipei["queries"][:3] == [
        "台北 阜杭豆浆 美食推荐",
        "台北 阜杭豆浆 本地人推荐",
        "台北 阜杭豆浆 真实体验",
    ]


@pytest.mark.unit
def test_mvp_seed_payload_keeps_existing_items_and_dedupes_seed_candidate() -> None:
    payload = build_mvp_seed_payload(
        [
            {
                "candidate": "阜杭豆浆",
                "category": "food",
                "destinations": ["Taipei"],
                "aliases": [],
                "queries": ["台北 阜杭豆浆 美食推荐"],
            },
            {
                "candidate": "自定义候选",
                "category": "food",
                "destinations": ["Paris"],
                "aliases": ["自定义别名"],
                "queries": [],
            },
        ]
    )

    names = [item["candidate"] for item in payload["items"]]

    assert names.count("阜杭豆浆") == 1
    assert "自定义候选" in names
    custom = next(item for item in payload["items"] if item["candidate"] == "自定义候选")
    assert custom["queries"][0] == "巴黎 自定义别名 美食推荐"


@pytest.mark.unit
def test_dedupe_gap_candidate_rows_keeps_one_uncovered_duplicate() -> None:
    first = {
        "candidate": "Chuka Soba Inoue",
        "status": "untouched",
        "relevant_post_count": 0,
        "relevant_image_count": 0,
        "error_count": 0,
        "query_item": {"queries": ["东京 中華そば井上 美食推荐"]},
    }
    duplicate = {
        "candidate": "Chukasoba Inoue",
        "status": "untouched",
        "relevant_post_count": 0,
        "relevant_image_count": 0,
        "error_count": 0,
        "query_item": {"queries": ["东京 中華そば井上 美食推荐"]},
    }

    assert dedupe_gap_candidate_rows([first, duplicate]) == [first]


@pytest.mark.unit
def test_dedupe_gap_candidate_rows_skips_duplicate_of_covered_candidate() -> None:
    covered = {
        "candidate": "Camellia Garden Tea Ceremony",
        "status": "covered",
        "query_item": {"queries": ["京都 山茶花茶道 本地人必去景点推荐"]},
    }
    duplicate_gap = {
        "candidate": "Camellia Tea Ceremony Flower",
        "status": "untouched",
        "relevant_post_count": 0,
        "relevant_image_count": 0,
        "error_count": 0,
        "query_item": {"queries": ["京都 山茶花茶道 本地人必去景点推荐"]},
    }

    assert dedupe_gap_candidate_rows([covered, duplicate_gap]) == []


@pytest.mark.unit
def test_dedupe_gap_candidate_rows_sorts_partial_before_untouched() -> None:
    untouched = {
        "candidate": "Untouched Place",
        "status": "untouched",
        "relevant_post_count": 0,
        "relevant_image_count": 0,
        "error_count": 0,
        "query_item": {"queries": ["东京 未触达 本地人推荐"]},
    }
    partial = {
        "candidate": "Partial Place",
        "status": "partial",
        "relevant_post_count": 1,
        "relevant_image_count": 2,
        "error_count": 0,
        "query_item": {"queries": ["东京 部分覆盖 本地人推荐"]},
    }

    assert dedupe_gap_candidate_rows([untouched, partial]) == [partial, untouched]


@pytest.mark.unit
def test_dedupe_gap_candidate_rows_deprioritizes_stale_partial_rows() -> None:
    fresh_partial = {
        "candidate": "Fresh Partial Place",
        "status": "partial",
        "relevant_post_count": 1,
        "relevant_image_count": 1,
        "skipped_query_count": 0,
        "error_count": 0,
        "query_item": {"queries": ["广州 新鲜部分 本地人推荐"]},
    }
    stale_partial = {
        "candidate": "Stale Partial Place",
        "status": "partial",
        "relevant_post_count": 1,
        "relevant_image_count": 3,
        "skipped_query_count": 4,
        "error_count": 0,
        "query_item": {"queries": ["广州 卡住部分 本地人推荐"]},
    }

    assert dedupe_gap_candidate_rows([stale_partial, fresh_partial]) == [fresh_partial, stale_partial]


@pytest.mark.unit
def test_dedupe_gap_candidate_rows_keeps_stale_partial_after_fresh_partial() -> None:
    stale_partial = {
        "candidate": "Stale Partial Place",
        "status": "partial",
        "relevant_post_count": 1,
        "relevant_image_count": 3,
        "skipped_query_count": 5,
        "error_count": 0,
        "query_item": {"queries": ["札幌 弱召回 本地人推荐"]},
    }
    fresh_partial = {
        "candidate": "Fresh Partial Place",
        "status": "partial",
        "relevant_post_count": 1,
        "relevant_image_count": 1,
        "skipped_query_count": 0,
        "error_count": 0,
        "query_item": {"queries": ["广州 新候选 本地人推荐"]},
    }

    assert dedupe_gap_candidate_rows([stale_partial, fresh_partial]) == [fresh_partial, stale_partial]


@pytest.mark.unit
def test_merge_reports_combines_main_and_gap_results() -> None:
    merged = merge_reports(
        [
            {"settings": {"post_limit": 8}, "results": [{"candidate": "A", "ok": True}]},
            {"settings": {"post_limit": 4}, "results": [{"candidate": "B", "skip_reason": "no_relevant_authentic_posts"}]},
        ]
    )

    assert merged["settings"] == {"post_limit": 8}
    assert [row["candidate"] for row in merged["results"]] == ["A", "B"]


@pytest.mark.unit
def test_collect_report_stats_ignores_public_search_gated_rows() -> None:
    stats = collect_report_stats(
        {
            "results": [
                {
                    "candidate": "Public Probe",
                    "query": "德里 Public Probe 真实体验",
                    "skip_reason": "public_search_gated",
                    "error": "xhs public search gate: search results are gated by XHS",
                }
            ]
        }
    )

    assert stats["skipped"] == {}
    assert stats["errors"] == {}


@pytest.mark.unit
def test_collect_report_stats_treats_historical_login_wall_as_public_gate() -> None:
    stats = collect_report_stats(
        {
            "results": [
                {
                    "candidate": "Public Probe",
                    "query": "德里 Public Probe 真实体验",
                    "error": "xhs login wall: search results require logged-in browser auth",
                }
            ]
        }
    )

    assert stats["skipped"] == {}
    assert stats["errors"] == {}
    assert stats["last_errors"] == {}


@pytest.mark.unit
def test_collect_report_stats_treats_historical_security_gate_as_public_gate() -> None:
    stats = collect_report_stats(
        {
            "results": [
                {
                    "candidate": "Public Probe",
                    "query": "德里 Public Probe 真实体验",
                    "error_type": "XHSSecurityGate",
                    "error": "xhs security gate active: retry after solving account security restriction",
                }
            ]
        }
    )

    assert stats["skipped"] == {}
    assert stats["errors"] == {}
    assert stats["last_errors"] == {}


@pytest.mark.unit
def test_collect_cache_stats_dedupes_same_post_across_queries() -> None:
    post = {
        "id": "same",
        "author": "alice",
        "title": "上海上生新所 真实体验",
        "body": "本地朋友带去, 老建筑很好逛。",
        "url": "https://www.xiaohongshu.com/explore/same",
        "images": ["/media/xhs/a.webp", "/media/xhs/b.webp"],
    }
    rows = [
        {"candidate": "Columbia Circle (Shanghai Film Studio site)", "query": "上海 上生新所 本地人推荐", "payload": [post]},
        {"candidate": "Columbia Circle (Shanghai Film Studio site)", "query": "上海 上生新所 真实体验", "payload": [dict(post)]},
    ]

    stats = collect_cache_stats(rows)

    assert stats["cached_posts"]["Columbia Circle (Shanghai Film Studio site)"] == 1
    assert stats["cached_images"]["Columbia Circle (Shanghai Film Studio site)"] == 2
    assert stats["relevant_posts"]["Columbia Circle (Shanghai Film Studio site)"] == 1
    assert stats["relevant_images"]["Columbia Circle (Shanghai Film Studio site)"] == 2


@pytest.mark.unit
def test_prewarm_work_items_resume_advances_to_next_queries_per_candidate() -> None:
    report = {
        "results": [
            {
                "candidate": "D-matcha Kyoto Tea Farm (Wazuka)",
                "original_query": "京都 d matcha 和束 茶室推荐",
                "query": "京都 d matcha 和束 真实体验",
                "ok": True,
                "quality_version": 4,
            },
            {
                "candidate": "D-matcha Kyoto Tea Farm (Wazuka)",
                "query": "京都 d matcha 和束 本地人推荐",
                "skip_reason": "no_relevant_authentic_posts",
                "attempts": [{"query": "京都 d matcha 和束 本地人推荐"}],
                "empty_retry_version": 4,
            },
        ]
    }
    items = [
        {
            "candidate": "D-matcha Kyoto Tea Farm (Wazuka)",
            "queries": [
                "京都 d matcha 和束 茶室推荐",
                "京都 d matcha 和束 本地人推荐",
                "京都 d matcha 和束 真实体验",
                "京都 d matcha 和束 茶道体验",
            ],
        }
    ]

    work = prewarm_work_items(items, limit_candidates=1, queries_per_candidate=2, done=resume_done_queries(report))

    assert work == [
        {"candidate": "D-matcha Kyoto Tea Farm (Wazuka)", "query": "京都 d matcha 和束 茶道体验"},
    ]


@pytest.mark.unit
def test_prewarm_work_items_limit_counts_candidates_with_pending_queries() -> None:
    items = [
        {"candidate": "Covered", "queries": ["东京 已完成 美食推荐"]},
        {"candidate": "Pending One", "queries": ["东京 待抓一 美食推荐"]},
        {"candidate": "Pending Two", "queries": ["东京 待抓二 美食推荐"]},
    ]
    done = {("Covered", "东京 已完成 美食推荐")}

    work = prewarm_work_items(items, limit_candidates=2, queries_per_candidate=1, done=done)

    assert work == [
        {"candidate": "Pending One", "query": "东京 待抓一 美食推荐"},
        {"candidate": "Pending Two", "query": "东京 待抓二 美食推荐"},
    ]


@pytest.mark.unit
def test_resume_done_queries_marks_failed_attempt_queries_done() -> None:
    report = {
        "results": [
            {
                "candidate": "Ippuku-do (一福堂) / Ippuku Chaya at Ninenzaka",
                "query": "京都 一福堂 茶室推荐",
                "skip_reason": "no_relevant_authentic_posts",
                "empty_retry_version": 4,
                "attempts": [
                    {"query": "京都 一福堂 茶室推荐"},
                    {"query": "京都 二年坂 一福堂 茶室推荐"},
                    {"query": "京都 一福堂 真实体验"},
                ],
            }
        ]
    }

    done = resume_done_queries(report)

    assert (
        "Ippuku-do (一福堂) / Ippuku Chaya at Ninenzaka",
        "京都 二年坂 一福堂 茶室推荐",
    ) in done


@pytest.mark.unit
def test_sanitize_public_gate_rows_only_marks_trailing_raw_empty_rows() -> None:
    report = {
        "results": [
            {
                "candidate": "Historical Empty",
                "query": "东京 旧 query 美食推荐",
                "skip_reason": "no_usable_authentic_posts",
                "raw_count": 0,
                "empty_retry_version": 4,
                "attempts": [{"query": "东京 旧 query 美食推荐", "raw_count": 0}],
            },
            {"candidate": "Covered", "query": "上海 M50", "ok": True, "raw_count": 8, "quality_version": 4},
            {
                "candidate": "Gate Empty",
                "query": "上海 M50创意园 本地人推荐",
                "skip_reason": "no_usable_authentic_posts",
                "raw_count": 0,
                "empty_retry_version": 4,
                "attempts": [{"query": "上海 M50创意园 本地人推荐", "raw_count": 0}],
            },
        ]
    }

    sanitized, changed_count = sanitize_public_gate_rows(report, "2026-06-03T10:50:56+00:00")

    assert changed_count == 1
    assert sanitized["results"][0]["skip_reason"] == "no_usable_authentic_posts"
    assert sanitized["results"][2]["error_type"] == "XHSPublicSearchGate"
    assert "empty_retry_version" not in sanitized["results"][2]
    assert ("Gate Empty", "上海 M50创意园 本地人推荐") not in resume_done_queries(sanitized)


@pytest.mark.unit
async def test_preflight_xhs_search_gate_reports_search_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakePage:
        url = "https://www.xiaohongshu.com/website-login/error?error_msg=安全限制"

        def set_default_timeout(self, timeout: int) -> None:
            self.timeout = timeout

        def set_default_navigation_timeout(self, timeout: int) -> None:
            self.navigation_timeout = timeout

        async def close(self) -> None:
            self.closed = True

    class FakeContext:
        async def new_page(self) -> FakePage:
            return FakePage()

        async def close(self) -> None:
            self.closed = True

    async def fake_open_preflight_context(**kwargs: object) -> tuple[FakeContext, None, None]:
        del kwargs
        return FakeContext(), None, None

    async def fake_goto(*args: object, **kwargs: object) -> int:
        del args, kwargs
        raise RuntimeError("xhs verification required: solve the safety check in the persistent profile")

    monkeypatch.setattr("plus_one.scripts.xhs_prewarm.open_preflight_context", fake_open_preflight_context)
    monkeypatch.setattr(_playwright_session, "_goto_xhs_search", fake_goto)
    args = SimpleNamespace(timeout_s=18.0, call_timeout_s=45.0)

    result = await preflight_xhs_search_gate(args)

    assert result["ok"] is False
    assert result["error_type"] == "RuntimeError"
    assert "verification required" in result["error"]


@pytest.mark.unit
async def test_preflight_xhs_search_gate_reports_raw_count(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakePage:
        url = "https://www.xiaohongshu.com/search_result_ai?keyword=test"

        def set_default_timeout(self, timeout: int) -> None:
            self.timeout = timeout

        def set_default_navigation_timeout(self, timeout: int) -> None:
            self.navigation_timeout = timeout

        async def close(self) -> None:
            self.closed = True

    class FakeContext:
        async def new_page(self) -> FakePage:
            return FakePage()

        async def close(self) -> None:
            self.closed = True

    async def fake_open_preflight_context(**kwargs: object) -> tuple[FakeContext, None, None]:
        del kwargs
        return FakeContext(), None, None

    async def fake_goto(*args: object, **kwargs: object) -> int:
        del args, kwargs
        return 200

    async def fake_body_text(page: object) -> str:
        del page
        return "东京 AFURI 惠比寿 美食推荐 笔记"

    async def fake_selector_counts(page: object) -> dict[str, int]:
        del page
        return {'a[href*="/search_result/"]': 1, 'a[href*="/explore/"]': 0, "section.note-item": 1, "section[data-index]": 0}

    monkeypatch.setattr("plus_one.scripts.xhs_prewarm.open_preflight_context", fake_open_preflight_context)
    monkeypatch.setattr(_playwright_session, "_goto_xhs_search", fake_goto)
    monkeypatch.setattr(_playwright_session, "_page_body_text", fake_body_text)
    monkeypatch.setattr("plus_one.scripts.xhs_prewarm.xhs_selector_counts", fake_selector_counts)
    args = SimpleNamespace(timeout_s=18.0, call_timeout_s=45.0)

    result = await preflight_xhs_search_gate(args)

    assert result["ok"] is True
    assert result["query"] == "东京 AFURI 惠比寿 美食推荐"
    assert result["http_status"] == 200
    assert result["raw_count"] == 2


@pytest.mark.unit
def test_filter_relevant_posts_keeps_alias_hit_and_drops_unrelated_search_noise() -> None:
    posts = [
        {
            "id": "wrong",
            "author": "alice",
            "title": "上海|饼ok",
            "body": "第一次吃创意菜, 人均1580, 服务态度也不错。",
            "url": "https://www.xiaohongshu.com/explore/wrong",
            "images": ["/media/xhs/wrong.webp"],
        },
        {
            "id": "right",
            "author": "bob",
            "title": "阿大葱油饼排队真实体验",
            "body": "本地朋友说阿大现在还是要排队, 人均十几块。",
            "url": "https://www.xiaohongshu.com/explore/right",
            "images": ["/media/xhs/right.webp"],
        },
    ]

    kept = filter_relevant_posts(posts, "A Da Cong You Bing", "上海 A Da Cong You Bing 美食推荐")

    assert [post["id"] for post in kept] == ["right"]


@pytest.mark.unit
def test_filter_relevant_posts_ignores_stale_quality_fields_for_other_candidate() -> None:
    posts = [
        {
            "id": "afuri",
            "author": "alice",
            "title": "东京 Afuri 拉面真实体验",
            "body": "柚子拉面不错。",
            "url": "https://www.xiaohongshu.com/explore/afuri",
            "images": ["/media/xhs/afuri.webp"],
            "xhs_quality_version": 4,
            "xhs_candidate": "Afuri Ebisu",
            "xhs_query": "东京 Afuri 美食推荐",
            "xhs_relevance_score": 0.75,
            "xhs_relevance_terms": ["Afuri"],
        }
    ]

    kept = filter_relevant_posts(posts, "Yong Qi Beef Offal (永记牛杂)", "广州 永记牛杂 美食推荐")

    assert kept == []


@pytest.mark.unit
def test_filter_relevant_posts_keeps_reordered_chinese_alias_tokens() -> None:
    posts = [
        {
            "id": "right",
            "author": "alice",
            "title": "东京惠比寿 阿夫利",
            "body": "柚子拉面酸酸的, 会想再吃。",
            "url": "https://www.xiaohongshu.com/explore/right",
            "images": ["/media/xhs/right.webp"],
        },
        {
            "id": "wrong",
            "author": "bob",
            "title": "东京9家美食必吃榜",
            "body": "惠比寿附近也有很多店。",
            "url": "https://www.xiaohongshu.com/explore/wrong",
            "images": ["/media/xhs/wrong.webp"],
        },
    ]

    kept = filter_relevant_posts(posts, "Afuri Ebisu", "东京 阿夫利 惠比寿 美食推荐")

    assert [post["id"] for post in kept] == ["right"]


@pytest.mark.unit
def test_filter_relevant_posts_normalises_traditional_chinese_alias() -> None:
    posts = [
        {
            "id": "right",
            "author": "alice",
            "title": "廣州寶華麵家雲吞面",
            "body": "很多街坊排队来, 面有硬心, 汤很香。",
            "url": "https://www.xiaohongshu.com/explore/right",
            "images": ["/media/xhs/right.webp"],
        }
    ]

    kept = filter_relevant_posts(posts, "Bao Hua Mian Jia (宝华面家)", "广州 宝华面家 美食推荐")

    assert [post["id"] for post in kept] == ["right"]


@pytest.mark.unit
def test_filter_relevant_posts_keeps_short_latin_alias_inside_real_note_body() -> None:
    posts = [
        {
            "id": "chez-lamine",
            "author": "traveler",
            "title": "Marrakesh-5, 值得一尝",
            "body": "图1-5，chez lamine的馕坑羊肉，两个人0.5kg差不多，皮脆肉嫩。",
            "url": "https://www.xiaohongshu.com/explore/chez-lamine",
            "images": ["/media/xhs/chez.webp"],
        }
    ]

    kept = filter_relevant_posts(
        posts,
        "Chez Lamine Hadj Mustapha",
        "马拉喀什 Chez Lamine 烤羊 美食推荐",
    )

    assert [post["id"] for post in kept] == ["chez-lamine"]


@pytest.mark.unit
def test_filter_relevant_posts_keeps_swfc_note_without_observation_deck_wording() -> None:
    posts = [
        {
            "id": "swfc",
            "author": "traveler",
            "title": "陆家嘴三件套打卡两个",
            "body": "从观光角度上海环球金融中心的体验碾压上海金茂大厦，100层基本不用排队。",
            "url": "https://www.xiaohongshu.com/explore/swfc",
            "images": ["/media/xhs/swfc.webp"],
        }
    ]

    kept = filter_relevant_posts(
        posts,
        "Lujiazui SWFC observation deck",
        "上海 环球金融中心 观光厅 夜景",
    )

    assert [post["id"] for post in kept] == ["swfc"]


@pytest.mark.unit
def test_filter_relevant_posts_drops_title_with_competing_destination() -> None:
    posts = [
        {
            "id": "wrong-city",
            "author": "alice",
            "title": "安利一家在札幌的专营日本茶的店铺",
            "body": "店主说茶园位于京都府的和束町, 但这次是在札幌店里喝的。",
            "url": "https://www.xiaohongshu.com/explore/wrong-city",
            "images": ["/media/xhs/wrong.webp"],
        },
        {
            "id": "right-city",
            "author": "bob",
            "title": "京都周边和束町 d:matcha 茶园游",
            "body": "D:Matcha 是 farm to table 茶园, 体验很完整。",
            "url": "https://www.xiaohongshu.com/explore/right-city",
            "images": ["/media/xhs/right.webp"],
        },
    ]

    kept = filter_relevant_posts(posts, "D-matcha Kyoto Tea Farm (Wazuka)", "京都 d matcha 和束 真实体验")

    assert [post["id"] for post in kept] == ["right-city"]


@pytest.mark.unit
def test_filter_relevant_posts_drops_moon_light_single_word_false_positive() -> None:
    posts = [
        {
            "id": "moon-sun-brewing",
            "author": "traveler",
            "title": "钝评札幌喝酒从夯到拉排行",
            "body": "Moon sun brewing 是一家精酿店, North Island 也不错。",
            "url": "https://www.xiaohongshu.com/explore/moon-sun-brewing",
            "images": ["/media/xhs/moon.webp"],
        }
    ]

    kept = filter_relevant_posts(posts, "Moon-Light (Tsukiakari)", "札幌 月光 美食推荐")

    assert kept == []


@pytest.mark.unit
def test_skip_reason_distinguishes_relevant_text_without_images() -> None:
    relevant_text = [{"id": "text", "title": "AFURI 惠比寿", "url": "https://www.xiaohongshu.com/explore/text"}]

    assert skip_reason_for_posts(relevant_text, relevant_text, relevant_text, []) == "no_content_images"


@pytest.mark.unit
def test_pipeline_diagnostics_keeps_stage_samples() -> None:
    raw = [
        {
            "id": "raw",
            "title": "AFURI 惠比寿 排队",
            "body": "本地朋友推荐, 但是排队久。",
            "url": "https://www.xiaohongshu.com/explore/raw",
            "images": ["/media/xhs/raw.webp"],
        }
    ]

    diagnostics = pipeline_diagnostics(
        raw_posts=raw,
        text_usable=raw,
        image_usable=raw,
        authentic_posts=raw,
        relevant_text_posts=raw,
        final_posts=[],
    )

    assert diagnostics["raw_samples"][0]["title"] == "AFURI 惠比寿 排队"
    assert diagnostics["relevant_text_samples"][0]["image_count"] == 1
    assert diagnostics["final_samples"] == []


@pytest.mark.unit
async def test_fetch_one_preserves_failed_attempt_diagnostics(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_fetch_query_once(query: str, candidate: str, args: object) -> dict[str, object]:
        del args
        return {
            "ok": False,
            "candidate": candidate,
            "query": query,
            "key": "k",
            "raw_count": 1,
            "usable_count": 0,
            "skip_reason": "no_content_images",
            "diagnostics": {"raw_samples": [{"title": "AFURI 惠比寿"}]},
        }

    monkeypatch.setattr("plus_one.scripts.xhs_prewarm.fetch_query_once", fake_fetch_query_once)
    args = SimpleNamespace(max_query_attempts=1)

    result = await fetch_one("东京 AFURI 惠比寿 美食推荐", "Afuri Ebisu", args)

    assert result["skip_reason"] == "no_content_images"
    assert result["diagnostics"]["raw_samples"][0]["title"] == "AFURI 惠比寿"
    assert result["attempts"][0]["query"] == "东京 AFURI 惠比寿 美食推荐"


@pytest.mark.unit
async def test_fetch_one_retries_after_transient_search_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    async def fake_fetch_query_once(query: str, candidate: str, args: object) -> dict[str, object]:
        del args
        seen.append(query)
        if len(seen) == 1:
            return {
                "ok": False,
                "candidate": candidate,
                "query": query,
                "key": "k1",
                "error_type": "RuntimeError",
                "error": "xhs public search gate: search results are gated by XHS",
                "skip_reason": "public_search_gated",
            }
        return {
            "ok": True,
            "candidate": candidate,
            "query": query,
            "key": "k2",
            "usable_count": 1,
            "image_count": 1,
            "quality_version": 4,
        }

    async def fake_mirror_cached_payload(*args: object, **kwargs: object) -> None:
        del args, kwargs

    monkeypatch.setattr("plus_one.scripts.xhs_prewarm.fetch_query_once", fake_fetch_query_once)
    monkeypatch.setattr("plus_one.scripts.xhs_prewarm.mirror_cached_payload", fake_mirror_cached_payload)
    args = SimpleNamespace(max_query_attempts=2)

    result = await fetch_one("东京 AFURI 惠比寿 美食推荐", "Afuri Ebisu", args)

    assert result["ok"] is True
    assert seen == ["东京 AFURI 惠比寿 美食推荐", "东京 阿夫利 惠比寿 美食推荐"]
    assert result["attempts"][0]["skip_reason"] == "public_search_gated"


@pytest.mark.unit
async def test_fetch_query_once_marks_public_search_gate_as_transient(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_fetch(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise RuntimeError("xhs public search gate: search results are gated by XHS")

    monkeypatch.delenv("XHS_PROFILE_DIR", raising=False)
    monkeypatch.delenv("XHS_STORAGE_STATE", raising=False)
    monkeypatch.delenv("XHS_COOKIE", raising=False)
    monkeypatch.setattr(_playwright_session, "fetch", fake_fetch)

    async def fake_index_miss(self: object, query: str, limit: int) -> list[dict[str, object]]:
        del self, query, limit
        return []

    monkeypatch.setattr(XHSSearchTool, "_fetch_from_search_index", fake_index_miss)
    args = SimpleNamespace(post_limit=4, timeout_s=1, call_timeout_s=2, images_per_post=2)

    result = await fetch_query_once("德里 Dilli Haat 真实体验", "Dilli Haat", args)

    assert result["skip_reason"] == "public_search_gated"
    assert result["error_type"] == "RuntimeError"


@pytest.mark.unit
async def test_fetch_query_once_uses_public_index_after_public_gate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    async def fake_fetch(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise RuntimeError("xhs public search gate: search results are gated by XHS")

    async def fake_fetch_from_search_index(self: object, query: str, limit: int) -> list[dict[str, object]]:
        del self, limit
        assert query == "德里 Dilli Haat 真实体验"
        return [
            {
                "id": "idx1",
                "author": "public search index",
                "title": "Dilli Haat 小红书",
                "body": "",
                "url": "https://www.xiaohongshu.com/explore/idx1",
                "images": [],
                "xhs_index_stub": True,
            }
        ]

    async def fake_enrich_indexed_posts(
        self: object,
        posts: list[dict[str, object]],
        limit: int,
        **kwargs: object,
    ) -> list[dict[str, object]]:
        del self, limit
        assert kwargs == {"timeout_s": 1.0, "images_per_post": 2}
        enriched = [dict(post) for post in posts]
        enriched[0].update(
            {
                "author": "alice",
                "title": "Dilli Haat INA eating notes",
                "body": "We visited Dilli Haat INA, ate momos, and walked the craft market with a local friend.",
                "images": ["/media/xhs/aa/dilli-haat.webp"],
            }
        )
        enriched[0].pop("xhs_index_stub", None)
        return enriched

    written: list[tuple[str, str, list[dict[str, object]]]] = []
    local_rows: list[tuple[str, str, list[dict[str, object]]]] = []

    async def fake_put_cached(source: str, key: str, payload: list[dict[str, object]]) -> None:
        written.append((source, key, payload))

    def fake_append_local_cache(path, query: str, candidate: str, posts: list[dict[str, object]]) -> None:
        del path
        local_rows.append((query, candidate, posts))

    monkeypatch.setattr(_playwright_session, "fetch", fake_fetch)
    monkeypatch.setattr(XHSSearchTool, "_fetch_from_search_index", fake_fetch_from_search_index)
    monkeypatch.setattr(XHSSearchTool, "_enrich_indexed_posts", fake_enrich_indexed_posts)
    monkeypatch.setattr("plus_one.scripts.xhs_prewarm.put_cached", fake_put_cached)
    monkeypatch.setattr("plus_one.scripts.xhs_prewarm.append_local_cache", fake_append_local_cache)
    args = SimpleNamespace(
        post_limit=4,
        timeout_s=1,
        call_timeout_s=2,
        images_per_post=2,
        allow_text_only=False,
        local_cache_file=tmp_path / "xhs.jsonl",
    )

    result = await fetch_query_once("德里 Dilli Haat 真实体验", "Dilli Haat", args)

    assert result["ok"] is True
    assert result["source"] == "public_search_index"
    assert result["usable_count"] == 1
    assert result["image_count"] == 1
    assert written[0][0] == "xhs"
    assert local_rows[0][0] == "德里 Dilli Haat 真实体验"
    assert written[0][2][0]["images"] == ["/media/xhs/aa/dilli-haat.webp"]


@pytest.mark.unit
async def test_fetch_query_once_public_index_only_skips_xhs_search_page(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    async def explode_fetch(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise AssertionError("public-index-only mode must not visit the XHS search page")

    async def fake_fetch_from_search_index(self: object, query: str, limit: int) -> list[dict[str, object]]:
        del self, limit
        assert query == "Delhi Dilli Haat local review"
        return [
            {
                "id": "idx1",
                "author": "public search index",
                "title": "Dilli Haat XHS",
                "body": "",
                "url": "https://www.xiaohongshu.com/explore/idx1",
                "images": [],
                "xhs_index_stub": True,
            }
        ]

    async def fake_enrich_indexed_posts(
        self: object,
        posts: list[dict[str, object]],
        limit: int,
        **kwargs: object,
    ) -> list[dict[str, object]]:
        del self, limit
        assert kwargs == {"timeout_s": 1.0, "images_per_post": 2}
        enriched = [dict(post) for post in posts]
        enriched[0].update(
            {
                "author": "alice",
                "title": "Dilli Haat INA eating notes",
                "body": "We visited Dilli Haat INA, ate momos, and walked the craft market with a local friend.",
                "images": ["/media/xhs/aa/dilli-haat.webp"],
            }
        )
        enriched[0].pop("xhs_index_stub", None)
        return enriched

    monkeypatch.setattr(_playwright_session, "fetch", explode_fetch)
    monkeypatch.setattr(XHSSearchTool, "_fetch_from_search_index", fake_fetch_from_search_index)
    monkeypatch.setattr(XHSSearchTool, "_enrich_indexed_posts", fake_enrich_indexed_posts)

    async def fake_put_cached(source: str, key: str, payload: list[dict[str, object]]) -> None:
        del source, key, payload

    def fake_append_local_cache(path, query: str, candidate: str, posts: list[dict[str, object]]) -> None:
        del path, query, candidate, posts

    monkeypatch.setattr("plus_one.scripts.xhs_prewarm.put_cached", fake_put_cached)
    monkeypatch.setattr("plus_one.scripts.xhs_prewarm.append_local_cache", fake_append_local_cache)
    args = SimpleNamespace(
        post_limit=4,
        timeout_s=1,
        call_timeout_s=2,
        images_per_post=2,
        allow_text_only=False,
        public_index_only=True,
        local_cache_file=tmp_path / "xhs.jsonl",
    )

    result = await fetch_query_once("Delhi Dilli Haat local review", "Dilli Haat", args)

    assert result["ok"] is True
    assert result["source"] == "public_search_index"
    assert result["usable_count"] == 1


@pytest.mark.unit
async def test_fetch_query_once_public_index_only_honors_call_timeout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    async def slow_public_index_once(query: str, candidate: str, args: object) -> dict[str, object]:
        del query, candidate, args
        await asyncio.sleep(0.2)
        return {"ok": True, "source": "public_search_index"}

    monkeypatch.setattr("plus_one.scripts.xhs_prewarm.fetch_public_index_once", slow_public_index_once)
    args = SimpleNamespace(
        post_limit=4,
        timeout_s=1,
        call_timeout_s=0.01,
        images_per_post=2,
        allow_text_only=False,
        public_index_only=True,
        local_cache_file=tmp_path / "xhs.jsonl",
    )

    result = await fetch_query_once("Delhi Dilli Haat local review", "Dilli Haat", args)

    assert result["ok"] is False
    assert result["error_type"] == "TimeoutError"


@pytest.mark.unit
async def test_fetch_public_index_once_passes_cli_detail_limits(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    captured: dict[str, object] = {}

    async def fake_fetch_from_search_index(self: object, query: str, limit: int) -> list[dict[str, object]]:
        del self, query
        assert limit == 4
        return [
            {
                "id": "idx1",
                "author": "public search index",
                "title": "Dilli Haat XHS",
                "body": "",
                "url": "https://www.xiaohongshu.com/explore/idx1",
                "images": [],
                "xhs_index_stub": True,
            }
        ]

    async def fake_enrich_indexed_posts(
        self: object,
        posts: list[dict[str, object]],
        limit: int,
        *,
        timeout_s: float,
        images_per_post: int,
    ) -> list[dict[str, object]]:
        del self
        captured.update({"limit": limit, "timeout_s": timeout_s, "images_per_post": images_per_post})
        enriched = [dict(post) for post in posts]
        enriched[0].update(
            {
                "author": "alice",
                "title": "Dilli Haat INA eating notes",
                "body": "We visited Dilli Haat INA, ate momos, and walked the craft market with a local friend.",
                "images": ["/media/xhs/aa/dilli-haat.webp"],
            }
        )
        enriched[0].pop("xhs_index_stub", None)
        return enriched

    async def fake_put_cached(source: str, key: str, payload: list[dict[str, object]]) -> None:
        del source, key, payload

    def fake_append_local_cache(path, query: str, candidate: str, posts: list[dict[str, object]]) -> None:
        del path, query, candidate, posts

    monkeypatch.setattr(XHSSearchTool, "_fetch_from_search_index", fake_fetch_from_search_index)
    monkeypatch.setattr(XHSSearchTool, "_enrich_indexed_posts", fake_enrich_indexed_posts)
    monkeypatch.setattr("plus_one.scripts.xhs_prewarm.put_cached", fake_put_cached)
    monkeypatch.setattr("plus_one.scripts.xhs_prewarm.append_local_cache", fake_append_local_cache)
    args = SimpleNamespace(
        post_limit=4,
        timeout_s=7,
        call_timeout_s=9,
        images_per_post=2,
        allow_text_only=False,
        local_cache_file=tmp_path / "xhs.jsonl",
    )

    result = await fetch_public_index_once("Delhi Dilli Haat local review", "Dilli Haat", args)

    assert result["ok"] is True
    assert captured == {"limit": 4, "timeout_s": 7.0, "images_per_post": 2}


@pytest.mark.unit
async def test_fetch_query_once_rejects_public_index_without_local_images(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    async def fake_fetch(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise RuntimeError("xhs public search gate: search results are gated by XHS")

    async def fake_fetch_from_search_index(self: object, query: str, limit: int) -> list[dict[str, object]]:
        del self, query, limit
        return [{"id": "idx1", "title": "Dilli Haat", "body": "", "url": "https://www.xiaohongshu.com/explore/idx1", "images": [], "xhs_index_stub": True}]

    async def fake_enrich_indexed_posts(
        self: object,
        posts: list[dict[str, object]],
        limit: int,
        **kwargs: object,
    ) -> list[dict[str, object]]:
        del self, limit
        assert kwargs == {"timeout_s": 1.0, "images_per_post": 2}
        enriched = [dict(post) for post in posts]
        enriched[0].update(
            {
                "author": "alice",
                "title": "Dilli Haat INA eating notes",
                "body": "We visited Dilli Haat INA, ate momos, and walked the craft market with a local friend.",
                "images": ["https://sns-webpic-qc.xhscdn.com/dilli-haat!webp"],
            }
        )
        enriched[0].pop("xhs_index_stub", None)
        return enriched

    async def explode_put(*args: object, **kwargs: object) -> None:
        raise AssertionError("remote-only public index images must not be cached")

    monkeypatch.setattr(_playwright_session, "fetch", fake_fetch)
    monkeypatch.setattr(XHSSearchTool, "_fetch_from_search_index", fake_fetch_from_search_index)
    monkeypatch.setattr(XHSSearchTool, "_enrich_indexed_posts", fake_enrich_indexed_posts)
    monkeypatch.setattr("plus_one.scripts.xhs_prewarm.put_cached", explode_put)
    args = SimpleNamespace(
        post_limit=4,
        timeout_s=1,
        call_timeout_s=2,
        images_per_post=2,
        allow_text_only=False,
        local_cache_file=tmp_path / "xhs.jsonl",
    )

    result = await fetch_query_once("德里 Dilli Haat 真实体验", "Dilli Haat", args)

    assert result["ok"] is False
    assert result["skip_reason"] == "no_content_images"
    assert result["source"] == "public_search_index"


@pytest.mark.unit
async def test_fetch_query_once_rejects_live_public_search_without_local_images(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    async def fake_fetch(*args: object, **kwargs: object) -> object:
        del args, kwargs
        return SimpleNamespace(
            posts=[
                {
                    "id": "p1",
                    "author": "alice",
                    "title": "Dilli Haat INA eating notes",
                    "body": "We visited Dilli Haat INA, ate momos, and walked the craft market with a local friend.",
                    "url": "https://www.xiaohongshu.com/explore/p1",
                    "images": ["https://sns-webpic-qc.xhscdn.com/dilli-haat!webp"],
                }
            ]
        )

    async def explode_put(*args: object, **kwargs: object) -> None:
        raise AssertionError("remote-only live XHS images must not be cached")

    monkeypatch.setattr(_playwright_session, "fetch", fake_fetch)
    monkeypatch.setattr("plus_one.scripts.xhs_prewarm.put_cached", explode_put)
    args = SimpleNamespace(
        post_limit=4,
        timeout_s=1,
        call_timeout_s=2,
        images_per_post=2,
        allow_text_only=False,
        public_search=True,
        local_cache_file=tmp_path / "xhs.jsonl",
    )

    result = await fetch_query_once("德里 Dilli Haat 真实体验", "Dilli Haat", args)

    assert result["ok"] is False
    assert result["source"] == "live_xhs"
    assert result["skip_reason"] == "no_content_images"


@pytest.mark.unit
def test_classify_search_diagnostic_prioritizes_public_search_gate_over_verify_text() -> None:
    result = classify_search_diagnostic(
        {
            "url": "https://www.xiaohongshu.com/search_result?keyword=test",
            "cookie_names": ["web_session"],
            "selector_counts": {},
        },
        "登录后查看搜索结果\n安全限制\n扫码登录",
    )

    assert result["has_public_search_gate"] is True
    assert "has_login_wall" not in result
    assert result["has_verify"] is True
    assert result["classification"] == "public_search_gated"


@pytest.mark.unit
def test_classify_search_diagnostic_does_not_treat_login_sms_code_as_verification() -> None:
    result = classify_search_diagnostic(
        {
            "url": "https://www.xiaohongshu.com/explore",
            "cookie_names": ["web_session"],
            "selector_counts": {"section.note-item": 30},
        },
        "登录后推荐更懂你的笔记\n手机号登录\n获取验证码\n首页",
    )

    assert result["has_login_ui"] is True
    assert result["has_verify"] is False
    assert result["has_results"] is True
    assert result["classification"] == "usable"


@pytest.mark.unit
def test_filter_relevant_posts_matches_mercado_mellah_english_spice_market_alias() -> None:
    posts = [
        {
            "id": "mellah1",
            "title": "省流版马拉喀什购物地图 避开85%雷点",
            "author": "行天",
            "body": "蓝色④区：Mellah spice market是个有机市场，即平价精油批发地。",
            "url": "https://www.xiaohongshu.com/explore/mellah1",
            "images": ["/media/xhs/aa/mellah.webp"],
        }
    ]

    relevant = filter_relevant_posts(
        posts,
        "Mercado Mellah (Marché des Épices)",
        "马拉喀什 Mellah 香料市场 美食推荐",
    )

    assert relevant == posts


@pytest.mark.unit
async def test_fetch_query_once_public_search_ignores_configured_auth_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_fetch(*args: object, **kwargs: object) -> object:
        del args
        captured.update(kwargs)
        return SimpleNamespace(
            posts=[
                {
                    "id": "p1",
                    "author": "alice",
                    "title": "Dilli Haat INA eating notes",
                    "body": "We visited Dilli Haat INA, ate momos, and walked the craft market.",
                    "url": "https://www.xiaohongshu.com/search_result/p1",
                    "images": ["https://ci.xiaohongshu.com/x.jpg"],
                }
            ]
        )

    monkeypatch.setenv("XHS_PROFILE_DIR", "C:/tmp/xhs-profile")
    monkeypatch.setenv("XHS_STORAGE_STATE", "C:/tmp/xhs-storage-state.json")
    monkeypatch.setenv("XHS_COOKIE", "sess=abc")
    monkeypatch.setattr(_playwright_session, "fetch", fake_fetch)
    args = SimpleNamespace(
        post_limit=4,
        timeout_s=1,
        call_timeout_s=2,
        images_per_post=2,
        allow_text_only=False,
        public_search=True,
    )

    await fetch_query_once("德里 Dilli Haat 真实体验", "Dilli Haat", args)

    assert captured["profile_dir"] is None
    assert captured["storage_state_path"] is None
    assert captured["cookie"] is None


@pytest.mark.unit
async def test_fetch_query_once_defaults_to_public_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_fetch(*args: object, **kwargs: object) -> object:
        del args
        captured.update(kwargs)
        return SimpleNamespace(
            posts=[
                {
                    "id": "p1",
                    "author": "alice",
                    "title": "Dilli Haat INA eating notes",
                    "body": "We visited Dilli Haat INA, ate momos, and walked the craft market.",
                    "url": "https://www.xiaohongshu.com/search_result/p1",
                    "images": ["https://ci.xiaohongshu.com/x.jpg"],
                }
            ]
        )

    monkeypatch.setenv("XHS_PROFILE_DIR", "C:/tmp/xhs-profile")
    monkeypatch.setenv("XHS_STORAGE_STATE", "C:/tmp/xhs-storage-state.json")
    monkeypatch.setenv("XHS_COOKIE", "sess=abc")
    monkeypatch.delenv("XHS_USE_CONFIGURED_SESSION", raising=False)
    monkeypatch.setattr(_playwright_session, "fetch", fake_fetch)
    args = SimpleNamespace(post_limit=4, timeout_s=1, call_timeout_s=2, images_per_post=2, allow_text_only=False)

    await fetch_query_once("德里 Dilli Haat 真实体验", "Dilli Haat", args)

    assert captured["profile_dir"] is None
    assert captured["storage_state_path"] is None
    assert captured["cookie"] is None


@pytest.mark.unit
async def test_fetch_query_once_public_search_can_use_public_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_fetch(*args: object, **kwargs: object) -> object:
        del args
        captured.update(kwargs)
        return SimpleNamespace(
            posts=[
                {
                    "id": "p1",
                    "author": "alice",
                    "title": "Dilli Haat INA eating notes",
                    "body": "We visited Dilli Haat INA, ate momos, and walked the craft market.",
                    "url": "https://www.xiaohongshu.com/search_result/p1",
                    "images": ["https://ci.xiaohongshu.com/x.jpg"],
                }
            ]
        )

    monkeypatch.setenv("XHS_PROFILE_DIR", "C:/tmp/auth-profile")
    monkeypatch.setenv("XHS_STORAGE_STATE", "C:/tmp/xhs-storage-state.json")
    monkeypatch.setenv("XHS_COOKIE", "sess=abc")
    monkeypatch.setattr(_playwright_session, "fetch", fake_fetch)
    args = SimpleNamespace(
        post_limit=4,
        timeout_s=1,
        call_timeout_s=2,
        images_per_post=2,
        allow_text_only=False,
        public_search=True,
        public_profile_dir="C:/tmp/public-profile",
    )

    await fetch_query_once("德里 Dilli Haat 真实体验", "Dilli Haat", args)

    assert captured["profile_dir"] == "C:\\tmp\\public-profile"
    assert captured["storage_state_path"] is None
    assert captured["cookie"] is None


@pytest.mark.unit
def test_xhs_public_profile_dir_uses_public_resolver(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    auth_profile = tmp_path / "auth-profile"
    public_profile = tmp_path / "public-profile"
    monkeypatch.setenv("XHS_PROFILE_DIR", str(auth_profile))

    resolved = xhs_profile_dir(public_search=True, public_profile_dir=str(public_profile))

    assert resolved == str(resolve_public_profile_dir(str(public_profile)))
    assert resolved != str(auth_profile.resolve())


@pytest.mark.unit
def test_xhs_default_public_search_ignores_configured_session_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from plus_one.scripts.xhs_prewarm import args_public_search, xhs_cookie, xhs_storage_state_path

    monkeypatch.setenv("XHS_PROFILE_DIR", "C:/tmp/auth-profile")
    monkeypatch.setenv("XHS_STORAGE_STATE", "C:/tmp/xhs-storage-state.json")
    monkeypatch.setenv("XHS_COOKIE", "sess=abc")
    monkeypatch.delenv("XHS_USE_CONFIGURED_SESSION", raising=False)
    args = SimpleNamespace(public_search=False, use_configured_session=False)

    public_search = args_public_search(args)

    assert public_search is True
    assert xhs_profile_dir(public_search=public_search) is None
    assert xhs_storage_state_path(public_search=public_search) is None
    assert xhs_cookie(public_search=public_search) is None


@pytest.mark.unit
async def test_build_search_diagnostic_defaults_to_public_profile(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    public_profile = tmp_path / "public-profile"
    auth_profile = tmp_path / "auth-profile"
    captured: dict[str, object] = {}

    class FakeLocator:
        async def count(self) -> int:
            return 1

    class FakePage:
        url = "https://www.xiaohongshu.com/search_result?keyword=test"

        def set_default_timeout(self, timeout: int) -> None:
            captured["timeout"] = timeout

        def set_default_navigation_timeout(self, timeout: int) -> None:
            captured["navigation_timeout"] = timeout

        async def wait_for_timeout(self, timeout: int) -> None:
            captured["wait_timeout"] = timeout

        async def title(self) -> str:
            return "小红书搜索"

        async def screenshot(self, **kwargs: object) -> None:
            captured["screenshot"] = kwargs

        def locator(self, selector: str) -> FakeLocator:
            captured.setdefault("selectors", []).append(selector)  # type: ignore[attr-defined]
            return FakeLocator()

        async def close(self) -> None:
            captured["page_closed"] = True

    class FakeContext:
        async def new_page(self) -> FakePage:
            return FakePage()

        async def cookies(self, url: str) -> list[dict[str, str]]:
            captured["cookie_url"] = url
            return []

    @contextlib.asynccontextmanager
    async def fake_open_public_diagnostic_context(**kwargs: object):
        captured.update(kwargs)
        yield FakeContext()

    async def fake_goto_xhs_search(*args: object, **kwargs: object) -> int:
        del args, kwargs
        return 200

    async def fake_page_body_text(page: object) -> str:
        del page
        return "公开搜索结果"

    monkeypatch.setenv("XHS_PROFILE_DIR", str(auth_profile))
    monkeypatch.setattr("plus_one.scripts.xhs_prewarm.DEFAULT_PUBLIC_BROWSER_PROFILE_DIR", public_profile)
    monkeypatch.setattr(xhs_prewarm, "_open_public_diagnostic_context", fake_open_public_diagnostic_context)
    monkeypatch.setattr(_playwright_session, "_goto_xhs_search", fake_goto_xhs_search)
    monkeypatch.setattr(_playwright_session, "_page_body_text", fake_page_body_text)

    report = await build_search_diagnostic(
        profile_dir=None,
        query="东京 AFURI 惠比寿 美食推荐",
        timeout_s=1,
        screenshot_file=tmp_path / "diagnostic.png",
        headed=False,
    )

    check = report["checks"][0]
    assert check["classification"] == "usable"
    assert check["profile_dir"] == str(public_profile.resolve())
    assert check["profile_dir"] != str(auth_profile.resolve())
    assert public_profile.exists()
    assert captured["resolved_profile"] == public_profile.resolve()


@pytest.mark.unit
async def test_fetch_query_once_marks_profile_gate_as_transient(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_fetch(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise RuntimeError("xhs verification required: solve the safety check in the persistent profile")

    async def fake_public_index_once(query: str, candidate: str, args: object) -> dict[str, object]:
        return {
            "ok": False,
            "candidate": candidate,
            "query": query,
            "raw_count": 0,
            "usable_count": 0,
            "skip_reason": "public_search_gated",
        }

    monkeypatch.setenv("XHS_PROFILE_DIR", "C:/tmp/xhs-profile")
    monkeypatch.delenv("XHS_STORAGE_STATE", raising=False)
    monkeypatch.delenv("XHS_COOKIE", raising=False)
    monkeypatch.setattr(_playwright_session, "fetch", fake_fetch)
    monkeypatch.setattr("plus_one.scripts.xhs_prewarm.fetch_public_index_once", fake_public_index_once)
    args = SimpleNamespace(post_limit=4, timeout_s=1, call_timeout_s=2, images_per_post=2)

    result = await fetch_query_once("德里 Dilli Haat 真实体验", "Dilli Haat", args)

    assert result["skip_reason"] == "public_search_gated"
    assert result["error_type"] == "RuntimeError"



@pytest.mark.unit
def test_classify_search_diagnostic_detects_account_security_error() -> None:
    result = classify_search_diagnostic(
        {
            "url": "https://www.xiaohongshu.com/website-login/error?error_code=300011",
            "cookie_names": ["web_session", "id_token"],
            "selector_counts": {},
        },
        "安全限制\n当前账号存在异常，请切换账号后重试",
    )

    assert result["has_verify"] is True
    assert result["classification"] == "security_verification"
