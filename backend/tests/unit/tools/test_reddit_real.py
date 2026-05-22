"""Unit tests for ``RedditSearchTool`` real mode (ADR-007 JSON endpoint).

Strategy: monkeypatch ``_make_client`` to return an ``httpx.AsyncClient``
wired to an ``httpx.MockTransport``, so each test injects whatever
response shape it needs without touching the network. Cache layer
(``get_cached`` / ``put_cached``) is stubbed so we don't need a DB.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from plus_one.core.tools import reddit as reddit_mod
from plus_one.core.tools.reddit import RedditSearchInput, RedditSearchTool


# === fixtures ===========================================================


@pytest.fixture
def real_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLUS_ONE_TOOLS_MODE", "real")
    # ADR-007: no credentials needed. UA optional — leave default.


@pytest.fixture(autouse=True)
def reset_rate_limit_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test starts with a clean module-level rate-limit clock and
    zero minimum interval so unit tests stay fast."""
    reddit_mod._last_call_monotonic[0] = 0.0
    monkeypatch.setattr(reddit_mod, "_MIN_INTERVAL_S", 0.0)


async def _no_cached(source: str, key: str) -> None:
    return None


async def _noop_put(source: str, key: str, payload: list[dict[str, Any]]) -> None:
    return None


def _mock_client(handler: httpx.MockTransport) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=handler, timeout=5.0)


def _install_mock(
    monkeypatch: pytest.MonkeyPatch,
    handler: Any,
) -> None:
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(reddit_mod, "_make_client", lambda: _mock_client(transport))
    monkeypatch.setattr(reddit_mod, "get_cached", _no_cached)
    monkeypatch.setattr(reddit_mod, "put_cached", _noop_put)


