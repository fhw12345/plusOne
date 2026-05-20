"""Xiaohongshu (RedNote) search tool — 3-tier scraper per ADR-003.

Mode is resolved per-call via ``get_tools_mode()``. Real-mode behavior
implements the ADR-003-mandated 3-tier fallback (see PRD Batch 2k §5):

  * **Tier 1** — live Playwright scrape via ``_playwright_session.fetch``.
    On success the payload is written to ``tool_cache`` (TTL 7d).
  * **Tier 2** — if tier 1 raises (timeout / 429 / captcha / network),
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
from pathlib import Path
from typing import ClassVar

import structlog
from pydantic import BaseModel, ConfigDict, Field

from plus_one.config import settings
from plus_one.core.agents.framework.tools import ToolResult
from plus_one.core.tools import _playwright_session
from plus_one.core.tools._cache import cache_key, load_json_fixture
from plus_one.core.tools._cache_db import get_cached, put_cached
from plus_one.core.tools._mode import get_tools_mode, require_env

logger = structlog.get_logger()


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
        # Fail loud at construction time when mode=real and the single
        # supported cookie env var is missing. ``require_env`` is a
        # no-op when mode=fixture so CI / e2e are unaffected.
        require_env("XHS_COOKIE", tool=self.name)

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
        try:
            scrape = await _playwright_session.fetch(
                args.query,
                cookie=os.environ["XHS_COOKIE"],
                limit=args.limit,
                user_agent=os.getenv("XHS_USER_AGENT"),
                timeout_s=float(os.getenv("XHS_TIMEOUT_S", "30")),
            )
            raw = scrape.posts
            # Cache even an empty result — the next call within TTL
            # should skip the scrape rather than re-hammering XHS.
            await put_cached(self._SOURCE, key, raw)
            posts = [XHSPost.model_validate(item) for item in raw[: args.limit]]
            logger.info("xhs_tier1_scrape_ok", key=key, count=len(posts))
            return ToolResult(
                tool=self.name,
                output=posts,
                notes=f"scraped {len(posts)} posts via playwright, key {key!r}",
            )
        except Exception as exc:
            logger.warning("xhs_tier1_failed", key=key, error=str(exc))

        # --- Tier 2: DB cache ---------------------------------------
        try:
            cached = await get_cached(self._SOURCE, key)
        except Exception as exc:
            logger.warning("xhs_tier2_lookup_failed", key=key, error=str(exc))
            cached = None
        if cached is not None:
            posts = [XHSPost.model_validate(item) for item in cached[: args.limit]]
            logger.info("xhs_cache_hit", key=key, count=len(posts))
            return ToolResult(
                tool=self.name,
                output=posts,
                notes=f"cache hit {key!r} -> {len(posts)} posts",
            )

        # --- Tier 3: fixture fallback ------------------------------
        raw_fixture = load_json_fixture(self._fixtures_dir, key)
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
