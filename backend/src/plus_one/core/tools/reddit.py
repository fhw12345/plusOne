"""Reddit search tool — fixture-backed for v1.

Returns posts that mention the query terms from a curated cache. Live
PRAW wiring deferred to a follow-up batch (will subclass + override
``_fetch``).
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from plus_one.config import settings
from plus_one.core.agents.framework.tools import ToolResult
from plus_one.core.tools._cache import cache_key, load_json_fixture


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
    """Fixture-backed Reddit search.

    Cache key is built from ``query`` plus the (sorted) subreddit list, so
    a fixture file ``tokyo_ramen_tonkotsu__japantravel__ramen.json``
    services the query "tokyo ramen tonkotsu" restricted to r/JapanTravel
    and r/ramen.
    """

    name: ClassVar[str] = "reddit_search"
    input_schema: ClassVar[type[BaseModel]] = RedditSearchInput
    is_concurrency_safe: ClassVar[bool] = True

    def __init__(self, fixtures_dir: Path | None = None) -> None:
        self._fixtures_dir = (fixtures_dir or settings.fixtures_dir) / "reddit"

    async def execute(self, args: RedditSearchInput) -> ToolResult[list[RedditPost]]:
        key = cache_key(args.query, *sorted(args.subreddits))
        raw = load_json_fixture(self._fixtures_dir, key)
        posts = [RedditPost.model_validate(item) for item in raw[: args.limit]]
        return ToolResult(
            tool=self.name,
            output=posts,
            notes=f"loaded {len(posts)} posts from cache key {key!r}",
        )