def _make_reddit_body(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {"data": {"children": [{"kind": "t3", "data": d} for d in items]}}


# === happy path =========================================================


@pytest.mark.unit
async def test_happy_path_parses_posts(
    monkeypatch: pytest.MonkeyPatch, real_mode: None
) -> None:
    body = _make_reddit_body(
        [
            {
                "id": "p1",
                "subreddit": "JapanTravel",
                "title": "Best tonkotsu in Tokyo",
                "selftext": "go to ichiran",
                "author": "alice",
                "score": 42,
                "permalink": "/r/JapanTravel/comments/p1/x/",
                "created_utc": 1716_000_000,
            },
            {
                "id": "p2",
                "subreddit": "ramen",
                "title": "tonkotsu rec",
                "selftext": "",
                "author": "bob",
                "score": 7,
                "permalink": "/r/ramen/comments/p2/y/",
                "created_utc": 1716_001_000,
            },
            {
                "id": "p3",
                "subreddit": "ramen",
                "title": "another",
                "selftext": "",
                "author": None,
                "score": None,
                "permalink": "/r/ramen/comments/p3/z/",
            },
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "www.reddit.com"
        assert "search.json" in request.url.path
        assert request.url.params["q"] == "tonkotsu ramen"
        return httpx.Response(200, json=body)

    _install_mock(monkeypatch, handler)
    tool = RedditSearchTool()
    result = await tool.execute(RedditSearchInput(query="tonkotsu ramen"))

    assert result.ok
    assert result.output is not None
    assert len(result.output) == 3
    assert result.output[0].id == "p1"
    assert result.output[0].title == "Best tonkotsu in Tokyo"
    assert result.output[0].permalink.startswith("https://reddit.com/r/JapanTravel/")
    # Defensive defaults survive missing author/score.
    assert result.output[2].author == "[deleted]"
    assert result.output[2].score == 0


@pytest.mark.unit
async def test_empty_children_returns_empty(
    monkeypatch: pytest.MonkeyPatch, real_mode: None
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"children": []}})

    _install_mock(monkeypatch, handler)
    tool = RedditSearchTool()
    result = await tool.execute(RedditSearchInput(query="nothing matches"))
    assert result.ok
    assert result.output == []


# === HTTP failures degrade to empty =====================================


@pytest.mark.unit
async def test_http_429_returns_empty_ok(
    monkeypatch: pytest.MonkeyPatch, real_mode: None
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="rate limited")

    _install_mock(monkeypatch, handler)
    tool = RedditSearchTool()
    result = await tool.execute(RedditSearchInput(query="q"))
    assert result.ok
    assert result.output == []
    assert "429" in result.notes


@pytest.mark.unit
async def test_http_503_returns_empty_ok(
    monkeypatch: pytest.MonkeyPatch, real_mode: None
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="unavailable")

    _install_mock(monkeypatch, handler)
    tool = RedditSearchTool()
    result = await tool.execute(RedditSearchInput(query="q"))
    assert result.ok
    assert result.output == []
    assert "503" in result.notes


@pytest.mark.unit
async def test_connect_error_returns_empty_ok(
    monkeypatch: pytest.MonkeyPatch, real_mode: None
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route")

    _install_mock(monkeypatch, handler)
    tool = RedditSearchTool()
    result = await tool.execute(RedditSearchInput(query="q"))
    assert result.ok
    assert result.output == []
    assert "network error" in result.notes


@pytest.mark.unit
async def test_malformed_json_returns_empty_ok(
    monkeypatch: pytest.MonkeyPatch, real_mode: None
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"not json at all <html>",
            headers={"content-type": "text/html"},
        )

    _install_mock(monkeypatch, handler)
    tool = RedditSearchTool()
    result = await tool.execute(RedditSearchInput(query="q"))
    assert result.ok
    assert result.output == []


# === cache short-circuit =================================================


@pytest.mark.unit
async def test_cache_hit_skips_http(
    monkeypatch: pytest.MonkeyPatch, real_mode: None
) -> None:
    cached = [
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
        return cached

    async def fake_put_cached(*args: object, **kwargs: object) -> None:
        raise AssertionError("put_cached must not run on cache hit")

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("HTTP must not run on cache hit")

    monkeypatch.setattr(reddit_mod, "get_cached", fake_get_cached)
    monkeypatch.setattr(reddit_mod, "put_cached", fake_put_cached)
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(reddit_mod, "_make_client", lambda: _mock_client(transport))

    tool = RedditSearchTool()
    result = await tool.execute(RedditSearchInput(query="anything"))
    assert result.ok
    assert result.output is not None
    assert result.output[0].id == "cached1"
    assert "cache hit" in result.notes


# === fixture mode untouched =============================================


@pytest.mark.unit
async def test_fixture_mode_unchanged(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """In fixture mode, execute() must NOT touch HTTP or the DB cache."""
    monkeypatch.delenv("PLUS_ONE_TOOLS_MODE", raising=False)

    async def explode(*args: object, **kwargs: object) -> None:
        raise AssertionError("real-mode helper called in fixture mode")

    monkeypatch.setattr(reddit_mod, "get_cached", explode)
    monkeypatch.setattr(reddit_mod, "put_cached", explode)

    (tmp_path / "reddit").mkdir()
    (tmp_path / "reddit" / "tokyo_ramen.json").write_text(
        json.dumps(
            [
                {
                    "id": "f1",
                    "subreddit": "ramen",
                    "title": "t",
                    "author": "u",
                    "score": 1,
                    "permalink": "https://x",
                }
            ]
        )
    )

    tool = RedditSearchTool(fixtures_dir=tmp_path)
    result = await tool.execute(RedditSearchInput(query="Tokyo ramen"))
    assert result.ok
    assert result.output is not None
    assert result.output[0].id == "f1"


@pytest.mark.unit
def test_subreddit_validator_rejects_path_traversal() -> None:
    """Subreddit values must be [A-Za-z0-9_]{1,50} — no slashes, no query."""
    from pydantic import ValidationError

    for bad in ("../r/all", "all?q=injected", "Japan/Travel", "", "x" * 51):
        with pytest.raises(ValidationError):
            RedditSearchInput(query="ok", subreddits=(bad,))


@pytest.mark.unit
def test_subreddit_validator_accepts_real_names() -> None:
    for good in ("JapanTravel", "ramen", "r_underscores_ok", "Tokyo123"):
        m = RedditSearchInput(query="ok", subreddits=(good,))
        assert m.subreddits == (good,)
