"""Tests for the three fixture-backed tools."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from plus_one.core.agents.framework.tools import Tool
from plus_one.core.tools.google_places import (
    GooglePlacesSearchInput,
    GooglePlacesSearchTool,
    Place,
)
from plus_one.core.tools.reddit import RedditPost, RedditSearchInput, RedditSearchTool
from plus_one.core.tools.xiaohongshu import (
    XHSPost,
    XHSSearchInput,
    XHSSearchTool,
)


def _write(path: Path, payload: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


# === Reddit ==============================================================


@pytest.mark.unit
async def test_reddit_search_returns_cached_posts(tmp_path: Path) -> None:
    _write(
        tmp_path / "reddit" / "tokyo_ramen.json",
        [
            {
                "id": "p1",
                "subreddit": "ramen",
                "title": "title",
                "body": "body",
                "author": "u",
                "score": 1,
                "permalink": "https://x",
            }
        ],
    )
    tool = RedditSearchTool(fixtures_dir=tmp_path)
    result = await tool.execute(RedditSearchInput(query="Tokyo ramen"))
    assert result.ok
    assert result.output is not None
    assert len(result.output) == 1
    assert isinstance(result.output[0], RedditPost)
    assert result.output[0].id == "p1"


@pytest.mark.unit
async def test_reddit_search_subreddits_change_cache_key(tmp_path: Path) -> None:
    """Same query but different subreddit list must hit different files."""
    _write(
        tmp_path / "reddit" / "tokyo_ramen__japantravel__ramen.json",
        [
            {
                "id": "subbed",
                "subreddit": "ramen",
                "title": "x",
                "author": "u",
                "score": 1,
                "permalink": "https://x",
            }
        ],
    )
    tool = RedditSearchTool(fixtures_dir=tmp_path)
    result = await tool.execute(
        RedditSearchInput(query="Tokyo ramen", subreddits=("ramen", "JapanTravel"))
    )
    assert result.output is not None
    assert len(result.output) == 1


@pytest.mark.unit
async def test_reddit_search_missing_fixture_returns_empty(tmp_path: Path) -> None:
    tool = RedditSearchTool(fixtures_dir=tmp_path)
    result = await tool.execute(RedditSearchInput(query="No fixture for this"))
    assert result.ok
    assert result.output == []


@pytest.mark.unit
async def test_reddit_search_respects_limit(tmp_path: Path) -> None:
    _write(
        tmp_path / "reddit" / "many.json",
        [
            {
                "id": f"p{i}",
                "subreddit": "ramen",
                "title": f"t{i}",
                "author": "u",
                "score": 1,
                "permalink": "https://x",
            }
            for i in range(10)
        ],
    )
    tool = RedditSearchTool(fixtures_dir=tmp_path)
    result = await tool.execute(RedditSearchInput(query="many", limit=3))
    assert result.output is not None
    assert len(result.output) == 3


# === XHS =================================================================


@pytest.mark.unit
async def test_xhs_search_returns_cached_posts(tmp_path: Path) -> None:
    _write(
        tmp_path / "xhs" / "tokyo_ramen.json",
        [
            {
                "id": "x1",
                "author": "a",
                "title": "title",
                "body": "body",
                "likes": 100,
                "comments": 10,
                "url": "https://x",
            }
        ],
    )
    tool = XHSSearchTool(fixtures_dir=tmp_path)
    result = await tool.execute(XHSSearchInput(query="Tokyo ramen"))
    assert result.output is not None
    assert isinstance(result.output[0], XHSPost)
    assert result.output[0].author == "a"


# === Google Places =======================================================


@pytest.mark.unit
async def test_google_places_returns_cached_places(tmp_path: Path) -> None:
    _write(
        tmp_path / "google_places" / "ramen__tokyo_japan.json",
        [
            {
                "place_id": "ChIJ_x",
                "name": "Some Ramen",
                "formatted_address": "1-2-3 Somewhere, Tokyo",
                "rating": 4.3,
                "user_ratings_total": 100,
                "price_level": 1,
                "types": ["restaurant"],
            }
        ],
    )
    tool = GooglePlacesSearchTool(fixtures_dir=tmp_path)
    result = await tool.execute(
        GooglePlacesSearchInput(query="ramen", location_hint="Tokyo, Japan")
    )
    assert result.output is not None
    assert isinstance(result.output[0], Place)
    assert result.output[0].rating == 4.3


# === Tool Protocol conformance ==========================================


@pytest.mark.unit
def test_tools_conform_to_framework_protocol() -> None:
    for tool in (
        RedditSearchTool(),
        XHSSearchTool(),
        GooglePlacesSearchTool(),
    ):
        assert isinstance(tool, Tool)  # runtime_checkable Protocol
        assert tool.is_concurrency_safe is True
