"""Xiaohongshu (RedNote) search tool — 3-tier scraper per ADR-003.

Mode is resolved per-call via ``get_tools_mode()``. Real-mode behavior
implements a real-mode fallback ladder derived from ADR-003 / PRD Batch 2k:

  * **Tier 1** — live Playwright scrape via ``_playwright_session.fetch``.
    The public desktop search page is attempted without cookie/storage
    injection by default. A configured browser session can be enabled
    explicitly for local diagnostics, but it is not required.
  * **Tier 2** — if tier 1 is unavailable or raises (timeout / 429 / captcha / network),
    look up ``tool_cache`` and serve a cached payload if present (and
    not expired).
  * **Tier 3** — public search-index discovery for already indexed XHS note
    URLs/titles. This is not full-content scraping.
  * **Tier 4** — if cache and search-index miss too, fall back to the curated fixture
    file (``fixtures/xhs/<slug>.json``) and emit a structured WARN log
    (``xhs_degraded_to_fixture``) so the degradation is visible in
    observability.
  * All three fail → ``ToolResult(ok=True, output=[], notes="degraded")``
    plus WARN ``xhs_total_failure``. The joiner treats empty output as
    "no evidence from this source" per PRD §3.4.

Fixture mode bypasses all three tiers and uses the same fixture-file
reader as tier 3 (current behavior preserved exactly).
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import os
import re
from html import escape, unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, ClassVar
from urllib.parse import parse_qs, unquote, urlencode, urlparse

import httpx
import structlog
from pydantic import BaseModel, ConfigDict, Field

from plus_one.config import settings
from plus_one.core.agents.framework.tools import ToolResult
from plus_one.core.tools import _playwright_session
from plus_one.core.tools._cache import cache_key, load_json_fixture
from plus_one.core.tools._cache_db import get_cached, put_cached
from plus_one.core.tools._mode import get_tools_mode

logger = structlog.get_logger()

_DUCKDUCKGO_SEARCH_URL = "https://duckduckgo.com/html/"
_BING_SEARCH_URL = "https://www.bing.com/search"
_SOGOU_SEARCH_URL = "https://www.sogou.com/web"
_SOGOU_IMAGE_SEARCH_URL = "https://pic.sogou.com/pics"
_SEARCH_INDEX_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
_XHS_NOTE_RE = re.compile(
    r"https?://(?:www\.)?xiaohongshu\.com/(?:explore|search_result|discovery/item(?:/sgh)?)/([A-Za-z0-9]+)",
    re.IGNORECASE,
)
_ASCII_MAX_CODEPOINT = 127
_CACHE_QUALITY_VERSION = 4
_MIN_QUERY_RELEVANCE_SCORE = 0.5
_MIN_CJK_QUERY_TERM_CHARS = 2
_MIN_LATIN_QUERY_TERM_CHARS = 3
_QUERY_INTENTS = (
    "本地人必去景点推荐",
    "本地人推荐",
    "本地人常去",
    "美食推荐",
    "酒吧推荐",
    "居酒屋推荐",
    "饮品推荐",
    "茶室推荐",
    "茶道体验",
    "咖啡推荐",
    "甜品推荐",
    "街头小吃",
    "小众景点",
    "小红书推荐",
    "真实体验",
    "值得吃吗",
    "值得去吗",
    "攻略",
    "避雷",
    "氛围",
    "recommend",
    "recommended",
    "review",
    "reviews",
    "guide",
)
_GENERIC_QUERY_ENTITY_TERMS = {
    "bar",
    "beer",
    "cafe",
    "coffee",
    "food",
    "garden",
    "hotel",
    "market",
    "museum",
    "park",
    "ramen",
    "restaurant",
    "shop",
    "soba",
    "station",
    "street",
    "temple",
}
CJK_NORMALIZATION_TABLE = str.maketrans(
    {
        "廣": "广",
        "東": "东",
        "寶": "宝",
        "華": "华",
        "麵": "面",
        "雲": "云",
        "燒": "烧",
        "點": "点",
        "園": "园",
        "館": "馆",
        "門": "门",
        "臺": "台",
        "灣": "湾",
        "區": "区",
        "舊": "旧",
        "裡": "里",
        "裏": "里",
        "鍋": "锅",
        "壽": "寿",
        "樂": "乐",
    }
)


class XHSPost(BaseModel):
    """One Xiaohongshu (RedNote) note."""

    model_config = ConfigDict(frozen=True)

    id: str
    author: str
    title: str
    body: str = ""
    likes: int = 0
    comments: int = 0
    url: str
    images: tuple[str, ...] = ()
    authenticity_score: float = Field(default=0.5, ge=0.0, le=1.0)
    is_promotional: bool = False
    promotion_signals: tuple[str, ...] = ()
    local_signals: tuple[str, ...] = ()


_MIN_AUTHENTICITY_SCORE = 0.35
_LONG_PERSONAL_NOTE_CHARS = 120
_MEDIUM_NOTE_CHARS = 60
_THIN_NOTE_CHARS = 15
_SOFT_PROMO_PILEUP_COUNT = 3
_PROMOTION_HARD_TERMS = (
    "私信",
    "私我",
    "加v",
    "加 v",
    "v信",
    "vx",
    "wechat",
    "weixin",
    "进群",
    "入群",
    "报我名字",
    "报暗号",
    "团购",
    "优惠券",
    "代订",
    "返利",
    "佣金",
    "商务合作",
    "探店合作",
    "合作请",
    "广告",
    "推广",
    "赞助",
    "免费试吃",
    "霸王餐",
    "抽奖",
    "福利",
)
_PROMOTION_SOFT_TERMS = (
    "必打卡",
    "必吃榜",
    "不允许你不知道",
    "全网",
    "爆火",
    "网红",
    "巨出片",
    "超出片",
    "封神",
    "天花板",
    "绝绝子",
    "姐妹们",
    "冲就完了",
    "码住",
    "收藏起来",
    "闭眼冲",
    "不踩雷",
    "套餐",
    "种草",
    "保姆级",
    "懒人包",
    "一篇搞定",
)
_MERCHANT_AUTHOR_TERMS = (
    "官方",
    "门店",
    "餐厅",
    "酒店",
    "民宿",
    "旅行社",
    "客服",
    "小助理",
)
_LOCAL_SIGNAL_TERMS = (
    "本地人",
    "本地朋友",
    "当地人",
    "朋友带",
    "住附近",
    "家附近",
    "公司附近",
    "常去",
    "经常去",
    "回头",
    "二刷",
    "三刷",
    "老店",
    "街坊",
    "居民",
    "工作日",
    "避开周末",
    "避开饭点",
    "排队",
    "不用排队",
    "踩雷",
    "避雷",
    "缺点",
    "一般",
    "不推荐",
    "不值得",
    "但是",
    "不过",
    "偏咸",
    "偏甜",
    "偏油",
    "服务",
    "环境",
    "价格",
    "人均",
    "菜单",
    "点了",
    "吃了",
    "喝了",
    "味道",
    "营业",
    "只收现金",
)
_DETAIL_RE = re.compile(
    r"(\d+\s*(?:min|分钟|小时|点|日|月|円|元|块)|人均\s*\d+|排队\s*\d+|[¥￥]\s*\d+)",
    re.IGNORECASE,
)
_CONTACT_RE = re.compile(r"(?<!\w)(?:vx|wechat|weixin)(?!\w)|(?<!\d)\+?\d[\d\s-]{7,}\d(?!\d)")


class XHSSearchInput(BaseModel):
    """Args for ``xhs_search``."""

    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=25, ge=1, le=100)


class XHSSearchTool:
    """XHS search with mode-aware dispatch.

    Cache key is the slugified query. Fixture file
    ``fixtures/xhs/<slug>.json`` is a list of XHSPost dicts; the same
    key is used for the DB cache lookup in real mode (tier 2).
    """

    name: ClassVar[str] = "xhs_search"
    input_schema: ClassVar[type[BaseModel]] = XHSSearchInput
    is_concurrency_safe: ClassVar[bool] = True

    _SOURCE: ClassVar[str] = "xhs"

    def __init__(self, fixtures_dir: Path | None = None) -> None:
        self._fixtures_dir = (fixtures_dir or settings.fixtures_dir) / "xhs"
        self._client: httpx.AsyncClient | None = None
        # Cache, public-index URL discovery, fixtures, and empty output keep
        # the Chinese-source slot live when XHS gates or throttles the page.

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        self._client = httpx.AsyncClient(
            headers={
                "User-Agent": _SEARCH_INDEX_UA,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
            timeout=httpx.Timeout(12.0, connect=5.0),
            follow_redirects=True,
        )
        return self._client

    # === fixture mode (unchanged behavior) ===========================

    def _execute_fixture(self, args: XHSSearchInput) -> ToolResult[list[XHSPost]]:
        key = cache_key(args.query)
        raw = load_json_fixture(self._fixtures_dir, key)
        posts = [XHSPost.model_validate(item) for item in raw[: args.limit]]
        return ToolResult(
            tool=self.name,
            output=posts,
            notes=f"loaded {len(posts)} posts from cache key {key!r}",
        )

    # === real mode (3-tier per ADR-003) ==============================

    async def _execute_real(self, args: XHSSearchInput) -> ToolResult[list[XHSPost]]:
        key = xhs_cache_key(args.query)

        if _prefer_cache():
            cached_result = await self._load_cached_result(
                key,
                args.limit,
                note_prefix="prewarmed",
                query=args.query,
            )
            if cached_result is not None:
                return cached_result

        # --- Tier 1: live scrape ------------------------------------
        cookie, profile_dir, storage_state_path = _configured_session_values()
        tier1_mode = (
            "persistent_profile"
            if profile_dir
            else "storage_state"
            if storage_state_path
            else "cookie"
            if cookie
            else "public"
        )
        try:
            scrape = await _playwright_session.fetch(
                args.query,
                cookie=None if (profile_dir or storage_state_path) else cookie,
                storage_state_path=None if profile_dir else storage_state_path,
                profile_dir=profile_dir,
                limit=args.limit,
                user_agent=os.getenv("XHS_USER_AGENT"),
                timeout_s=float(os.getenv("XHS_TIMEOUT_S", "30")),
                cache_images=_cache_images_enabled(),
                images_per_post=_images_per_post(),
            )
            raw = mark_quality_checked_xhs_posts(
                filter_query_relevant_xhs_posts(
                    filter_authentic_xhs_posts(annotate_xhs_posts(scrape.posts)),
                    args.query,
                ),
                args.query,
            )
            preflight_posts = [XHSPost.model_validate(item) for item in raw[: args.limit]]
            if not preflight_posts:
                logger.info("xhs_tier1_scrape_empty", key=key, mode=tier1_mode)
                raise RuntimeError("xhs tier1 returned 0 authentic posts")
            await put_cached(self._SOURCE, key, raw)
            posts = [XHSPost.model_validate(item) for item in raw[: args.limit]]
            logger.info("xhs_tier1_scrape_ok", key=key, count=len(posts), mode=tier1_mode)
            return ToolResult(
                tool=self.name,
                output=posts,
                notes=f"scraped {len(posts)} posts via {tier1_mode} playwright, key {key!r}",
            )
        except Exception as exc:
            logger.warning(
                "xhs_tier1_failed",
                key=key,
                mode=tier1_mode,
                error=str(exc),
                error_type=type(exc).__name__,
                exc_info=True,
            )

        # --- Tier 2: DB cache ---------------------------------------
        cached_result = await self._load_cached_result(
            key,
            args.limit,
            note_prefix="cache",
            query=args.query,
        )
        if cached_result is not None:
            return cached_result

        # --- Tier 3: public search index fallback -------------------
        try:
            indexed = await self._fetch_from_search_index(args.query, args.limit)
            if indexed:
                indexed = await self._enrich_indexed_posts(indexed, args.limit)
                indexed = annotate_xhs_posts(indexed)
                indexed = mark_quality_checked_xhs_posts(
                    filter_query_relevant_xhs_posts(indexed, args.query),
                    args.query,
                )
                if not indexed:
                    logger.info("xhs_search_index_quality_miss", key=key)
                    raise RuntimeError("xhs search index returned no enriched relevant posts")
                await put_cached(self._SOURCE, key, indexed)
                posts = [XHSPost.model_validate(item) for item in indexed[: args.limit]]
                logger.info("xhs_search_index_hit", key=key, count=len(posts))
                return ToolResult(
                    tool=self.name,
                    output=posts,
                    notes=f"public search index hit {key!r} -> {len(posts)} posts",
                )
        except Exception as exc:
            logger.warning(
                "xhs_search_index_failed",
                key=key,
                error=str(exc),
                error_type=type(exc).__name__,
            )

        # --- Tier 4: fixture fallback ------------------------------
        raw_fixture = self._load_fixture_fallback(args.query, key)
        if raw_fixture:
            logger.warning("xhs_degraded_to_fixture", key=key, count=len(raw_fixture))
            fixture_posts = filter_query_relevant_xhs_posts(
                annotate_xhs_posts(raw_fixture), args.query
            )
            posts = [XHSPost.model_validate(item) for item in fixture_posts[: args.limit]]
            return ToolResult(
                tool=self.name,
                output=posts,
                notes=f"degraded to fixture {key!r} -> {len(posts)} posts",
            )

        logger.warning("xhs_total_failure", key=key)
        return ToolResult(
            tool=self.name,
            output=[],
            notes="degraded",
        )

    async def execute(self, args: XHSSearchInput) -> ToolResult[list[XHSPost]]:
        if get_tools_mode() == "fixture":
            return self._execute_fixture(args)
        return await self._execute_real(args)

    async def _load_cached_result(
        self,
        key: str,
        limit: int,
        *,
        note_prefix: str,
        query: str,
    ) -> ToolResult[list[XHSPost]] | None:
        try:
            cached = await get_cached(self._SOURCE, key)
        except Exception as exc:
            logger.warning("xhs_tier2_lookup_failed", key=key, error=str(exc))
            return None
        if cached:
            cached = filter_authentic_xhs_posts(annotate_xhs_posts(cached))
            cached = filter_query_relevant_xhs_posts(cached, query)
            if not cached:
                logger.info("xhs_cache_quality_miss", key=key, mode=note_prefix)
                return None
            posts = [XHSPost.model_validate(item) for item in cached[:limit]]
            if note_prefix == "cache" and _posts_need_image_enrichment(posts):
                enriched = await self._enrich_indexed_posts(
                    [post.model_dump(mode="json") for post in posts],
                    limit,
                )
                enriched = filter_authentic_xhs_posts(annotate_xhs_posts(enriched))
                enriched = filter_query_relevant_xhs_posts(enriched, query)
                if _has_more_images(cached, enriched):
                    await put_cached(self._SOURCE, key, enriched)
                    posts = [XHSPost.model_validate(item) for item in enriched[:limit]]
            logger.info("xhs_cache_hit", key=key, count=len(posts), mode=note_prefix)
            return ToolResult(
                tool=self.name,
                output=posts,
                notes=f"{note_prefix} cache hit {key!r} -> {len(posts)} posts",
            )
        if cached == []:
            logger.info("xhs_cache_empty_miss", key=key, mode=note_prefix)
        return None

    async def _fetch_from_search_index(self, query: str, limit: int) -> list[dict[str, object]]:
        """Return public XHS note URLs already indexed by a search engine.

        This is not an XHS API replacement. It only extracts note URLs and
        titles from public search-result HTML, giving the Joiner source URLs
        without cookies, login automation, or private endpoints.
        """
        parser = _SearchResultParser()
        web_posts: list[dict[str, object]] = []
        for search_query in _search_index_queries(query):
            for url, params in (
                (_DUCKDUCKGO_SEARCH_URL, {"q": search_query}),
                (_BING_SEARCH_URL, {"q": search_query}),
                (_SOGOU_SEARCH_URL, {"query": search_query}),
            ):
                try:
                    response = await self._get_client().get(url, params=params)
                    response.raise_for_status()
                except Exception as exc:
                    logger.warning(
                        "xhs_public_index_provider_failed",
                        provider=url,
                        query=search_query,
                        error=str(exc),
                        error_type=type(exc).__name__,
                    )
                    continue
                parser.feed(response.text)
                parser.feed(_links_from_text(response.text))
                posts = _posts_from_links(parser.links, query, limit)
                if posts:
                    web_posts = posts
                    break
            if web_posts:
                break
        if not web_posts:
            web_posts = _posts_from_links(parser.links, query, limit)
        image_posts: list[dict[str, object]] = []
        for image_query in _image_index_queries(query):
            with contextlib.suppress(Exception):
                response = await self._get_client().get(
                    _SOGOU_IMAGE_SEARCH_URL,
                    params={"query": image_query, "ie": "utf8"},
                )
                response.raise_for_status()
                image_posts = _posts_from_sogou_image_index_html(response.text, image_query, limit)
            if image_posts:
                break
        return _merge_index_posts(image_posts, web_posts, limit)

    async def _enrich_indexed_posts(
        self,
        posts: list[dict[str, object]],
        limit: int,
        *,
        timeout_s: float | None = None,
        images_per_post: int | None = None,
    ) -> list[dict[str, object]]:
        """Best-effort add note-detail text/images to public-index hits."""
        try:
            resolved_timeout_s = float(
                timeout_s if timeout_s is not None else os.getenv("XHS_TIMEOUT_S", "30")
            )
            resolved_images_per_post = int(
                images_per_post if images_per_post is not None else _images_per_post()
            )
            device_profile = _playwright_session._device_profile_for_fetch(None)
            context, close_context = await _playwright_session._open_scrape_context(
                user_agent=_playwright_session.pick_user_agent(
                    os.getenv("XHS_USER_AGENT"),
                    device_profile=device_profile,
                ),
                storage_state_path=None,
                profile_dir=None,
                device_profile=device_profile,
            )
            try:
                enriched = await _enrich_public_index_posts_with_context(
                    context,
                    [dict(post) for post in posts[:limit]],
                    timeout_s=resolved_timeout_s,
                    images_per_post=resolved_images_per_post,
                )
            finally:
                if close_context:
                    await context.close()
            return enriched
        except Exception as exc:
            logger.warning(
                "xhs_search_index_enrich_failed",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return posts

    def _load_fixture_fallback(self, query: str, key: str) -> list[dict[str, object]]:
        for candidate_key in _fixture_keys(query, key):
            raw = load_json_fixture(self._fixtures_dir, candidate_key)
            if raw:
                return raw
        return []


async def _enrich_public_index_posts_with_context(
    context: Any,
    posts: list[dict[str, object]],
    *,
    timeout_s: float,
    images_per_post: int,
) -> list[dict[str, object]]:
    if not posts:
        return []

    enriched = [dict(post) for post in posts]
    if _cache_images_enabled():
        image_index_posts = [
            post for post in enriched if post.get("xhs_image_index_stub") and post.get("images")
        ]
        if image_index_posts:
            cached_image_posts = await _playwright_session._cache_post_images_with_context(
                context,
                image_index_posts,
                images_per_post=images_per_post,
                timeout_s=min(timeout_s, 8.0),
            )
            cached_by_id = {_index_post_identity(post): post for post in cached_image_posts}
            enriched = [
                dict(cached_by_id.get(_index_post_identity(post), post)) for post in enriched
            ]

    detail_candidates = [
        post for post in enriched if _public_index_post_needs_detail_enrichment(post)
    ]
    if detail_candidates:
        detail_enriched = await _playwright_session._enrich_posts_from_details(
            context,
            detail_candidates,
            timeout_s=min(timeout_s, 8.0),
        )
        detail_by_id = {_index_post_identity(post): post for post in detail_enriched}
        enriched = [dict(detail_by_id.get(_index_post_identity(post), post)) for post in enriched]

    if _cache_images_enabled():
        uncached_image_posts = [
            post
            for post in enriched
            if post.get("images")
            and not any(str(image).startswith("/media/") for image in post.get("images") or [])
        ]
        if uncached_image_posts:
            cached_uncached_posts = await _playwright_session._cache_post_images_with_context(
                context,
                uncached_image_posts,
                images_per_post=images_per_post,
                timeout_s=min(timeout_s, 8.0),
            )
            cached_by_id = {_index_post_identity(post): post for post in cached_uncached_posts}
            enriched = [
                dict(cached_by_id.get(_index_post_identity(post), post)) for post in enriched
            ]

    return enriched


def _public_index_post_needs_detail_enrichment(post: dict[str, object]) -> bool:
    title = str(post.get("title") or "").strip()
    body = str(post.get("body") or "").strip()
    images = [str(image) for image in post.get("images") or []]
    has_local_image = any(image.startswith("/media/") for image in images)
    if post.get("xhs_image_index_stub") and title and (body or has_local_image):
        return False
    return not (
        post.get("xhs_index_stub")
        and not body
        and not images
        and title.casefold() in {"", "小红书", "xiaohongshu"}
    )


def annotate_xhs_posts(posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach source-quality fields used to separate real notes from soft ads."""
    return [annotate_xhs_post(post) for post in posts]


