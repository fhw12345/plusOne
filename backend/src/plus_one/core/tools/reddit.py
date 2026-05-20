"""Reddit search tool — fixture-backed in default mode, PRAW-backed in real mode.

Mode is resolved per-call via ``get_tools_mode()`` (see ``_mode.py``).
Real-mode behavior:

  * Lazy PRAW client construction in ``__init__`` — fails loud if
    required creds are missing (``REDDIT_CLIENT_ID`` etc).
  * Cache-or-fetch: look up DB cache first, fall back to PRAW
    (wrapped in ``asyncio.to_thread`` since PRAW is sync), then write
    the response back to the cache for TTL (24h, set in
    ``_cache_db.py::_TTL_BY_SOURCE``).
  * Concurrency-bounded by a module-level ``asyncio.Semaphore(3)`` and
    a 1.0s minimum interval between starts of the PRAW call (PRD §4.4).
"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from typing import Any, ClassVar

import structlog
from pydantic import BaseModel, ConfigDict, Field

from plus_one.config import settings
from plus_one.core.agents.framework.tools import ToolResult
from plus_one.core.tools._cache import cache_key, load_json_fixture
from plus_one.core.tools._cache_db import get_cached, put_cached
from plus_one.core.tools._mode import get_tools_mode, require_env

logger = structlog.get_logger()

# Module-level rate limiter — shared across all instances of the tool
# within one process (one process per worker per ADR-006).
_REDDIT_SEMAPHORE = asyncio.Semaphore(3)
_MIN_INTERVAL_S = 1.0
_last_call_lock = asyncio.Lock()
# Mutable state lives inside a single-slot list so we don't need
# ``global`` (ruff PLW0603). The list itself is module-level immutable.
_last_call_monotonic: list[float] = [0.0]


async def _rate_limit() -> None:
    """Enforce a 1s minimum gap between starts of PRAW calls.

    Held under ``_last_call_lock`` so concurrent callers serialize the
    interval check; the actual sleep happens BEFORE releasing the lock
    so the gap is enforced even when called from many tasks at once.
    The semaphore (acquired by the caller) caps concurrency at 3 on
    top of this.
    """
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


class RedditSearchInput(BaseModel):
    """Args for ``reddit_search``."""

    query: str = Field(min_length=1, max_length=200)
    subreddits: tuple[str, ...] = Field(default=())
    limit: int = Field(default=25, ge=1, le=100)


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
        # In real mode, fail loud at construction if any required env
        # is missing. The PRAW client itself is built lazily so fixture
        # mode (CI / e2e / dev) never imports praw needlessly.
        require_env(
            "REDDIT_CLIENT_ID",
            "REDDIT_CLIENT_SECRET",
            "REDDIT_USER_AGENT",
            tool=self.name,
        )
        self._reddit_client: Any | None = None

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

    def _get_reddit_client(self) -> Any:
        """Lazily build a PRAW ``Reddit`` client. Cached on the instance."""
        if self._reddit_client is not None:
            return self._reddit_client
        # Local import so fixture-mode imports stay cheap and praw stays
        # an optional runtime dep.
        import praw  # noqa: PLC0415

        self._reddit_client = praw.Reddit(
            client_id=os.environ["REDDIT_CLIENT_ID"],
            client_secret=os.environ["REDDIT_CLIENT_SECRET"],
            user_agent=os.environ["REDDIT_USER_AGENT"],
            check_for_async=False,
        )
        return self._reddit_client

    def _fetch_from_praw_sync(
        self, query: str, subreddits: tuple[str, ...], limit: int
    ) -> list[dict[str, Any]]:
        """Blocking PRAW call. Always run via ``asyncio.to_thread``."""
        client = self._get_reddit_client()
        target = "+".join(sorted(subreddits)) if subreddits else "all"
        out: list[dict[str, Any]] = []
        for submission in client.subreddit(target).search(query, limit=limit):
            out.append(
                {
                    "id": str(submission.id),
                    "subreddit": str(submission.subreddit.display_name),
                    "title": str(submission.title or ""),
                    "body": str(getattr(submission, "selftext", "") or ""),
                    "author": str(submission.author.name)
                    if submission.author is not None
                    else "[deleted]",
                    "score": int(getattr(submission, "score", 0) or 0),
                    "permalink": f"https://reddit.com{submission.permalink}",
                    "created_utc": float(submission.created_utc)
                    if getattr(submission, "created_utc", None) is not None
                    else None,
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
                raw = await asyncio.to_thread(
                    self._fetch_from_praw_sync,
                    args.query,
                    tuple(sorted(args.subreddits)),
                    args.limit,
                )
            except Exception as exc:
                logger.warning("reddit_fetch_failed", key=key, error=str(exc))
                return ToolResult(
                    tool=self.name,
                    ok=False,
                    output=None,
                    error=f"reddit fetch failed: {exc}",
                )

        await put_cached(self._SOURCE, key, raw)
        posts = [RedditPost.model_validate(item) for item in raw[: args.limit]]
        return ToolResult(
            tool=self.name,
            output=posts,
            notes=f"fetched {len(posts)} posts via PRAW, key {key!r}",
        )

    async def execute(self, args: RedditSearchInput) -> ToolResult[list[RedditPost]]:
        if get_tools_mode() == "fixture":
            return self._execute_fixture(args)
        return await self._execute_real(args)
