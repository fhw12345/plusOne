"""Unit tests for ``XHSSearchTool`` fallback tiers (PRD Batch 2k §5.5).

Every scenario mocks ``_playwright_session.fetch`` (real Chromium does
not run in tests), ``get_cached`` / ``put_cached``, and the fixture
loader where needed. Fixture-mode tests stay in ``test_tools.py``;
this file is real-mode-only plus a fixture-mode short-circuit guard.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from plus_one.core.tools import _playwright_session
from plus_one.core.tools import xiaohongshu as xhs_mod
from plus_one.core.tools.xiaohongshu import XHSSearchInput, XHSSearchTool


@pytest.fixture
def real_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLUS_ONE_TOOLS_MODE", "real")
    monkeypatch.setenv("XHS_COOKIE", "sess=abc; userid=42")


def _post(pid: str) -> dict[str, Any]:
    return {
        "id": pid,
        "author": "alice",
        "title": f"title {pid}",
        "body": "",
        "likes": 1,
        "comments": 0,
        "url": f"https://www.xiaohongshu.com/explore/{pid}",
        "images": [],
    }


# === init: require_env ====================================================


@pytest.mark.unit
def test_missing_cookie_in_real_mode_does_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLUS_ONE_TOOLS_MODE", "real")
    monkeypatch.delenv("XHS_COOKIE", raising=False)
    XHSSearchTool()


@pytest.mark.unit
def test_init_in_fixture_mode_does_not_require_cookie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PLUS_ONE_TOOLS_MODE", raising=False)
    monkeypatch.delenv("XHS_COOKIE", raising=False)
    # Must not raise.
    XHSSearchTool()


# === Tier 1 success =======================================================


@pytest.mark.unit
async def test_tier1_scrape_success_caches_and_returns(
    monkeypatch: pytest.MonkeyPatch, real_mode: None
) -> None:
    scraped = [_post("s1"), _post("s2")]

    async def fake_fetch(query: str, **kwargs: Any) -> _playwright_session.FetchResult:
        assert query == "tokyo ramen"
        assert kwargs["cookie"] == "sess=abc; userid=42"
        return _playwright_session.FetchResult(posts=scraped)

    written: list[tuple[str, str, list[dict[str, Any]]]] = []

    async def fake_put_cached(source: str, key: str, payload: list[dict[str, Any]]) -> None:
        written.append((source, key, payload))

    async def explode_get(*args: object, **kwargs: object) -> Any:
        raise AssertionError("get_cached must not run on tier 1 success")

    def explode_fixture(*args: object, **kwargs: object) -> list[dict[str, Any]]:
        raise AssertionError("fixture loader must not run on tier 1 success")

    monkeypatch.setattr(_playwright_session, "fetch", fake_fetch)
    monkeypatch.setattr(xhs_mod, "put_cached", fake_put_cached)
    monkeypatch.setattr(xhs_mod, "get_cached", explode_get)
    monkeypatch.setattr(xhs_mod, "load_json_fixture", explode_fixture)

    tool = XHSSearchTool()
    result = await tool.execute(XHSSearchInput(query="tokyo ramen"))

    assert result.ok
    assert result.output is not None
    assert [p.id for p in result.output] == ["s1", "s2"]
    assert len(written) == 1
    assert written[0][0] == "xhs"
    assert written[0][2] == scraped
    assert "playwright" in result.notes


# === Tier 1 fail -> Tier 2 hit ============================================


@pytest.mark.unit
async def test_tier1_fail_tier2_cache_hit(monkeypatch: pytest.MonkeyPatch, real_mode: None) -> None:
    cached_payload = [_post("c1")]

    async def fake_fetch(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("captcha")

    async def fake_get_cached(source: str, key: str) -> list[dict[str, Any]]:
        assert source == "xhs"
        return cached_payload

    async def explode_put(*args: object, **kwargs: object) -> None:
        raise AssertionError("put_cached must not run on tier 2 path")

    def explode_fixture(*args: object, **kwargs: object) -> list[dict[str, Any]]:
        raise AssertionError("fixture loader must not run on tier 2 hit")

    monkeypatch.setattr(_playwright_session, "fetch", fake_fetch)
    monkeypatch.setattr(xhs_mod, "get_cached", fake_get_cached)
    monkeypatch.setattr(xhs_mod, "put_cached", explode_put)
    monkeypatch.setattr(xhs_mod, "load_json_fixture", explode_fixture)

    tool = XHSSearchTool()
    result = await tool.execute(XHSSearchInput(query="tokyo ramen"))

    assert result.ok
    assert result.output is not None
    assert [p.id for p in result.output] == ["c1"]
    assert "cache hit" in result.notes


@pytest.mark.unit
async def test_missing_cookie_public_fail_uses_search_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PLUS_ONE_TOOLS_MODE", "real")
    monkeypatch.delenv("XHS_COOKIE", raising=False)

    async def fake_fetch(*args: Any, **kwargs: Any) -> Any:
        assert kwargs["cookie"] is None
        raise RuntimeError("login wall")

    async def fake_get_cached(source: str, key: str) -> list[dict[str, Any]] | None:
        assert source == "xhs"
        return None

    written: list[tuple[str, str, list[dict[str, Any]]]] = []

    async def fake_put_cached(source: str, key: str, payload: list[dict[str, Any]]) -> None:
        written.append((source, key, payload))

    def explode_fixture(*args: object, **kwargs: object) -> list[dict[str, Any]]:
        raise AssertionError("fixture loader must not run on search-index hit")

    monkeypatch.setattr(_playwright_session, "fetch", fake_fetch)
    monkeypatch.setattr(xhs_mod, "get_cached", fake_get_cached)
    monkeypatch.setattr(xhs_mod, "put_cached", fake_put_cached)
    monkeypatch.setattr(xhs_mod, "load_json_fixture", explode_fixture)

    html = """
    <html><body>
      <a class="result__a" href="/l/?uddg=https%3A%2F%2Fwww.xiaohongshu.com%2Fexplore%2Fabc123%3Fxsec_token%3Dtok%26noisy%3D1">
        东京拉面真实体验
      </a>
    </body></html>
    """
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, text=html, request=request)
    )
    client = httpx.AsyncClient(transport=transport, timeout=5.0)

    tool = XHSSearchTool()
    monkeypatch.setattr(tool, "_get_client", lambda: client)
    result = await tool.execute(XHSSearchInput(query="tokyo ramen"))
    await client.aclose()

    assert result.ok
    assert result.output is not None
    assert [p.id for p in result.output] == ["abc123"]
    assert result.output[0].url == "https://www.xiaohongshu.com/explore/abc123?xsec_token=tok"
    assert "public search index hit" in result.notes
    assert written[0][0] == "xhs"
    assert written[0][1] == "tokyo_ramen"


@pytest.mark.unit
async def test_missing_cookie_uses_public_tier1(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLUS_ONE_TOOLS_MODE", "real")
    monkeypatch.delenv("XHS_COOKIE", raising=False)
    scraped = [_post("public-1")]

    async def fake_fetch(query: str, **kwargs: Any) -> _playwright_session.FetchResult:
        assert query == "tokyo ramen"
        assert kwargs["cookie"] is None
        return _playwright_session.FetchResult(posts=scraped)

    written: list[tuple[str, str, list[dict[str, Any]]]] = []

    async def fake_put_cached(source: str, key: str, payload: list[dict[str, Any]]) -> None:
        written.append((source, key, payload))

    async def explode_get(*args: object, **kwargs: object) -> Any:
        raise AssertionError("get_cached must not run on public tier 1 success")

    monkeypatch.setattr(_playwright_session, "fetch", fake_fetch)
    monkeypatch.setattr(xhs_mod, "get_cached", explode_get)
    monkeypatch.setattr(xhs_mod, "put_cached", fake_put_cached)

    tool = XHSSearchTool()
    result = await tool.execute(XHSSearchInput(query="tokyo ramen"))

    assert result.ok
    assert result.output is not None
    assert [p.id for p in result.output] == ["public-1"]
    assert written == [("xhs", "tokyo_ramen", scraped)]
    assert "public playwright" in result.notes


@pytest.mark.unit
async def test_public_tier1_empty_continues_to_fixture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PLUS_ONE_TOOLS_MODE", "real")
    monkeypatch.delenv("XHS_COOKIE", raising=False)
    fixture_payload = [_post("f-empty")]

    async def fake_fetch(*args: Any, **kwargs: Any) -> _playwright_session.FetchResult:
        assert kwargs["cookie"] is None
        return _playwright_session.FetchResult(posts=[])

    async def fake_get_cached(source: str, key: str) -> list[dict[str, Any]] | None:
        assert source == "xhs"
        return []

    async def fake_search_index(self: object, query: str, limit: int) -> list[dict[str, Any]]:
        del self, query, limit
        return []

    async def explode_put(*args: object, **kwargs: object) -> None:
        raise AssertionError("empty tier 1 must not cache an empty payload")

    def fake_load_fixture(directory: Any, key: str) -> list[dict[str, Any]]:
        return fixture_payload if key == "tokyo_ramen_tonkotsu" else []

    monkeypatch.setattr(_playwright_session, "fetch", fake_fetch)
    monkeypatch.setattr(xhs_mod, "get_cached", fake_get_cached)
    monkeypatch.setattr(xhs_mod, "put_cached", explode_put)
    monkeypatch.setattr(xhs_mod, "load_json_fixture", fake_load_fixture)
    monkeypatch.setattr(XHSSearchTool, "_fetch_from_search_index", fake_search_index)

    tool = XHSSearchTool()
    result = await tool.execute(XHSSearchInput(query="Menya Itto ramen 推荐"))

    assert result.ok
    assert result.output is not None
    assert [p.id for p in result.output] == ["f-empty"]
    assert "degraded to fixture" in result.notes


@pytest.mark.unit
async def test_missing_cookie_public_fail_uses_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLUS_ONE_TOOLS_MODE", "real")
    monkeypatch.delenv("XHS_COOKIE", raising=False)
    cached_payload = [_post("c-no-cookie")]

    async def fake_fetch(*args: Any, **kwargs: Any) -> Any:
        assert kwargs["cookie"] is None
        raise RuntimeError("login wall")

    async def fake_get_cached(source: str, key: str) -> list[dict[str, Any]]:
        assert source == "xhs"
        return cached_payload

    async def explode_put(*args: object, **kwargs: object) -> None:
        raise AssertionError("put_cached must not run on cache hit")

    monkeypatch.setattr(_playwright_session, "fetch", fake_fetch)
    monkeypatch.setattr(xhs_mod, "get_cached", fake_get_cached)
    monkeypatch.setattr(xhs_mod, "put_cached", explode_put)

    tool = XHSSearchTool()
    result = await tool.execute(XHSSearchInput(query="tokyo ramen"))

    assert result.ok
    assert result.output is not None
    assert [p.id for p in result.output] == ["c-no-cookie"]
    assert "cache hit" in result.notes


# === Live/cache/search miss -> fixture ===================================


@pytest.mark.unit
async def test_tier1_2_fail_tier3_fixture(
    monkeypatch: pytest.MonkeyPatch,
    real_mode: None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fixture_payload = [_post("f1")]

    async def fake_fetch(*args: Any, **kwargs: Any) -> Any:
        raise TimeoutError("timed out")

    async def fake_get_cached(source: str, key: str) -> None:
        return None

    async def explode_put(*args: object, **kwargs: object) -> None:
        raise AssertionError("put_cached must not run on fixture fallback")

    async def fake_search_index(self: object, query: str, limit: int) -> list[dict[str, Any]]:
        del self, query, limit
        return []

    def fake_load_fixture(directory: Any, key: str) -> list[dict[str, Any]]:
        return fixture_payload

    monkeypatch.setattr(_playwright_session, "fetch", fake_fetch)
    monkeypatch.setattr(xhs_mod, "get_cached", fake_get_cached)
    monkeypatch.setattr(xhs_mod, "put_cached", explode_put)
    monkeypatch.setattr(xhs_mod, "load_json_fixture", fake_load_fixture)
    monkeypatch.setattr(XHSSearchTool, "_fetch_from_search_index", fake_search_index)

    tool = XHSSearchTool()
    result = await tool.execute(XHSSearchInput(query="tokyo ramen"))

    assert result.ok
    assert result.output is not None
    assert [p.id for p in result.output] == ["f1"]
    assert "degraded to fixture" in result.notes
    # structlog default config writes to stdout, not stdlib logging — so
    # we capture via capsys rather than caplog.
    out = capsys.readouterr().out
    assert "xhs_degraded_to_fixture" in out


# === all 3 fail -> empty ok=True with notes="degraded" ===================


@pytest.mark.unit
async def test_all_three_tiers_fail_returns_empty_degraded(
    monkeypatch: pytest.MonkeyPatch,
    real_mode: None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def fake_fetch(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("network down")

    async def fake_get_cached(source: str, key: str) -> None:
        return None

    def fake_load_fixture(directory: Any, key: str) -> list[dict[str, Any]]:
        return []

    async def fake_search_index(self: object, query: str, limit: int) -> list[dict[str, Any]]:
        del self, query, limit
        return []

    monkeypatch.setattr(_playwright_session, "fetch", fake_fetch)
    monkeypatch.setattr(xhs_mod, "get_cached", fake_get_cached)
    monkeypatch.setattr(xhs_mod, "load_json_fixture", fake_load_fixture)
    monkeypatch.setattr(XHSSearchTool, "_fetch_from_search_index", fake_search_index)

    tool = XHSSearchTool()
    result = await tool.execute(XHSSearchInput(query="obscure query"))

    assert result.ok
    assert result.output == []
    assert result.notes == "degraded"
    out = capsys.readouterr().out
    assert "xhs_total_failure" in out


# === fixture-mode short-circuits before tier 1 ===========================


@pytest.mark.unit
async def test_fixture_mode_short_circuits_tier_1(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """Fixture mode must NOT call Playwright nor the DB cache."""
    monkeypatch.delenv("PLUS_ONE_TOOLS_MODE", raising=False)

    async def explode_fetch(*args: object, **kwargs: object) -> Any:
        raise AssertionError("playwright fetch must not run in fixture mode")

    async def explode_get(*args: object, **kwargs: object) -> Any:
        raise AssertionError("get_cached must not run in fixture mode")

    async def explode_put(*args: object, **kwargs: object) -> None:
        raise AssertionError("put_cached must not run in fixture mode")

    monkeypatch.setattr(_playwright_session, "fetch", explode_fetch)
    monkeypatch.setattr(xhs_mod, "get_cached", explode_get)
    monkeypatch.setattr(xhs_mod, "put_cached", explode_put)

    (tmp_path / "xhs").mkdir()
    (tmp_path / "xhs" / "tokyo_ramen.json").write_text(
        '[{"id":"f1","author":"a","title":"t","url":"https://x"}]'
    )

    tool = XHSSearchTool(fixtures_dir=tmp_path)
    result = await tool.execute(XHSSearchInput(query="Tokyo ramen"))

    assert result.ok
    assert result.output is not None
    assert result.output[0].id == "f1"