def annotate_xhs_post(post: dict[str, Any]) -> dict[str, Any]:
    assessed = assess_xhs_authenticity(post)
    updated = dict(post)
    updated["authenticity_score"] = assessed["score"]
    updated["is_promotional"] = assessed["is_promotional"]
    updated["promotion_signals"] = assessed["promotion_signals"]
    updated["local_signals"] = assessed["local_signals"]
    return updated


def filter_authentic_xhs_posts(posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop notes that look like merchant traffic acquisition, not local advice."""
    kept: list[dict[str, Any]] = []
    for post in annotate_xhs_posts(posts):
        score = _coerce_score(post.get("authenticity_score"))
        if score >= _MIN_AUTHENTICITY_SCORE and not post.get("is_promotional"):
            kept.append(post)
    return kept


def filter_query_relevant_xhs_posts(
    posts: list[dict[str, Any]], query: str
) -> list[dict[str, Any]]:
    terms = _query_relevance_terms(query)
    if not terms:
        return [post for post in posts if not post.get("xhs_index_stub")]
    kept: list[dict[str, Any]] = []
    for post in posts:
        if post.get("xhs_index_stub"):
            continue
        if (
            post.get("xhs_quality_version") == _CACHE_QUALITY_VERSION
            or _query_relevance_score(post, terms) >= _MIN_QUERY_RELEVANCE_SCORE
        ):
            kept.append(post)
    return kept


def mark_quality_checked_xhs_posts(posts: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    marked: list[dict[str, Any]] = []
    for post in posts:
        updated = dict(post)
        updated["xhs_quality_version"] = _CACHE_QUALITY_VERSION
        updated["xhs_query"] = query
        marked.append(updated)
    return marked


def _query_relevance_terms(query: str) -> list[str]:
    text = query
    for intent in _QUERY_INTENTS:
        text = re.sub(re.escape(intent), " ", text, flags=re.IGNORECASE)
    chunks = re.split(r"\s+|[/\u2014\u2013+&,()\uFF08\uFF09]", text)
    terms: list[str] = []
    for chunk in chunks:
        term = chunk.strip(" -_/,&")
        if not term or _looks_like_destination_only(term):
            continue
        if any(ord(char) > _ASCII_MAX_CODEPOINT for char in term):
            if len(_compact_relevance_text(term)) >= _MIN_CJK_QUERY_TERM_CHARS:
                terms.append(term)
        elif (
            len(term) >= _MIN_LATIN_QUERY_TERM_CHARS
            and term.casefold() not in _GENERIC_QUERY_ENTITY_TERMS
        ):
            terms.append(term)
    return _unique(terms)


def _query_relevance_score(post: dict[str, Any], terms: list[str]) -> float:
    text = " ".join(
        str(post.get(field) or "") for field in ("title", "body", "author", "url")
    ).casefold()
    compact_text = _compact_relevance_text(text)
    for term in terms:
        folded = term.casefold()
        compact = _compact_relevance_text(folded)
        if folded in text or compact in compact_text:
            return 1.0
    return 0.0


def _compact_relevance_text(text: str) -> str:
    return re.sub(
        r"[\W_]+", "", text.translate(CJK_NORMALIZATION_TABLE), flags=re.UNICODE
    ).casefold()


def _looks_like_destination_only(term: str) -> bool:
    return term.casefold() in {
        "tokyo",
        "东京",
        "kyoto",
        "京都",
        "osaka",
        "大阪",
        "sapporo",
        "札幌",
        "shanghai",
        "上海",
        "guangzhou",
        "广州",
        "hakone",
        "箱根",
        "marrakech",
        "马拉喀什",
        "delhi",
        "德里",
    }


def assess_xhs_authenticity(post: dict[str, Any]) -> dict[str, Any]:
    title = str(post.get("title") or "")
    body = str(post.get("body") or "")
    author = str(post.get("author") or "")
    text = f"{title}\n{body}"
    lowered = text.casefold()
    author_lowered = author.casefold()

    score = 0.5
    promotion_signals: list[str] = []
    local_signals: list[str] = []

    hard_terms = _matched_terms(lowered, _PROMOTION_HARD_TERMS)
    if "广告" in hard_terms and ("不是广告" in lowered or "非广告" in lowered):
        hard_terms.remove("广告")
    if hard_terms:
        promotion_signals.extend(f"hard:{term}" for term in hard_terms[:8])
        score -= min(0.45, 0.18 * len(hard_terms))
    if _CONTACT_RE.search(lowered):
        promotion_signals.append("hard:contact_info")
        score -= 0.3

    soft_terms = _matched_terms(lowered, _PROMOTION_SOFT_TERMS)
    if soft_terms:
        promotion_signals.extend(f"soft:{term}" for term in soft_terms[:8])
        score -= min(0.24, 0.06 * len(soft_terms))

    merchant_terms = _matched_terms(author_lowered, _MERCHANT_AUTHOR_TERMS)
    if merchant_terms:
        promotion_signals.extend(f"author:{term}" for term in merchant_terms[:4])
        score -= 0.25

    local_terms = _matched_terms(lowered, _LOCAL_SIGNAL_TERMS)
    if local_terms:
        local_signals.extend(local_terms[:10])
        score += min(0.3, 0.06 * len(local_terms))
    if _DETAIL_RE.search(lowered):
        local_signals.append("specific_detail")
        score += 0.12

    length_score, length_signal = _body_length_signal(body)
    score += length_score
    if length_signal:
        local_signals.append(length_signal)

    if post.get("images"):
        score += 0.05
    else:
        score -= 0.05

    if (
        len(soft_terms) >= _SOFT_PROMO_PILEUP_COUNT
        and not local_terms
        and not _DETAIL_RE.search(lowered)
    ):
        score -= 0.12

    score = round(max(0.0, min(1.0, score)), 2)
    is_promotional = bool(hard_terms or merchant_terms or _CONTACT_RE.search(lowered)) or (
        score < _MIN_AUTHENTICITY_SCORE
    )
    return {
        "score": score,
        "is_promotional": is_promotional,
        "promotion_signals": _unique(promotion_signals),
        "local_signals": _unique(local_signals),
    }


def _matched_terms(text: str, terms: tuple[str, ...]) -> list[str]:
    return [term for term in terms if term.casefold() in text]


def _body_length_signal(body: str) -> tuple[float, str | None]:
    compact_body = "".join(body.split())
    length = len(compact_body)
    if length >= _LONG_PERSONAL_NOTE_CHARS:
        return 0.08, "long_personal_note"
    if length >= _MEDIUM_NOTE_CHARS:
        return 0.04, "medium_note"
    if length < _THIN_NOTE_CHARS:
        return -0.12, None
    return 0.0, None


def _unique(items: list[str]) -> list[str]:
    out: list[str] = []
    for item in items:
        if item not in out:
            out.append(item)
    return out


def _coerce_score(raw: object) -> float:
    try:
        return float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _posts_from_links(
    links: list[tuple[str, str]], query: str, limit: int
) -> list[dict[str, object]]:
    posts: list[dict[str, object]] = []
    seen: set[str] = set()
    for href, title in links:
        url = _normalise_xhs_url(href)
        if url is None or url in seen:
            continue
        seen.add(url)
        match = _XHS_NOTE_RE.search(url)
        post_id = match.group(1) if match else f"idx_{len(posts) + 1}"
        clean_title = " ".join(unescape(title).split())[:160]
        posts.append(
            {
                "id": post_id,
                "author": "public search index",
                "title": clean_title or query,
                "body": "",
                "likes": 0,
                "comments": 0,
                "url": url,
                "images": [],
                "xhs_index_query": query,
                "xhs_index_stub": True,
            }
        )
        if len(posts) >= limit:
            break
    return posts


def _posts_from_sogou_image_index_html(
    text: str, query: str, limit: int
) -> list[dict[str, object]]:
    posts: list[dict[str, object]] = []
    seen: set[str] = set()
    for item in _sogou_image_index_items(text):
        if not isinstance(item, dict):
            continue
        title = " ".join(str(item.get("title") or item.get("content_title") or "").split())
        body = " ".join(str(item.get("content_major") or item.get("summary") or "").split())
        raw_page_url = str(
            item.get("page_url") or item.get("pageUrl") or item.get("url") or item.get("link") or ""
        )
        page_url = _normalise_xhs_url(raw_page_url) if raw_page_url else None
        image_url = _first_sogou_xhs_image_url(item)
        if not page_url or not image_url or page_url in seen:
            continue
        seen.add(page_url)
        match = _XHS_NOTE_RE.search(page_url)
        post_id = match.group(1) if match else f"img_{len(posts) + 1}"
        posts.append(
            {
                "id": post_id,
                "author": "public image index",
                "title": title or query,
                "body": body,
                "likes": 0,
                "comments": 0,
                "url": page_url,
                "images": [image_url],
                "xhs_index_query": query,
                "xhs_image_index_stub": True,
            }
        )
        if len(posts) >= limit:
            break
    return posts


def _merge_index_posts(
    primary: list[dict[str, object]],
    fallback: list[dict[str, object]],
    limit: int,
) -> list[dict[str, object]]:
    merged: list[dict[str, object]] = []
    seen: set[str] = set()
    for post in [*primary, *fallback]:
        key = _index_post_identity(post)
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(post)
        if len(merged) >= limit:
            break
    return merged


def _index_post_identity(post: dict[str, object]) -> str:
    url = str(post.get("url") or "")
    match = _XHS_NOTE_RE.search(url)
    if match:
        return match.group(1)
    return str(post.get("id") or "")


def _sogou_image_index_items(text: str) -> list[object]:
    marker = '"searchList"'
    index = text.find(marker)
    if index < 0:
        return []
    bracket = text.find("[", index)
    if bracket < 0:
        return []
    depth = 0
    in_string = False
    escaped = False
    for pos in range(bracket, len(text)):
        char = text[pos]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                with contextlib.suppress(json.JSONDecodeError):
                    parsed = json.loads(text[bracket : pos + 1])
                    return parsed if isinstance(parsed, list) else []
                return []
    return []


def _first_sogou_xhs_image_url(item: dict[str, object]) -> str | None:
    for key in ("pic_url", "ori_pic_url", "thumbUrl", "thumb_url", "picUrl"):
        raw = item.get(key)
        if not isinstance(raw, str) or not raw:
            continue
        url = raw.replace("\\/", "/")
        if _is_likely_public_xhs_image(url):
            return url
    return None


def _is_likely_public_xhs_image(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    host = parsed.netloc.lower()
    lowered = url.lower()
    if any(marker in lowered for marker in ("avatar", "favicon", "icon", "logo")):
        return False
    return "xhscdn.com" in host or host.endswith("xiaohongshu.com")


def _search_index_queries(query: str) -> tuple[str, ...]:
    cleaned = " ".join(query.split())
    without_recommend = re.sub(
        r"\b(recommend|recommended|推荐)\b", " ", cleaned, flags=re.IGNORECASE
    )
    without_recommend = " ".join(without_recommend.split())
    candidates = [
        f"site:xiaohongshu.com/explore {cleaned}",
        f"site:xiaohongshu.com/discovery/item {cleaned}",
        f"xiaohongshu.com/explore {cleaned}",
        f"小红书 {cleaned}",
    ]
    if without_recommend and without_recommend != cleaned:
        candidates.extend(
            [
                f"site:xiaohongshu.com/explore {without_recommend}",
                f"小红书 {without_recommend}",
            ]
        )
    unique: list[str] = []
    for item in candidates:
        if item not in unique:
            unique.append(item)
    return tuple(unique)


def _image_index_queries(query: str) -> tuple[str, ...]:
    cleaned = " ".join(query.split())
    without_intents = cleaned
    for intent in _QUERY_INTENTS:
        without_intents = without_intents.replace(intent, " ")
    without_intents = " ".join(without_intents.split())

    candidates = [cleaned]
    if cleaned and not cleaned.startswith("小红书"):
        candidates.append(f"小红书 {cleaned}")
    if without_intents and without_intents != cleaned:
        candidates.append(without_intents)
        if not without_intents.startswith("小红书"):
            candidates.append(f"小红书 {without_intents}")

    unique: list[str] = []
    for item in candidates:
        if item and item not in unique:
            unique.append(item)
    return tuple(unique)


def xhs_cache_key(query: str) -> str:
    """Cache XHS mixed Chinese/Latin queries without losing intent words.

    The shared ``cache_key`` intentionally keeps ASCII-friendly slugs for
    fixture filenames. XHS live queries are often mixed strings such as
    ``东京 Afuri 美食推荐`` and ``东京 Afuri 本地人推荐``; the shared key would
    collapse both to ``afuri``. Add a short query hash only for mixed
    non-ASCII queries so ASCII fixtures/tests keep their historical keys.
    """
    key = cache_key(query)
    has_non_ascii = any(ord(char) > _ASCII_MAX_CODEPOINT for char in query)
    if has_non_ascii and not key.startswith("x"):
        return f"{key}__{hashlib.sha256(query.encode('utf-8')).hexdigest()[:12]}"
    return key


def _prefer_cache() -> bool:
    return os.getenv("XHS_PREFER_CACHE", "1").strip().lower() not in {"0", "false", "no"}


def _use_configured_session() -> bool:
    """Opt in to legacy cookie/storage/profile reuse.

    Public XHS crawling should not silently depend on authentication state just
    because a developer has old environment variables set locally.
    """
    return os.getenv("XHS_USE_CONFIGURED_SESSION", "0").strip().lower() in {"1", "true", "yes"}


def _configured_session_values() -> tuple[str | None, str | None, str | None]:
    if not _use_configured_session():
        return None, None, None
    return (
        os.getenv("XHS_COOKIE") or None,
        os.getenv("XHS_PROFILE_DIR") or None,
        os.getenv("XHS_STORAGE_STATE") or None,
    )


def _cache_images_enabled() -> bool:
    return os.getenv("XHS_CACHE_IMAGES", "1").strip().lower() not in {"0", "false", "no"}


def _images_per_post() -> int:
    raw = os.getenv("XHS_IMAGES_PER_POST", "3")
    try:
        return max(0, int(raw))
    except ValueError:
        return 3


def _posts_need_image_enrichment(posts: list[XHSPost]) -> bool:
    return bool(posts) and all(not post.images for post in posts)


def _has_more_images(before: list[dict[str, object]], after: list[dict[str, object]]) -> bool:
    before_count = sum(len(item.get("images") or []) for item in before)
    after_count = sum(len(item.get("images") or []) for item in after)
    return after_count > before_count


class _SearchResultParser(HTMLParser):
    """Tiny link collector for public search-result HTML."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attr_map = {k.lower(): v or "" for k, v in attrs}
        href = attr_map.get("href", "")
        if not _normalise_xhs_url(href):
            return
        self._href = href
        self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self._href is None:
            return
        self.links.append((self._href, " ".join(self._text)))
        self._href = None
        self._text = []


def _links_from_text(text: str) -> str:
    links = re.findall(
        r"https?://(?:www\.)?xiaohongshu\.com/(?:explore|search_result)/[A-Za-z0-9]+(?:\?[^\s\"'<>]+)?|https?://(?:www\.)?xiaohongshu\.com/discovery/item/(?:sgh/)?[A-Za-z0-9]+(?:\?[^\s\"'<>]+)?",
        text,
        flags=re.IGNORECASE,
    )
    if not links:
        return ""
    anchors = []
    for raw_href in links:
        href = _normalise_xhs_url(raw_href)
        if not href:
            continue
        match = _XHS_NOTE_RE.search(href)
        note_id = match.group(1) if match else href
        anchors.append(f'<a href="{escape(href, quote=True)}">{escape(note_id)}</a>')
    return "\n".join(anchors)


def _fixture_keys(query: str, key: str) -> tuple[str, ...]:
    keys: list[str] = [key]
    legacy_key = cache_key(query)
    if legacy_key != key:
        keys.append(legacy_key)
    cleaned = re.sub(r"\b(recommend|recommended|推荐)\b", " ", query, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if cleaned:
        keys.append(cache_key(cleaned))

    lower = query.lower()
    if any(
        term in lower
        for term in (
            "tokyo",
            "ramen",
            "menya",
            "ichiran",
            "tsukemen",
            "shoyu",
            "shio",
            "tonkotsu",
            "niboshi",
            "paitan",
            "hototogisu",
            "kagari",
            "afuri",
            "nakiryu",
            "rokurinsha",
            "yoroiya",
            "mensho",
            "soranoiro",
            "hachigou",
            "musashi",
            "bigiya",
        )
    ):
        keys.append("tokyo_ramen_tonkotsu")

    unique: list[str] = []
    for item in keys:
        if item not in unique:
            unique.append(item)
    return tuple(unique)


def _normalise_xhs_url(raw_href: str) -> str | None:
    """Extract a canonical XHS note URL from direct or search-engine redirect links."""
    href = unescape(raw_href)
    parsed = urlparse(href)
    query_params = parse_qs(parsed.query)
    redirect_target = _redirect_target_from_query(query_params)
    if redirect_target:
        href = redirect_target
        parsed = urlparse(href)
    match = _XHS_NOTE_RE.search(href)
    if not match:
        return None
    note_id = match.group(1)
    base = f"https://www.xiaohongshu.com/explore/{note_id}"
    if parsed.query:
        keep = {
            key: value[0]
            for key, value in parse_qs(parsed.query).items()
            if key in {"xsec_token", "xsec_source"} and value
        }
        if keep:
            base = f"{base}?{urlencode(keep)}"
    return base


def _redirect_target_from_query(query_params: dict[str, list[str]]) -> str:
    for key in ("uddg", "u", "url", "target", "q"):
        for raw_value in query_params.get(key, []):
            value = _decode_redirect_value(raw_value)
            if "xiaohongshu.com" in value:
                return value
    return ""


def _decode_redirect_value(raw_value: str) -> str:
    value = unquote(raw_value).strip()
    if value.startswith("a1"):
        encoded = value[2:]
        padding = "=" * (-len(encoded) % 4)
        with contextlib.suppress(Exception):
            decoded = base64.urlsafe_b64decode(f"{encoded}{padding}").decode(
                "utf-8", errors="ignore"
            )
            if decoded:
                return unquote(decoded).strip()
    return value
