"""Unit tests for ``RedditSearchTool`` in real mode.

Strategy: stub out ``_fetch_from_praw_sync`` (which is the only place
the tool talks to PRAW) and mock the cache layer
(``get_cached`` / ``put_cached``) so we don't need a DB. This proves
the cache-or-fetch branching, rate-limit semaphore, and require_env
behavior without bringing in vcrpy (which would add a heavy dep for
one cassette).
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

from plus_one.core.tools import reddit as reddit_mod
from plus_one.core.tools.reddit import (
    RedditSearchInput,
    RedditSearchTool,
)


@pytest.fixture
def real_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLUS_ONE_TOOLS_MODE", "real")
    monkeypatch.setenv("REDDIT_CLIENT_ID", "cid")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "csecret")
    monkeypatch.setenv("REDDIT_USER_AGENT", "plus-one/test by tester")


@pytest.fixture(autouse=True)
def reset_rate_limit_state() -> None:
    """Each test starts with a clean module-level rate-limit clock."""
    reddit_mod._last_call_monotonic[0] = 0.0


# === require_env at __init__ ============================================


@pytest.mark.unit
def test_missing_creds_in_real_mode_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLUS_ONE_TOOLS_MODE", "real")
    monkeypatch.delenv("REDDIT_CLIENT_ID", raising=False)
    monkeypatch.delenv("REDDIT_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("REDDIT_USER_AGENT", raising=False)
    with pytest.raises(RuntimeError) as exc_info:
        RedditSearchTool()
    msg = str(exc_info.value)
    assert "reddit_search" in msg
    assert "REDDIT_CLIENT_ID" in msg


@pytest.mark.unit
def test_init_in_fixture_mode_does_not_require_creds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PLUS_ONE_TOOLS_MODE", raising=False)
    monkeypatch.delenv("REDDIT_CLIENT_ID", raising=False)
    # Must not raise.
    RedditSearchTool()


# === cache-hit short-circuits PRAW ======================================


@pytest.mark.unit
async def test_cache_hit_skips_praw(monkeypatch: pytest.MonkeyPatch, real_mode: None) -> None:
    cached_payload = [
        {
            "id": "cached1",
            "subreddit": "ramen",
            "title": "cached title",
            "body": "",
            "author": "u",
            "score": 5,
            "permalink": "https://reddit.com/x",
        }
    ]

    async def fake_get_cached(source: str, key: str) -> list[dict[str, Any]]:
        return cached_payload

    async def fake_put_cached(source: str, key: str, payload: list[dict[str, Any]]) -> None:
        raise AssertionError("put_cached must not run on cache hit")

    fetch_called = False

    def fake_fetch(*args: object, **kwargs: object) -> list[dict[str, Any]]:
        nonlocal fetch_called
        fetch_called = True
        return []

    monkeypatch.setattr(reddit_mod, "get_cached", fake_get_cached)
    monkeypatch.setattr(reddit_mod, "put_cached", fake_put_cached)

    tool = RedditSearchTool()
    monkeypatch.setattr(tool, "_fetch_from_praw_sync", fake_fetch)

    result = await tool.execute(RedditSearchInput(query="tokyo ramen"))
    assert result.ok
    assert result.output is not None
    assert len(result.output) == 1
    assert result.output[0].id == "cached1"
    assert fetch_called is False
    assert "cache hit" in result.notes


@pytest.mark.unit
async def test_cache_miss_calls_praw_and_writes_cache(
    monkeypatch: pytest.MonkeyPatch, real_mode: None
) -> None:
    fetched_payload = [
        {
            "id": "fetched1",
            "subreddit": "ramen",
            "title": "fresh title",
            "body": "body",
            "author": "alice",
            "score": 9,
            "permalink": "https://reddit.com/y",
        }
    ]

    async def fake_get_cached(source: str, key: str) -> list[dict[str, Any]] | None:
        return None

    written: list[tuple[str, str, list[dict[str, Any]]]] = []

    async def fake_put_cached(source: str, key: str, payload: list[dict[str, Any]]) -> None:
        written.append((source, key, payload))

    def fake_fetch(query: str, subreddits: tuple[str, ...], limit: int) -> list[dict[str, Any]]:
        assert query == "tokyo ramen"
        assert limit == 25
        return fetched_payload

    monkeypatch.setattr(reddit_mod, "get_cached", fake_get_cached)
    monkeypatch.setattr(reddit_mod, "put_cached", fake_put_cached)

    tool = RedditSearchTool()
    monkeypatch.setattr(tool, "_fetch_from_praw_sync", fake_fetch)

    result = await tool.execute(RedditSearchInput(query="tokyo ramen"))
    assert result.ok
    assert result.output is not None
    assert result.output[0].id == "fetched1"
    assert len(written) == 1
    assert written[0][0] == "reddit"
    assert written[0][2] == fetched_payload


@pytest.mark.unit
async def test_praw_failure_returns_not_ok(
    monkeypatch: pytest.MonkeyPatch, real_mode: None
) -> None:
    async def fake_get_cached(source: str, key: str) -> None:
        return None

    async def fake_put_cached(*args: object, **kwargs: object) -> None:
        raise AssertionError("must not write on failure")

    def fake_fetch(*args: object, **kwargs: object) -> list[dict[str, Any]]:
        raise RuntimeError("boom")

    monkeypatch.setattr(reddit_mod, "get_cached", fake_get_cached)
    monkeypatch.setattr(reddit_mod, "put_cached", fake_put_cached)

    tool = RedditSearchTool()
    monkeypatch.setattr(tool, "_fetch_from_praw_sync", fake_fetch)

    result = await tool.execute(RedditSearchInput(query="anything"))
    assert result.ok is False
    assert result.error is not None
    assert "boom" in result.error


# === fixture mode untouched =============================================


@pytest.mark.unit
async def test_fixture_mode_unchanged(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """In fixture mode, execute() must NOT touch PRAW or the DB cache."""
    monkeypatch.delenv("PLUS_ONE_TOOLS_MODE", raising=False)

    async def explode(*args: object, **kwargs: object) -> None:
        raise AssertionError("real-mode helper called in fixture mode")

    monkeypatch.setattr(reddit_mod, "get_cached", explode)
    monkeypatch.setattr(reddit_mod, "put_cached", explode)

    (tmp_path / "reddit").mkdir()
    (tmp_path / "reddit" / "tokyo_ramen.json").write_text(
        '[{"id":"f1","subreddit":"ramen","title":"t","author":"u","score":1,'
        '"permalink":"https://x"}]'
    )

    tool = RedditSearchTool(fixtures_dir=tmp_path)
    result = await tool.execute(RedditSearchInput(query="Tokyo ramen"))
    assert result.ok
    assert result.output is not None
    assert result.output[0].id == "f1"


# === rate limiting =======================================================


@pytest.mark.unit
async def test_semaphore_bounds_concurrency(
    monkeypatch: pytest.MonkeyPatch, real_mode: None
) -> None:
    """At most 3 PRAW calls should be in-flight concurrently. The 4th must
    block until one of the first three releases the semaphore."""
    # Drop the min-interval to make this test fast — semaphore behavior
    # is what we're asserting, not the 1s gap.
    monkeypatch.setattr(reddit_mod, "_MIN_INTERVAL_S", 0.0)

    in_flight = 0
    peak_in_flight = 0
    enter_event = asyncio.Event()
    release_event = asyncio.Event()

    async def fake_get_cached(*args: object, **kwargs: object) -> None:
        return None

    async def fake_put_cached(*args: object, **kwargs: object) -> None:
        return None

    monkeypatch.setattr(reddit_mod, "get_cached", fake_get_cached)
    monkeypatch.setattr(reddit_mod, "put_cached", fake_put_cached)

    tool = RedditSearchTool()

    def fake_fetch(*args: object, **kwargs: object) -> list[dict[str, Any]]:
        nonlocal in_flight, peak_in_flight
        in_flight += 1
        peak_in_flight = max(peak_in_flight, in_flight)
        enter_event.set()
        # Block until the test releases us.
        while not release_event.is_set():
            time.sleep(0.01)
        in_flight -= 1
        return []

    monkeypatch.setattr(tool, "_fetch_from_praw_sync", fake_fetch)

    # Kick off 5 concurrent calls.
    tasks = [asyncio.create_task(tool.execute(RedditSearchInput(query=f"q{i}"))) for i in range(5)]

    # Wait for the in-flight queue to settle at exactly 3 (semaphore cap).
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        await asyncio.sleep(0.05)
        if peak_in_flight >= 3 and in_flight == 3:
            break
    assert peak_in_flight == 3, (
        f"expected semaphore to cap concurrency at 3, peaked at {peak_in_flight}"
    )

    # 4th and 5th are blocked. Release.
    release_event.set()
    results = await asyncio.gather(*tasks)
    assert all(r.ok for r in results)
    assert peak_in_flight == 3
