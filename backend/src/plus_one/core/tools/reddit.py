"""Reddit search tool — fixture-backed in default mode, JSON-backed in real mode.

Real mode (ADR-007) hits the unauthenticated public endpoint
``https://www.reddit.com/r/{sub}/search.json`` via ``httpx.AsyncClient``,
relying on OS-level ``HTTPS_PROXY`` / ``NO_PROXY`` env vars rather than
in-Python proxy logic. No PRAW, no credentials.

Behavior:

  * Cache-or-fetch: look up DB cache first, fall back to the JSON
    endpoint, then write the response back to the cache for TTL (24h,
    set in ``_cache_db.py::_TTL_BY_SOURCE``).
  * Concurrency-bounded by a module-level ``asyncio.Semaphore(3)`` and
    a 1.0s minimum interval between starts of the HTTP call.
  * Every failure mode (network, HTTP error, bad JSON) returns
    ``ToolResult(ok=True, output=[], notes=...)`` so the joiner's
    empty-evidence fallback is preserved — we never raise out of
    ``execute``.
"""

from __future__ import annotations

import asyncio
import os
import re
import time
from pathlib import Path
from typing import Any, ClassVar

import httpx
import structlog
from pydantic import BaseModel, ConfigDict, Field, field_validator

from plus_one.config import settings
from plus_one.core.agents.framework.tools import ToolResult
from plus_one.core.tools._cache import cache_key, load_json_fixture
from plus_one.core.tools._cache_db import get_cached, put_cached
from plus_one.core.tools._mode import get_tools_mode

logger = structlog.get_logger()

# Module-level rate limiter — shared across all instances of the tool
# within one process (one process per worker per ADR-006).
_REDDIT_SEMAPHORE = asyncio.Semaphore(3)
_MIN_INTERVAL_S = 1.0
_last_call_lock = asyncio.Lock()
# Mutable state lives inside a single-slot list so we don't need
# ``global`` (ruff PLW0603). The list itself is module-level immutable.
_last_call_monotonic: list[float] = [0.0]


def _make_client() -> httpx.AsyncClient:
    """Construct the async HTTP client. Monkeypatch seam for tests.

    Reads ``PLUS_ONE_REDDIT_PROXY`` (dedicated, opt-in) rather than the
    OS-wide ``HTTPS_PROXY`` so we can route Reddit through a GFW bypass
    without also routing Maestro / localhost traffic through it.
    """
    ua = os.getenv("REDDIT_USER_AGENT", "plus-one/0.1 (+contact via repo)")
    proxy = os.getenv("PLUS_ONE_REDDIT_PROXY") or None
    return httpx.AsyncClient(
        headers={"User-Agent": ua},
        timeout=15.0,
        follow_redirects=True,
        proxy=proxy,
    )


async def _rate_limit() -> None:
    """Enforce a 1s minimum gap between starts of Reddit calls."""
    async with _last_call_lock:
        now = time.monotonic()
        elapsed = now - _last_call_monotonic[0]
        if elapsed < _MIN_INTERVAL_S:
            await asyncio.sleep(_MIN_INTERVAL_S - elapsed)
        _last_call_monotonic[0] = time.monotonic()


class RedditPost(BaseModel):
    """One post (or comment) lifted from Reddit."""

    model_config = ConfigDict(frozen=True)

    id: str
    subreddit: str
    title: str
    body: str = ""
    author: str
    score: int = 0
    permalink: str
    created_utc: float | None = None


_SUBREDDIT_RE = re.compile(r"^[A-Za-z0-9_]{1,50}$")


