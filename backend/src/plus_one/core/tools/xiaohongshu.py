"""Xiaohongshu (RedNote) search tool — 3-tier scraper per ADR-003.

Mode is resolved per-call via ``get_tools_mode()``. Real-mode behavior
implements the ADR-003-mandated 3-tier fallback (see PRD Batch 2k §5):

  * **Tier 1** — live Playwright scrape via ``_playwright_session.fetch``.
    When ``XHS_COOKIE`` is configured it is injected; otherwise the tool
    tries the logged-out public web page. On success the payload is
    written to ``tool_cache`` (TTL 7d).
  * **Tier 2** — if tier 1 is unavailable or raises (timeout / 429 / captcha / network),
    look up ``tool_cache`` and serve a cached payload if present (and
    not expired).
  * **Tier 3** — if cache miss too, fall back to the curated fixture
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

import os
import re
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import ClassVar
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
_SEARCH_INDEX_UA = "plus-one-xhs-public-index/0.1"
_XHS_NOTE_RE = re.compile(
    r"https?://(?:www\.)?xiaohongshu\.com/(?:explore|discovery/item)/([A-Za-z0-9]+)",
    re.IGNORECASE,
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
        # XHS live scraping can use a user-supplied cookie, but the tool
        # first tries a logged-out public browser session without one.
        # Cache/fixtures/empty output keep the Chinese-source slot live
        # when XHS gates or throttles the public page.

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        self._client = httpx.AsyncClient(
            headers={"User-Agent": _SEARCH_INDEX_UA, "Accept": "text/html,application/xhtml+xml"},
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
        key = cache_key(args.query)

        # --- Tier 1: live scrape ------------------------------------
        cookie = os.getenv("XHS_COOKIE") or None
        tier1_mode = "cookie" if cookie else "public"
        try:
            scrape = await _playwright_session.fetch(
                args.query,
                cookie=cookie,
                limit=args.limit,
                user_agent=os.getenv("XHS_USER_AGENT"),
                timeout_s=float(os.getenv("XHS_TIMEOUT_S", "30")),
            )
            raw = scrape.posts
            preflight_posts = [XHSPost.model_validate(item) for item in raw[: args.limit]]
            if not preflight_posts:
                logger.info("xhs_tier1_scrape_empty", key=key, mode=tier1_mode)
                raise RuntimeError("xhs tier1 returned 0 posts")
            # Cache even an empty result — the next call within TTL
            # should skip the scrape rather than re-hammering XHS.
            # Only non-empty tier-1 results reach this point.
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
            )

        # --- Tier 2: DB cache ---------------------------------------
        try:
            cached = await get_cached(self._SOURCE, key)
        except Exception as exc:
            logger.warning("xhs_tier2_lookup_failed", key=key, error=str(exc))
            cached = None
        if cached:
            posts = [XHSPost.model_validate(item) for item in cached[: args.limit]]
            logger.info("xhs_cache_hit", key=key, count=len(posts))
            return ToolResult(
                tool=self.name,
                output=posts,
                notes=f"cache hit {key!r} -> {len(posts)} posts",
            )
        if cached == []:
            logger.info("xhs_cache_empty_miss", key=key)

        # --- Tier 3: public search index fallback -------------------
        if cookie is None:
            try:
                indexed = await self._fetch_from_search_index(args.query, args.limit)
                if indexed:
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
            posts = [XHSPost.model_validate(item) for item in raw_fixture[: args.limit]]
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

    async def _fetch_from_search_index(self, query: str, limit: int) -> list[dict[str, object]]:
        """Return public XHS note URLs already indexed by a search engine.

        This is not an XHS API replacement. It only extracts note URLs and
        titles from public search-result HTML, giving the Joiner source URLs
        without cookies, login automation, or private endpoints.
        """
        parser = _SearchResultParser()
        search_query = f"site:xiaohongshu.com/explore {query}"
        for url, params in (
            (_DUCKDUCKGO_SEARCH_URL, {"q": search_query}),
            (_BING_SEARCH_URL, {"q": search_query}),
        ):
            try:
                response = await self._get_client().get(url, params=params)
                response.raise_for_status()
            except Exception as exc:
                logger.warning(
                    "xhs_public_index_provider_failed",
                    provider=url,
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
                continue
            parser.feed(response.text)
            parser.feed(_links_from_text(response.text))

        posts: list[dict[str, object]] = []
        seen: set[str] = set()
        for href, title in parser.links:
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
                    "body": f"publicly indexed xhs result for: {query}",
                    "likes": 0,
                    "comments": 0,
                    "url": url,
                    "images": [],
                }
            )
            if len(posts) >= limit:
                break
        return posts

    def _load_fixture_fallback(self, query: str, key: str) -> list[dict[str, object]]:
        for candidate_key in _fixture_keys(query, key):
            raw = load_json_fixture(self._fixtures_dir, candidate_key)
            if raw:
                return raw
        return []


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
        if "xiaohongshu.com" not in href and "uddg=" not in href and "/l/?" not in href:
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
    links = _XHS_NOTE_RE.findall(text)
    if not links:
        return ""
    anchors = []
    for note_id in links:
        href = f"https://www.xiaohongshu.com/explore/{note_id}"
        anchors.append(f'<a href="{href}">{note_id}</a>')
    return "\n".join(anchors)


def _fixture_keys(query: str, key: str) -> tuple[str, ...]:
    keys: list[str] = [key]
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
    """Extract a canonical XHS note URL from direct or DDG redirect links."""
    href = unescape(raw_href)
    parsed = urlparse(href)
    query_params = parse_qs(parsed.query)
    if "duckduckgo.com" in parsed.netloc or "uddg" in query_params:
        uddg = query_params.get("uddg", [""])[0]
        if not uddg:
            return None
        href = unquote(uddg)
        parsed = urlparse(href)
    match = _XHS_NOTE_RE.search(href)
    if not match:
        return None
    base = f"https://www.xiaohongshu.com/{parsed.path.strip('/')}"
    if parsed.query:
        keep = {
            key: value[0]
            for key, value in parse_qs(parsed.query).items()
            if key in {"xsec_token", "xsec_source"} and value
        }
        if keep:
            base = f"{base}?{urlencode(keep)}"
    return base
