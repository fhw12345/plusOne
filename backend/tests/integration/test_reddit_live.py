"""Live integration smoke for ``RedditSearchTool`` against real Reddit.

Skipped by default — only runs under ``pytest -m live``. Requires
network connectivity to ``https://www.reddit.com`` (and, in local dev
behind GFW, ``HTTPS_PROXY=http://127.0.0.1:10809``).
"""

from __future__ import annotations

import pytest

from plus_one.core.tools import reddit as reddit_mod
from plus_one.core.tools.reddit import RedditSearchInput, RedditSearchTool


@pytest.mark.live
async def test_live_reddit_search_returns_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PLUS_ONE_TOOLS_MODE", "real")

    # Bypass DB cache for this smoke (no DB in integration env).
    async def _no_cached(source: str, key: str) -> None:
        return None

    async def _noop_put(*args: object, **kwargs: object) -> None:
        return None

    monkeypatch.setattr(reddit_mod, "get_cached", _no_cached)
    monkeypatch.setattr(reddit_mod, "put_cached", _noop_put)

    tool = RedditSearchTool()
    result = await tool.execute(
        RedditSearchInput(
            query="tonkotsu ramen",
            subreddits=("JapanTravel",),
            limit=5,
        )
    )
    assert result.ok
    assert result.output is not None
    assert len(result.output) >= 1
    assert result.output[0].title != ""
