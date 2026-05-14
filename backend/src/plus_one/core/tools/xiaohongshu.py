"""Xiaohongshu (RedNote) search tool — fixture-backed for v1.

Per ADR-003, live XHS scraping uses Playwright with a 3-tier fallback.
That work is deferred; this batch ships only the fixture-backed reader
the agents will consume.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from plus_one.config import settings
from plus_one.core.agents.framework.tools import ToolResult
from plus_one.core.tools._cache import cache_key, load_json_fixture


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
    """Fixture-backed XHS search.

    Cache key is the slugified query. Fixture file
    ``fixtures/xhs/<slug>.json`` is a list of XHSPost dicts.
    """

    name: ClassVar[str] = "xhs_search"
    input_schema: ClassVar[type[BaseModel]] = XHSSearchInput
    is_concurrency_safe: ClassVar[bool] = True

    def __init__(self, fixtures_dir: Path | None = None) -> None:
        self._fixtures_dir = (fixtures_dir or settings.fixtures_dir) / "xhs"

    async def execute(self, args: XHSSearchInput) -> ToolResult[list[XHSPost]]:
        key = cache_key(args.query)
        raw = load_json_fixture(self._fixtures_dir, key)
        posts = [XHSPost.model_validate(item) for item in raw[: args.limit]]
        return ToolResult(
            tool=self.name,
            output=posts,
            notes=f"loaded {len(posts)} posts from cache key {key!r}",
        )