class RedditSearchInput(BaseModel):
    """Args for ``reddit_search``."""

    query: str = Field(min_length=1, max_length=200)
    subreddits: tuple[str, ...] = Field(default=())
    limit: int = Field(default=25, ge=1, le=100)

    @field_validator("subreddits")
    @classmethod
    def _check_subreddits(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        for sub in v:
            if not _SUBREDDIT_RE.match(sub):
                raise ValueError(
                    f"invalid subreddit name {sub!r} — must match {_SUBREDDIT_RE.pattern}"
                )
        return v


class RedditSearchTool:
    """Reddit search.

    Cache key is built from ``query`` plus the (sorted) subreddit list,
    so a fixture file ``tokyo_ramen_tonkotsu__japantravel__ramen.json``
    services the query "tokyo ramen tonkotsu" restricted to
    r/JapanTravel and r/ramen. The same cache key is also used as the
    DB cache lookup key in real mode.
    """

    name: ClassVar[str] = "reddit_search"
    input_schema: ClassVar[type[BaseModel]] = RedditSearchInput
    is_concurrency_safe: ClassVar[bool] = True

    _SOURCE: ClassVar[str] = "reddit"

    def __init__(self, fixtures_dir: Path | None = None) -> None:
        self._fixtures_dir = (fixtures_dir or settings.fixtures_dir) / "reddit"
        # ADR-007: no credentials required. UA defaulted in _make_client().

    # === fixture mode (unchanged behavior) ===========================

    def _execute_fixture(self, args: RedditSearchInput) -> ToolResult[list[RedditPost]]:
        key = cache_key(args.query, *sorted(args.subreddits))
        raw = load_json_fixture(self._fixtures_dir, key)
        posts = [RedditPost.model_validate(item) for item in raw[: args.limit]]
        return ToolResult(
            tool=self.name,
            output=posts,
            notes=f"loaded {len(posts)} posts from cache key {key!r}",
        )

    # === real mode ===================================================

    async def _fetch_from_json(
        self, query: str, subreddits: tuple[str, ...], limit: int
    ) -> list[dict[str, Any]]:
        """Hit ``/r/{subs}/search.json`` and map to RedditPost dict shape.

        Lets ``httpx.HTTPStatusError`` / ``ConnectError`` / ``TimeoutException``
        propagate to ``_execute_real`` which converts them to empty results.
        Raises ``ValueError`` on JSON decode failure.
        """
        target = "+".join(sorted(subreddits)) if subreddits else "all"
        url = f"https://www.reddit.com/r/{target}/search.json"
        params = {
            "q": query,
            "restrict_sr": "1",
            "limit": str(limit),
            "raw_json": "1",
        }
        async with _make_client() as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            try:
                body = resp.json()
            except Exception as exc:
                raise ValueError(f"reddit returned non-JSON body: {exc}") from exc

        children = body.get("data", {}).get("children") or []
        out: list[dict[str, Any]] = []
        for child in children:
            data = child.get("data") or {}
            permalink_raw = data.get("permalink", "") or ""
            permalink = (
                f"https://reddit.com{permalink_raw}"
                if permalink_raw.startswith("/")
                else permalink_raw
            )
            out.append(
                {
                    "id": str(data.get("id", "")),
                    "subreddit": str(data.get("subreddit", "")),
                    "title": str(data.get("title", "") or ""),
                    "body": str(data.get("selftext", "") or ""),
                    "author": str(data.get("author", "[deleted]") or "[deleted]"),
                    "score": int(data.get("score", 0) or 0),
                    "permalink": permalink,
                    "created_utc": (
                        float(data["created_utc"])
                        if data.get("created_utc") is not None
                        else None
                    ),
                }
            )
        return out

    async def _execute_real(self, args: RedditSearchInput) -> ToolResult[list[RedditPost]]:
        key = cache_key(args.query, *sorted(args.subreddits))
        cached = await get_cached(self._SOURCE, key)
        if cached is not None:
            posts = [RedditPost.model_validate(item) for item in cached[: args.limit]]
            logger.info("reddit_cache_hit", key=key, count=len(posts))
            return ToolResult(
                tool=self.name,
                output=posts,
                notes=f"cache hit {key!r} -> {len(posts)} posts",
            )

        async with _REDDIT_SEMAPHORE:
            await _rate_limit()
            try:
                raw = await self._fetch_from_json(
                    args.query,
                    tuple(sorted(args.subreddits)),
                    args.limit,
                )
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                logger.warning("reddit_network_error", key=key, error=str(exc))
                return ToolResult(
                    tool=self.name,
                    ok=True,
                    output=[],
                    notes=f"reddit network error: {exc}",
                )
            except httpx.HTTPStatusError as exc:
                logger.warning(
                    "reddit_http_error",
                    key=key,
                    status=exc.response.status_code,
                )
                return ToolResult(
                    tool=self.name,
                    ok=True,
                    output=[],
                    notes=f"reddit http {exc.response.status_code}: {exc}",
                )
            except Exception as exc:
                logger.warning("reddit_fetch_failed", key=key, error=str(exc))
                return ToolResult(
                    tool=self.name,
                    ok=True,
                    output=[],
                    notes=f"reddit fetch failed: {exc}",
                )

        await put_cached(self._SOURCE, key, raw)
        posts = [RedditPost.model_validate(item) for item in raw[: args.limit]]
        return ToolResult(
            tool=self.name,
            output=posts,
            notes=f"fetched {len(posts)} posts via json, key {key!r}",
        )

    async def execute(self, args: RedditSearchInput) -> ToolResult[list[RedditPost]]:
        if get_tools_mode() == "fixture":
            return self._execute_fixture(args)
        return await self._execute_real(args)
