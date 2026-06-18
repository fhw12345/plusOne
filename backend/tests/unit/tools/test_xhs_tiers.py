"""Unit tests for ``XHSSearchTool`` fallback tiers (PRD Batch 2k §5.5).

Every scenario mocks ``_playwright_session.fetch`` (real Chromium does
not run in tests), ``get_cached`` / ``put_cached``, and the fixture
loader where needed. Fixture-mode tests stay in ``test_tools.py``;
this file is real-mode-only plus a fixture-mode short-circuit guard.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

import httpx
import pytest

from plus_one.core.tools import _playwright_session
from plus_one.core.tools import xiaohongshu as xhs_mod
from plus_one.core.tools.xiaohongshu import (
    XHSSearchInput,
    XHSSearchTool,
    _enrich_public_index_posts_with_context,
    _image_index_queries,
    _links_from_text,
    _merge_index_posts,
    _normalise_xhs_url,
    _posts_from_sogou_image_index_html,
    _public_index_post_needs_detail_enrichment,
    assess_xhs_authenticity,
    filter_authentic_xhs_posts,
    filter_query_relevant_xhs_posts,
)


@pytest.fixture
def real_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLUS_ONE_TOOLS_MODE", "real")
    monkeypatch.setenv("XHS_COOKIE", "sess=abc; userid=42")
    monkeypatch.delenv("XHS_PROFILE_DIR", raising=False)
    monkeypatch.delenv("XHS_STORAGE_STATE", raising=False)
    monkeypatch.delenv("XHS_USE_CONFIGURED_SESSION", raising=False)


def _post(pid: str) -> dict[str, Any]:
    return {
        "id": pid,
        "author": "alice",
        "title": f"title {pid}",
        "body": "本地朋友带我工作日去, 点了招牌, 人均120, 味道不错但是排队会久。",
        "likes": 1,
        "comments": 0,
        "url": f"https://www.xiaohongshu.com/explore/{pid}",
        "images": [f"https://sns-webpic-qc.xhscdn.com/{pid}!webp"],
    }


# === XHS authenticity scoring ============================================


@pytest.mark.unit
def test_assess_xhs_authenticity_keeps_grounded_local_note() -> None:
    score = assess_xhs_authenticity(
        {
            "author": "普通用户",
            "title": "广州老店早茶真实体验",
            "body": "本地朋友带我工作日去, 点了虾饺和烧卖, 人均90, 但是排队40分钟, 服务一般。",
            "images": ["/media/xhs/a.webp"],
        }
    )

    assert score["score"] >= 0.7
    assert score["is_promotional"] is False
    assert "本地朋友" in score["local_signals"]
    assert "specific_detail" in score["local_signals"]


@pytest.mark.unit
def test_filter_authentic_xhs_posts_drops_group_buy_traffic_note() -> None:
    local = _post("local")
    promo = {
        **_post("promo"),
        "author": "某某餐厅官方",
        "title": "广州新店必打卡, 姐妹们闭眼冲",
        "body": "团购套餐限时福利, 私信我领优惠券, 报暗号还有折扣。",
    }

    kept = filter_authentic_xhs_posts([local, promo])

    assert [post["id"] for post in kept] == ["local"]
    assert kept[0]["authenticity_score"] >= 0.35
    assert kept[0]["is_promotional"] is False


@pytest.mark.unit
def test_filter_query_relevant_xhs_posts_drops_old_search_noise() -> None:
    wrong = {
        **_post("wrong"),
        "title": "上海|饼ok",
        "body": "第一次吃创意菜, 人均1580, 服务态度也不错。",
    }
    right = {
        **_post("right"),
        "title": "阿大葱油饼排队真实体验",
        "body": "本地朋友说阿大葱油饼工作日也会排队。",
    }

    kept = filter_query_relevant_xhs_posts([wrong, right], "上海 阿大葱油饼 美食推荐")

    assert [post["id"] for post in kept] == ["right"]


@pytest.mark.unit
def test_filter_query_relevant_xhs_posts_trusts_quality_checked_cache() -> None:
    post = {**_post("checked"), "title": "旧标题里没有实体", "xhs_quality_version": 4}

    assert filter_query_relevant_xhs_posts([post], "上海 阿大葱油饼 美食推荐") == [post]


@pytest.mark.unit
def test_filter_query_relevant_xhs_posts_drops_stale_quality_checked_cache() -> None:
    post = {**_post("checked"), "title": "旧标题里没有实体", "xhs_quality_version": 3}

    assert filter_query_relevant_xhs_posts([post], "上海 阿大葱油饼 美食推荐") == []


@pytest.mark.unit
def test_filter_query_relevant_xhs_posts_normalises_traditional_chinese() -> None:
    post = {**_post("baohua"), "title": "廣州寶華麵家雲吞面", "body": "街坊排队, 汤很香。"}

    kept = filter_query_relevant_xhs_posts([post], "广州 宝华面家 美食推荐")

    assert [item["id"] for item in kept] == ["baohua"]


@pytest.mark.unit
def test_filter_query_relevant_xhs_posts_drops_unenriched_index_stub() -> None:
    post = {
        **_post("idx"),
        "title": "小红书",
        "body": "",
        "images": [],
        "xhs_index_query": "广州 宝华园 美食推荐",
        "xhs_index_stub": True,
    }

    assert filter_query_relevant_xhs_posts([post], "广州 宝华园 美食推荐") == []


@pytest.mark.unit
def test_xhs_gate_text_detects_too_frequent_security_page() -> None:
    with pytest.raises(RuntimeError, match="verification required"):
        _playwright_session._raise_for_gate_text("请求太频繁, 请稍后再试")


@pytest.mark.unit
def test_xhs_gate_url_detects_captcha_redirect() -> None:
    with pytest.raises(RuntimeError, match="verification required"):
        _playwright_session._raise_for_gate_url(
            "https://www.xiaohongshu.com/website-login/captcha?redirectPath=https%3A%2F%2Fexample.com"
        )


# === cookie parsing =======================================================


@pytest.mark.unit
def test_parse_cookie_blob_accepts_raw_header() -> None:
    assert _playwright_session._parse_cookie_blob("Cookie: a=b; c=d") == [
        {"name": "a", "value": "b", "domain": ".xiaohongshu.com", "path": "/"},
        {"name": "c", "value": "d", "domain": ".xiaohongshu.com", "path": "/"},
    ]


@pytest.mark.unit
def test_parse_cookie_blob_accepts_json_list() -> None:
    cookies = _playwright_session._parse_cookie_blob(
        '[{"name":"web_session","value":"abc","domain":".xiaohongshu.com"}]'
    )

    assert cookies == [
        {"name": "web_session", "value": "abc", "domain": ".xiaohongshu.com", "path": "/"}
    ]


@pytest.mark.unit
def test_parse_cookie_blob_accepts_single_json_cookie() -> None:
    cookies = _playwright_session._parse_cookie_blob('{"name":"a","value":"1"}')

    assert cookies == [{"name": "a", "value": "1", "domain": ".xiaohongshu.com", "path": "/"}]


@pytest.mark.unit
def test_parse_cookie_blob_accepts_cookies_object_and_filters_bad_items() -> None:
    cookies = _playwright_session._parse_cookie_blob(
        '{"cookies":[{"name":"a","value":"1"},{"value":"missing-name"},"bad"]}'
    )

    assert cookies == [{"name": "a", "value": "1", "domain": ".xiaohongshu.com", "path": "/"}]


@pytest.mark.unit
def test_parse_cookie_blob_malformed_json_returns_empty() -> None:
    assert _playwright_session._parse_cookie_blob("{") == []


@pytest.mark.unit
def test_mobile_context_kwargs() -> None:
    kwargs = _playwright_session._context_kwargs(
        user_agent="ua",
        storage_state_path="state.json",
        device_profile="mobile",
    )

    assert kwargs["user_agent"] == "ua"
    assert kwargs["storage_state"] == "state.json"
    assert kwargs["is_mobile"] is True
    assert kwargs["has_touch"] is True
    assert kwargs["viewport"] == {"width": 390, "height": 844}


@pytest.mark.unit
def test_desktop_context_kwargs() -> None:
    kwargs = _playwright_session._context_kwargs(
        user_agent="ua",
        storage_state_path=None,
        device_profile="desktop",
    )

    assert kwargs["user_agent"] == "ua"
    assert "storage_state" not in kwargs
    assert "is_mobile" not in kwargs


@pytest.mark.unit
def test_headed_context_kwargs_start_minimized(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XHS_HEADLESS", "0")

    kwargs = _playwright_session._browser_launch_kwargs()

    assert kwargs["headless"] is False
    assert "--start-minimized" in kwargs["args"]


@pytest.mark.unit
def test_headless_context_kwargs_do_not_start_minimized(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("XHS_HEADLESS", raising=False)

    kwargs = _playwright_session._browser_launch_kwargs()

    assert kwargs["headless"] is True
    assert "args" not in kwargs


@pytest.mark.unit
def test_browser_launch_kwargs_can_use_configured_channel(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XHS_BROWSER_CHANNEL", "chrome")

    kwargs = _playwright_session._browser_launch_kwargs(headless=True)

    assert kwargs["channel"] == "chrome"


@pytest.mark.unit
def test_random_delay_seconds_uses_configured_range(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_playwright_session.secrets, "randbelow", lambda bucket: bucket // 2)

    delay = _playwright_session._random_delay_seconds(4.0, 10.0)

    assert delay == 7.0


@pytest.mark.unit
def test_persistent_profile_uses_home_search_entry_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("XHS_SEARCH_ENTRY", raising=False)

    assert _playwright_session._use_home_search_entry(".auth/xhs-profile") is True
    assert _playwright_session._use_home_search_entry(None) is False


@pytest.mark.unit
def test_search_entry_can_force_direct_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XHS_SEARCH_ENTRY", "direct")

    assert _playwright_session._use_home_search_entry(".auth/xhs-profile") is False


@pytest.mark.unit
async def test_search_result_ai_counts_as_search_landing() -> None:
    class FakePage:
        url = "https://www.xiaohongshu.com/search_result_ai?keyword=test"

        async def evaluate(self, script: str) -> str:
            del script
            return ""

        async def wait_for_load_state(self, *args: object, **kwargs: object) -> None:
            raise AssertionError("search_result_ai should return without waiting")

    await _playwright_session._wait_for_search_landing(FakePage(), timeout_s=1)


@pytest.mark.unit
async def test_open_scrape_context_uses_persistent_profile(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[dict[str, str]] = []
    profile_dir = tmp_path / "xhs-profile"

    class FakeBrowserType:
        async def launch_persistent_context(self, profile_path: Path, **kwargs: Any) -> str:
            calls.append(
                {
                    "profile_dir": Path(profile_path).as_posix(),
                    "user_agent": kwargs["user_agent"],
                }
            )
            return "persistent-context"

    class FakePlaywright:
        chromium = FakeBrowserType()

    _playwright_session._pw_ctx_slot[0] = FakePlaywright()
    _playwright_session._persistent_context_slot[0] = None
    _playwright_session._persistent_profile_dir_slot[0] = None

    try:
        context, close_context = await _playwright_session._open_scrape_context(
            user_agent="ua",
            storage_state_path="state.json",
            profile_dir=str(profile_dir),
            device_profile="mobile",
        )
    finally:
        _playwright_session._persistent_context_slot[0] = None
        _playwright_session._persistent_profile_dir_slot[0] = None
        _playwright_session._pw_ctx_slot[0] = None

    assert context == "persistent-context"
    assert close_context is False
    assert calls == [{"profile_dir": profile_dir.as_posix(), "user_agent": "ua"}]


@pytest.mark.unit
def test_merge_detail_keeps_original_url_on_xhs_security_redirect() -> None:
    post = _post("abc")
    merged = _playwright_session._merge_detail(
        post,
        {
            "title": "security page",
            "body": "redirect",
            "url": "https://www.xiaohongshu.com/404?source=/404/sec_token",
        },
    )

    assert merged == post


@pytest.mark.unit
def test_merge_detail_keeps_original_on_home_redirect() -> None:
    post = _post("abc")
    post["url"] = "https://www.xiaohongshu.com/explore/abc"

    merged = _playwright_session._merge_detail(
        post,
        {
            "title": "马上登录即可",
            "body": "刷到更懂你的优质内容",
            "url": "https://www.xiaohongshu.com/explore",
            "images": ["https://sns-webpic-qc.xhscdn.com/homepage!webp"],
        },
    )

    assert merged == post


@pytest.mark.unit
def test_merge_detail_keeps_original_on_note_id_mismatch() -> None:
    post = _post("abc")
    post["url"] = "https://www.xiaohongshu.com/explore/abc"

    merged = _playwright_session._merge_detail(
        post,
        {
            "title": "another note",
            "body": "not the requested note",
            "url": "https://www.xiaohongshu.com/explore/def",
            "images": ["https://sns-webpic-qc.xhscdn.com/def!webp"],
        },
    )

    assert merged == post


@pytest.mark.unit
def test_merge_detail_accepts_tokenized_search_result_url_and_content_images() -> None:
    post = _post("abc")
    post["url"] = "https://www.xiaohongshu.com/search_result/abc?xsec_token=tok"
    post["images"] = ["https://sns-webpic-qc.xhscdn.com/card-cover!webp"]
    post["xhs_index_stub"] = True

    merged = _playwright_session._merge_detail(
        post,
        {
            "title": "detail title",
            "body": "real note body",
            "url": "https://www.xiaohongshu.com/explore/abc?xsec_token=tok",
            "images": [
                "https://www.xiaohongshu.com/explore/abc",
                "https://sns-avatar-qc.xhscdn.com/avatar.jpg",
                "https://sns-webpic-qc.xhscdn.com/detail-1!webp",
            ],
        },
    )

    assert merged["url"] == "https://www.xiaohongshu.com/explore/abc?xsec_token=tok"
    assert merged["body"] == "real note body"
    assert "xhs_index_stub" not in merged
    assert merged["images"] == [
        "https://sns-webpic-qc.xhscdn.com/detail-1!webp",
        "https://sns-webpic-qc.xhscdn.com/card-cover!webp",
    ]


@pytest.mark.unit
async def test_enrich_posts_from_details_retries_navigation_interrupted_evaluate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def noop(*args: object, **kwargs: object) -> None:
        del args, kwargs

    monkeypatch.setattr(_playwright_session, "_detail_page_dwell", noop)
    monkeypatch.setattr(_playwright_session, "_human_mouse_pause", noop)
    monkeypatch.setattr(_playwright_session, "_human_scroll_page", noop)
    monkeypatch.setattr(_playwright_session, "_wait_for_lazy_content_images", noop)

    class FakeResponse:
        status = 200

    class FakePage:
        url = "https://www.xiaohongshu.com/explore/abc?xsec_token=tok"

        def __init__(self) -> None:
            self.evaluate_calls = 0
            self.closed = False

        def set_default_timeout(self, timeout: int) -> None:
            del timeout

        def set_default_navigation_timeout(self, timeout: int) -> None:
            del timeout

        async def goto(self, *args: object, **kwargs: object) -> FakeResponse:
            del args, kwargs
            return FakeResponse()

        async def wait_for_function(self, *args: object, **kwargs: object) -> None:
            del args, kwargs

        async def wait_for_load_state(self, *args: object, **kwargs: object) -> None:
            del args, kwargs

        async def wait_for_timeout(self, *args: object, **kwargs: object) -> None:
            del args, kwargs

        async def evaluate(self, script: str) -> dict[str, object]:
            del script
            self.evaluate_calls += 1
            if self.evaluate_calls == 1:
                raise RuntimeError(
                    "Execution context was destroyed, most likely because of a navigation"
                )
            return {
                "author": "alice",
                "title": "detail title",
                "body": "real detail body",
                "url": self.url,
                "images": ["https://sns-webpic-qc.xhscdn.com/detail!webp"],
            }

        async def close(self) -> None:
            self.closed = True

    fake_page = FakePage()

    class FakeContext:
        async def new_page(self) -> FakePage:
            return fake_page

    posts = [
        {
            "id": "abc",
            "author": "public index",
            "title": "stub",
            "body": "",
            "url": "https://www.xiaohongshu.com/explore/abc?xsec_token=tok",
            "images": [],
            "xhs_index_stub": True,
        }
    ]

    enriched = await _playwright_session._enrich_posts_from_details(
        FakeContext(), posts, timeout_s=2
    )

    assert fake_page.evaluate_calls == 2
    assert fake_page.closed is True
    assert enriched[0]["body"] == "real detail body"
    assert enriched[0]["images"] == ["https://sns-webpic-qc.xhscdn.com/detail!webp"]
    assert "xhs_index_stub" not in enriched[0]


@pytest.mark.unit
def test_likely_xhs_content_image_filters_non_content_urls() -> None:
    assert _playwright_session._is_likely_xhs_content_image(
        "https://sns-webpic-qc.xhscdn.com/photo!webp"
    )
    assert _playwright_session._is_likely_xhs_content_image(
        "http://o4.xiaohongshu.com/discovery/w1280/photo.jpg"
    )
    assert not _playwright_session._is_likely_xhs_content_image(
        "https://fe-platform.xhscdn.com/platform/104101l0320so64n6nk062u7au7rdm9g007pkcqvqmd668?imageView2/2/format/webp"
    )
    assert not _playwright_session._is_likely_xhs_content_image(
        "https://www.xiaohongshu.com/explore/abc"
    )
    assert not _playwright_session._is_likely_xhs_content_image(
        "https://sns-avatar-qc.xhscdn.com/avatar.jpg"
    )


@pytest.mark.unit
async def test_cache_post_images_with_context_rewrites_images_to_local_media(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(_playwright_session.settings, "media_dir", tmp_path)

    class FakeResponse:
        ok = True
        headers: ClassVar[dict[str, str]] = {"content-type": "image/webp", "content-length": "9"}

        async def body(self) -> bytes:
            return b"fake-webp"

    class FakeRequest:
        async def get(self, *args: object, **kwargs: object) -> FakeResponse:
            del args, kwargs
            return FakeResponse()

    class FakeContext:
        request = FakeRequest()

    posts = [
        {
            "id": "abc",
            "images": (
                "https://sns-webpic-qc.xhscdn.com/photo!webp",
                "https://sns-avatar-qc.xhscdn.com/avatar.jpg",
            ),
        }
    ]

    cached = await _playwright_session._cache_post_images_with_context(
        FakeContext(),
        posts,
        images_per_post=3,
        timeout_s=2,
    )

    assert cached[0]["source_images"] == ["https://sns-webpic-qc.xhscdn.com/photo!webp"]
    assert cached[0]["images"][0].startswith("/media/xhs/")
    assert (
        cached[0]["cached_images"][0]["source_url"] == "https://sns-webpic-qc.xhscdn.com/photo!webp"
    )
    assert (tmp_path / "xhs").exists()


@pytest.mark.unit
def test_canonicalise_xhs_note_url_keeps_xsec_token() -> None:
    assert (
        _playwright_session._canonicalise_xhs_note_url(
            "https://www.xiaohongshu.com/search_result/abc?xsec_token=tok&xsec_source="
        )
        == "https://www.xiaohongshu.com/explore/abc?xsec_token=tok&xsec_source="
    )


@pytest.mark.unit
def test_normalise_xhs_url_accepts_bing_redirect_u_param() -> None:
    raw = (
        "https://www.bing.com/ck/a?!&&p=abc&u="
        "https%3A%2F%2Fwww.xiaohongshu.com%2Fexplore%2Fabc123%3Fxsec_token%3Dtok%26noisy%3D1"
        "&ntb=1"
    )

    assert _normalise_xhs_url(raw) == "https://www.xiaohongshu.com/explore/abc123?xsec_token=tok"


@pytest.mark.unit
def test_normalise_xhs_url_accepts_discovery_item_sgh_path() -> None:
    raw = "https://www.xiaohongshu.com/discovery/item/sgh/62ff2b6b000000001b01a507?foo=bar"

    assert _normalise_xhs_url(raw) == "https://www.xiaohongshu.com/explore/62ff2b6b000000001b01a507"


@pytest.mark.unit
def test_links_from_text_preserves_xsec_token() -> None:
    html = _links_from_text(
        "see https://www.xiaohongshu.com/explore/abc123?xsec_token=tok&xsec_source=pc_search"
    )

    assert "xsec_token=tok" in html
    assert "xsec_source=pc_search" in html


@pytest.mark.unit
def test_links_from_text_accepts_search_result_urls_with_token() -> None:
    html = _links_from_text(
        "see https://www.xiaohongshu.com/search_result/abc123?xsec_token=tok&xsec_source=pc_search"
    )

    assert "https://www.xiaohongshu.com/explore/abc123" in html
    assert "xsec_token=tok" in html
    assert "xsec_source=pc_search" in html


@pytest.mark.unit
def test_links_from_text_accepts_plain_sogou_discovery_item_sgh_urls() -> None:
    html = _links_from_text(
        "https://www.xiaohongshu.com/discovery/item/sgh/62ff2b6b000000001b01a507?foo=bar"
    )

    assert "https://www.xiaohongshu.com/explore/62ff2b6b000000001b01a507" in html
    assert "https://www.xiaohongshu.com/explore/sgh" not in html


@pytest.mark.unit
async def test_search_index_parser_accepts_bing_redirect_links() -> None:
    href = (
        "https://www.bing.com/ck/a?!&&p=abc&u="
        "https%3A%2F%2Fwww.xiaohongshu.com%2Fexplore%2Fabc123%3Fxsec_token%3Dtok"
        "&ntb=1"
    )
    html = f'<html><body><a href="{href}">东京拉面真实体验</a></body></html>'
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text=html, request=request))
    client = httpx.AsyncClient(transport=transport, timeout=5.0)
    tool = XHSSearchTool()
    tool._client = client

    try:
        posts = await tool._fetch_from_search_index("tokyo ramen", 3)
    finally:
        await client.aclose()

    assert posts[0]["id"] == "abc123"
    assert posts[0]["url"] == "https://www.xiaohongshu.com/explore/abc123?xsec_token=tok"
    assert posts[0]["xhs_index_stub"] is True


@pytest.mark.unit
async def test_search_index_parser_accepts_sogou_discovery_item_links() -> None:
    html = (
        '<html><body><a href="https://www.xiaohongshu.com/discovery/item/sgh/62ff2b6b000000001b01a507">'
        "广州永记牛杂真实体验</a></body></html>"
    )
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text=html, request=request))
    client = httpx.AsyncClient(transport=transport, timeout=5.0)
    tool = XHSSearchTool()
    tool._client = client

    try:
        posts = await tool._fetch_from_search_index("广州 永记牛杂 美食推荐", 3)
    finally:
        await client.aclose()

    assert posts[0]["id"] == "62ff2b6b000000001b01a507"
    assert posts[0]["url"] == "https://www.xiaohongshu.com/explore/62ff2b6b000000001b01a507"
    assert posts[0]["xhs_index_stub"] is True


@pytest.mark.unit
async def test_search_index_prefers_sogou_image_result_over_plain_stub() -> None:
    web_html = '<a href="https://www.xiaohongshu.com/explore/plain123">plain123</a>'
    image_html = r"""
    <script>{"searchList":[
      {"ch_site_name":"小红书","title":"京都和束 d matcha 茶园游","content_major":"和束茶园真实体验",
       "page_url":"https:\/\/www.xiaohongshu.com\/explore\/image123",
       "pic_url":"http:\/\/o4.xiaohongshu.com\/discovery\/w1280\/photo.jpg"}
    ]}</script>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        text = image_html if "pic.sogou.com" in str(request.url) else web_html
        return httpx.Response(200, text=text, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=5.0)
    tool = XHSSearchTool()
    tool._client = client

    try:
        posts = await tool._fetch_from_search_index("京都 d matcha 和束 小红书", 3)
    finally:
        await client.aclose()

    assert posts[0]["id"] == "image123"
    assert posts[0]["images"] == ["http://o4.xiaohongshu.com/discovery/w1280/photo.jpg"]


@pytest.mark.unit
def test_posts_from_sogou_image_index_html_extracts_xhs_image_results() -> None:
    html = r"""
    <script>window.__INITIAL_STATE__={"query":"京都 d matcha 和束 小红书","searchList":[
      {"ch_site_name":"小红书","title":"京都和束 d matcha 茶园游","content_major":"和束茶园真实体验",
       "page_url":"https:\/\/www.xiaohongshu.com\/explore\/abc123",
       "pic_url":"http:\/\/o4.xiaohongshu.com\/discovery\/w1280\/photo.jpg"},
      {"ch_site_name":"搜狐网","title":"无关","pic_url":"https:\/\/example.com\/x.jpg"}
    ]};</script>
    """

    posts = _posts_from_sogou_image_index_html(html, "京都 d matcha 和束 小红书", 3)

    assert posts == [
        {
            "id": "abc123",
            "author": "public image index",
            "title": "京都和束 d matcha 茶园游",
            "body": "和束茶园真实体验",
            "likes": 0,
            "comments": 0,
            "url": "https://www.xiaohongshu.com/explore/abc123",
            "images": ["http://o4.xiaohongshu.com/discovery/w1280/photo.jpg"],
            "xhs_index_query": "京都 d matcha 和束 小红书",
            "xhs_image_index_stub": True,
        }
    ]


@pytest.mark.unit
def test_image_index_queries_try_xhs_prefixed_and_intentless_variants() -> None:
    assert _image_index_queries("广州 永记牛杂 美食推荐") == (
        "广州 永记牛杂 美食推荐",
        "小红书 广州 永记牛杂 美食推荐",
        "广州 永记牛杂",
        "小红书 广州 永记牛杂",
    )


@pytest.mark.unit
async def test_search_index_tries_prefixed_image_query_after_empty_image_result() -> None:
    image_html = r"""
    <script>{"searchList":[
      {"ch_site_name":"小红书","title":"广州永记牛杂真实体验","content_major":"老店牛杂本地人推荐",
       "page_url":"https:\/\/www.xiaohongshu.com\/explore\/beef123",
       "pic_url":"http:\/\/o4.xiaohongshu.com\/discovery\/w1280\/beef.jpg"}
    ]}</script>
    """
    requested_queries: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if "pic.sogou.com" in str(request.url):
            query = str(request.url.params.get("query") or "")
            requested_queries.append(query)
            text = image_html if query == "小红书 广州 永记牛杂 美食推荐" else "<html></html>"
            return httpx.Response(200, text=text, request=request)
        return httpx.Response(200, text="<html></html>", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=5.0)
    tool = XHSSearchTool()
    tool._client = client

    try:
        posts = await tool._fetch_from_search_index("广州 永记牛杂 美食推荐", 3)
    finally:
        await client.aclose()

    assert requested_queries[:2] == ["广州 永记牛杂 美食推荐", "小红书 广州 永记牛杂 美食推荐"]
    assert posts[0]["id"] == "beef123"
    assert posts[0]["images"] == ["http://o4.xiaohongshu.com/discovery/w1280/beef.jpg"]


@pytest.mark.unit
def test_posts_from_sogou_image_index_html_accepts_url_field_for_xhs_results() -> None:
    html = r"""
    <script>window.__INITIAL_STATE__={"searchList":[
      {"ch_site_name":"","title":"京都和束 d matcha 茶园游","content_major":"和束茶园真实体验",
       "url":"https:\/\/www.xiaohongshu.com\/search_result\/abc123?xsec_token=tok",
       "picUrl":"http:\/\/o4.xiaohongshu.com\/discovery\/w1280\/photo.jpg"}
    ]};</script>
    """

    posts = _posts_from_sogou_image_index_html(html, "京都 d matcha 和束 小红书", 3)

    assert posts[0]["id"] == "abc123"
    assert posts[0]["url"] == "https://www.xiaohongshu.com/explore/abc123?xsec_token=tok"
    assert posts[0]["images"] == ["http://o4.xiaohongshu.com/discovery/w1280/photo.jpg"]


@pytest.mark.unit
def test_posts_from_sogou_image_index_html_accepts_legacy_discovery_item_urls() -> None:
    html = r"""
    <script>window.__INITIAL_STATE__={"searchList":[
      {"ch_site_name":"小红书","title":"箱根丸山物产 小红书笔记","content_major":"大涌谷茶屋真实体验",
       "url":"http:\/\/www.xiaohongshu.com\/discovery\/item\/5678248233f60c3235ce8ca2",
       "picUrl":"http:\/\/o4.xiaohongshu.com\/discovery\/w640\/photo.jpg",
       "oriPicUrl":"http:\/\/o4.xiaohongshu.com\/discovery\/w640\/photo.jpg"}
    ]};</script>
    """

    posts = _posts_from_sogou_image_index_html(html, "箱根 丸山物产 小红书", 3)

    assert posts[0]["id"] == "5678248233f60c3235ce8ca2"
    assert posts[0]["url"] == "https://www.xiaohongshu.com/explore/5678248233f60c3235ce8ca2"
    assert posts[0]["images"] == ["http://o4.xiaohongshu.com/discovery/w640/photo.jpg"]


@pytest.mark.unit
def test_merge_index_posts_dedupes_by_note_id_and_keeps_image_result() -> None:
    image_post = {
        "id": "abc123",
        "url": "https://www.xiaohongshu.com/explore/abc123?xsec_token=tok",
        "title": "带图结果",
        "images": ["http://o4.xiaohongshu.com/discovery/w1280/photo.jpg"],
    }
    plain_stub = {
        "id": "abc123",
        "url": "https://www.xiaohongshu.com/explore/abc123",
        "title": "abc123",
        "images": [],
    }

    merged = _merge_index_posts([image_post], [plain_stub], 3)

    assert merged == [image_post]


@pytest.mark.unit
async def test_enrich_indexed_posts_caches_detail_images(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {}

    async def fake_enrich_details(
        context: object, posts: list[dict[str, object]], timeout_s: float
    ) -> list[dict[str, object]]:
        assert context is fake_context
        assert timeout_s > 0
        enriched = [dict(posts[0])]
        enriched[0].update(
            {
                "title": "Dilli Haat INA eating notes",
                "body": "local friend visit",
                "images": ["https://sns-webpic-qc.xhscdn.com/detail!webp"],
            }
        )
        enriched[0].pop("xhs_index_stub", None)
        return enriched

    async def fake_cache_images(
        context: object, posts: list[dict[str, object]], **kwargs: object
    ) -> list[dict[str, object]]:
        assert context is fake_context
        calls["cache"] = kwargs
        cached = [dict(posts[0])]
        cached[0]["source_images"] = ["https://sns-webpic-qc.xhscdn.com/detail!webp"]
        cached[0]["images"] = ["/media/xhs/aa/detail.webp"]
        return cached

    class FakeContext:
        async def close(self) -> None:
            calls["closed"] = True

    fake_context = FakeContext()

    async def fake_open_with_close(**kwargs: object) -> tuple[FakeContext, bool]:
        calls["open"] = kwargs
        return fake_context, True

    monkeypatch.setattr(_playwright_session, "_open_scrape_context", fake_open_with_close)
    monkeypatch.setattr(_playwright_session, "_enrich_posts_from_details", fake_enrich_details)
    monkeypatch.setattr(_playwright_session, "_cache_post_images_with_context", fake_cache_images)
    monkeypatch.delenv("XHS_USE_CONFIGURED_SESSION", raising=False)

    tool = XHSSearchTool()
    result = await tool._enrich_indexed_posts(
        [
            {
                "id": "idx1",
                "title": "Dilli Haat",
                "url": "https://www.xiaohongshu.com/explore/idx1?xsec_token=tok",
                "images": [],
                "xhs_index_stub": True,
            }
        ],
        1,
    )

    assert result[0]["images"] == ["/media/xhs/aa/detail.webp"]
    assert result[0]["source_images"] == ["https://sns-webpic-qc.xhscdn.com/detail!webp"]
    assert calls["closed"] is True


@pytest.mark.unit
async def test_public_image_index_caches_index_image_without_detail_enrich(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, object] = {}
    image_url = "http://o4.xiaohongshu.com/discovery/w1280/photo.jpg"

    async def fake_cache_images(
        context: object, posts: list[dict[str, object]], **kwargs: object
    ) -> list[dict[str, object]]:
        assert context is fake_context
        calls["cache"] = kwargs
        cached = [dict(posts[0])]
        cached[0]["source_images"] = [image_url]
        cached[0]["images"] = ["/media/xhs/aa/photo.webp"]
        return cached

    async def fail_detail_enrich(*args: object, **kwargs: object) -> list[dict[str, object]]:
        del args, kwargs
        raise AssertionError("image index result should not require detail enrichment")

    class FakeContext:
        pass

    fake_context = FakeContext()
    monkeypatch.setattr(_playwright_session, "_cache_post_images_with_context", fake_cache_images)
    monkeypatch.setattr(_playwright_session, "_enrich_posts_from_details", fail_detail_enrich)

    result = await _enrich_public_index_posts_with_context(
        fake_context,
        [
            {
                "id": "abc123",
                "author": "public image index",
                "title": "京都和束 d matcha 茶园真实体验",
                "body": "和束茶园本地人推荐路线",
                "url": "https://www.xiaohongshu.com/explore/abc123",
                "images": [image_url],
                "xhs_image_index_stub": True,
            }
        ],
        timeout_s=12,
        images_per_post=2,
    )

    assert result[0]["images"] == ["/media/xhs/aa/photo.webp"]
    assert result[0]["source_images"] == [image_url]
    assert calls["cache"] == {"images_per_post": 2, "timeout_s": 8.0}


@pytest.mark.unit
def test_bare_public_search_index_stub_skips_detail_enrichment() -> None:
    assert not _public_index_post_needs_detail_enrichment(
        {
            "id": "idx-stub",
            "author": "public search index",
            "title": "小红书",
            "body": "",
            "url": "https://www.xiaohongshu.com/explore/idx-stub",
            "images": [],
            "xhs_index_stub": True,
        }
    )


@pytest.mark.unit
def test_meaningful_public_search_index_stub_still_allows_detail_enrichment() -> None:
    assert _public_index_post_needs_detail_enrichment(
        {
            "id": "idx-note",
            "author": "public search index",
            "title": "广州永记牛杂真实体验",
            "body": "",
            "url": "https://www.xiaohongshu.com/explore/idx-note",
            "images": [],
            "xhs_index_stub": True,
        }
    )


@pytest.mark.unit
async def test_enrich_indexed_posts_stays_public_when_configured_session_is_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, object] = {}

    class FakeContext:
        async def close(self) -> None:
            calls["closed"] = True

    fake_context = FakeContext()

    async def fake_open_with_close(**kwargs: object) -> tuple[FakeContext, bool]:
        calls["open"] = kwargs
        return fake_context, True

    async def fake_enrich_details(
        context: object,
        posts: list[dict[str, object]],
        timeout_s: float,
    ) -> list[dict[str, object]]:
        del timeout_s
        assert context is fake_context
        return posts

    async def fake_cache_images(
        context: object,
        posts: list[dict[str, object]],
        **kwargs: object,
    ) -> list[dict[str, object]]:
        del kwargs
        assert context is fake_context
        return posts

    monkeypatch.setenv("XHS_USE_CONFIGURED_SESSION", "1")
    monkeypatch.setenv("XHS_PROFILE_DIR", ".auth/xhs-profile")
    monkeypatch.setenv("XHS_STORAGE_STATE", "state.json")
    monkeypatch.setenv("XHS_COOKIE", "sess=abc")
    monkeypatch.setattr(_playwright_session, "_open_scrape_context", fake_open_with_close)
    monkeypatch.setattr(_playwright_session, "_enrich_posts_from_details", fake_enrich_details)
    monkeypatch.setattr(_playwright_session, "_cache_post_images_with_context", fake_cache_images)

    tool = XHSSearchTool()
    await tool._enrich_indexed_posts(
        [
            {
                "id": "idx1",
                "title": "Dilli Haat",
                "url": "https://www.xiaohongshu.com/explore/idx1?xsec_token=tok",
                "images": [],
                "xhs_index_stub": True,
            }
        ],
        1,
    )

    open_kwargs = calls["open"]
    assert open_kwargs["profile_dir"] is None
    assert open_kwargs["storage_state_path"] is None


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
async def test_real_mode_prefers_prewarmed_cache_before_live_scrape(
    monkeypatch: pytest.MonkeyPatch,
    real_mode: None,
) -> None:
    cached_payload = [_post("prewarm")]
    cached_payload[0]["images"] = ["/media/xhs/aa/photo.webp"]

    async def fake_get_cached(source: str, key: str) -> list[dict[str, Any]]:
        assert source == "xhs"
        assert key == "tokyo_ramen"
        return cached_payload

    async def explode_fetch(*args: object, **kwargs: object) -> Any:
        raise AssertionError("prewarmed cache should be read before live XHS scrape")

    async def explode_put(*args: object, **kwargs: object) -> None:
        raise AssertionError("cache-first path must not rewrite the prewarmed payload")

    monkeypatch.setattr(xhs_mod, "get_cached", fake_get_cached)
    monkeypatch.setattr(xhs_mod, "put_cached", explode_put)
    monkeypatch.setattr(_playwright_session, "fetch", explode_fetch)

    tool = XHSSearchTool()
    result = await tool.execute(XHSSearchInput(query="tokyo ramen"))

    assert result.ok
    assert result.output is not None
    assert result.output[0].id == "prewarm"
    assert result.output[0].images == ("/media/xhs/aa/photo.webp",)
    assert "prewarmed cache hit" in result.notes


@pytest.mark.unit
async def test_tier1_scrape_success_caches_and_returns(
    monkeypatch: pytest.MonkeyPatch, real_mode: None
) -> None:
    monkeypatch.setenv("XHS_PREFER_CACHE", "0")
    monkeypatch.delenv("XHS_STORAGE_STATE", raising=False)
    scraped = [_post("s1"), _post("s2")]

    async def fake_fetch(query: str, **kwargs: Any) -> _playwright_session.FetchResult:
        assert query == "tokyo ramen"
        assert kwargs["cookie"] is None
        assert kwargs["storage_state_path"] is None
        assert kwargs["profile_dir"] is None
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
    assert [post["id"] for post in written[0][2]] == ["s1", "s2"]
    assert written[0][2][0]["authenticity_score"] >= 0.35
    assert written[0][2][0]["is_promotional"] is False
    assert "public playwright" in result.notes


@pytest.mark.unit
async def test_tier1_ignores_configured_session_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PLUS_ONE_TOOLS_MODE", "real")
    monkeypatch.setenv("XHS_PREFER_CACHE", "0")
    monkeypatch.setenv("XHS_COOKIE", "sess=abc; userid=42")
    monkeypatch.setenv("XHS_STORAGE_STATE", "state.json")
    monkeypatch.setenv("XHS_PROFILE_DIR", ".auth/xhs-profile")
    scraped = [_post("p1")]

    async def fake_fetch(query: str, **kwargs: Any) -> _playwright_session.FetchResult:
        assert query == "tokyo ramen"
        assert kwargs["cookie"] is None
        assert kwargs["storage_state_path"] is None
        assert kwargs["profile_dir"] is None
        return _playwright_session.FetchResult(posts=scraped)

    written: list[tuple[str, str, list[dict[str, Any]]]] = []

    async def fake_put_cached(source: str, key: str, payload: list[dict[str, Any]]) -> None:
        written.append((source, key, payload))

    async def explode_get(*args: object, **kwargs: object) -> Any:
        raise AssertionError("get_cached must not run on tier 1 success")

    monkeypatch.setattr(_playwright_session, "fetch", fake_fetch)
    monkeypatch.setattr(xhs_mod, "put_cached", fake_put_cached)
    monkeypatch.setattr(xhs_mod, "get_cached", explode_get)

    tool = XHSSearchTool()
    result = await tool.execute(XHSSearchInput(query="tokyo ramen"))

    assert result.ok
    assert result.output is not None
    assert [p.id for p in result.output] == ["p1"]
    assert len(written) == 1
    assert written[0][0] == "xhs"
    assert written[0][1] == "tokyo_ramen"
    assert [post["id"] for post in written[0][2]] == ["p1"]
    assert written[0][2][0]["authenticity_score"] >= 0.35
    assert "public playwright" in result.notes


@pytest.mark.unit
async def test_tier1_can_opt_into_configured_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PLUS_ONE_TOOLS_MODE", "real")
    monkeypatch.setenv("XHS_PREFER_CACHE", "0")
    monkeypatch.setenv("XHS_USE_CONFIGURED_SESSION", "1")
    monkeypatch.setenv("XHS_COOKIE", "sess=abc; userid=42")
    monkeypatch.setenv("XHS_STORAGE_STATE", "state.json")
    monkeypatch.setenv("XHS_PROFILE_DIR", ".auth/xhs-profile")
    scraped = [_post("p1")]

    async def fake_fetch(query: str, **kwargs: Any) -> _playwright_session.FetchResult:
        assert query == "tokyo ramen"
        assert kwargs["cookie"] is None
        assert kwargs["storage_state_path"] is None
        assert kwargs["profile_dir"] == ".auth/xhs-profile"
        return _playwright_session.FetchResult(posts=scraped)

    async def fake_put_cached(*args: object, **kwargs: object) -> None:
        del args, kwargs

    async def explode_get(*args: object, **kwargs: object) -> Any:
        raise AssertionError("get_cached must not run on tier 1 success")

    monkeypatch.setattr(_playwright_session, "fetch", fake_fetch)
    monkeypatch.setattr(xhs_mod, "put_cached", fake_put_cached)
    monkeypatch.setattr(xhs_mod, "get_cached", explode_get)

    tool = XHSSearchTool()
    result = await tool.execute(XHSSearchInput(query="tokyo ramen"))

    assert result.ok
    assert "persistent_profile playwright" in result.notes


# === Tier 1 fail -> Tier 2 hit ============================================


@pytest.mark.unit
async def test_tier1_fail_tier2_cache_hit(monkeypatch: pytest.MonkeyPatch, real_mode: None) -> None:
    monkeypatch.setenv("XHS_PREFER_CACHE", "0")
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
async def test_public_search_gate_uses_search_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PLUS_ONE_TOOLS_MODE", "real")
    monkeypatch.delenv("XHS_COOKIE", raising=False)

    async def fake_fetch(*args: Any, **kwargs: Any) -> Any:
        assert kwargs["cookie"] is None
        raise RuntimeError("public search gated")

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

    async def fake_enrich_indexed_posts(
        self: object, posts: list[dict[str, Any]], limit: int
    ) -> list[dict[str, Any]]:
        del self, limit
        enriched = [dict(post) for post in posts]
        enriched[0].update(
            {
                "title": "东京拉面真实体验",
                "body": "本地朋友带我去 tokyo ramen, 排队30分钟, 汤底不错。",
                "images": ["/media/xhs/abc123.webp"],
            }
        )
        enriched[0].pop("xhs_index_stub", None)
        return enriched

    monkeypatch.setattr(XHSSearchTool, "_enrich_indexed_posts", fake_enrich_indexed_posts)

    html = """
    <html><body>
      <a class="result__a" href="/l/?uddg=https%3A%2F%2Fwww.xiaohongshu.com%2Fexplore%2Fabc123%3Fxsec_token%3Dtok%26noisy%3D1">
        东京拉面真实体验
      </a>
    </body></html>
    """
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text=html, request=request))
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
    assert written[0][2][0]["authenticity_score"] >= 0.35


@pytest.mark.unit
async def test_unenriched_search_index_stub_does_not_cache_or_return_hit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PLUS_ONE_TOOLS_MODE", "real")
    monkeypatch.delenv("XHS_COOKIE", raising=False)

    async def fake_fetch(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        raise RuntimeError("public search gated")

    async def fake_get_cached(source: str, key: str) -> list[dict[str, Any]] | None:
        del source, key
        return None

    async def explode_put(*args: object, **kwargs: object) -> None:
        raise AssertionError("unenriched search-index stubs must not be cached")

    def fake_load_fixture(directory: Any, key: str) -> list[dict[str, Any]]:
        del directory, key
        return []

    async def fake_search_index(self: object, query: str, limit: int) -> list[dict[str, Any]]:
        del self, limit
        return [
            {
                "id": "idx-stub",
                "author": "public search index",
                "title": "小红书",
                "body": "",
                "likes": 0,
                "comments": 0,
                "url": "https://www.xiaohongshu.com/explore/idx-stub",
                "images": [],
                "xhs_index_query": query,
                "xhs_index_stub": True,
            }
        ]

    monkeypatch.setattr(_playwright_session, "fetch", fake_fetch)
    monkeypatch.setattr(xhs_mod, "get_cached", fake_get_cached)
    monkeypatch.setattr(xhs_mod, "put_cached", explode_put)
    monkeypatch.setattr(xhs_mod, "load_json_fixture", fake_load_fixture)
    monkeypatch.setattr(XHSSearchTool, "_fetch_from_search_index", fake_search_index)

    tool = XHSSearchTool()
    result = await tool.execute(XHSSearchInput(query="tokyo ramen"))

    assert result.ok
    assert result.output == []
    assert result.notes == "degraded"


@pytest.mark.unit
async def test_default_public_playwright_uses_search_index_after_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PLUS_ONE_TOOLS_MODE", "real")
    monkeypatch.delenv("XHS_COOKIE", raising=False)
    monkeypatch.delenv("XHS_PROFILE_DIR", raising=False)
    monkeypatch.delenv("XHS_STORAGE_STATE", raising=False)
    indexed = [_post("idx-no-cookie")]

    async def fake_fetch(*args: object, **kwargs: Any) -> Any:
        assert kwargs["cookie"] is None
        assert kwargs["profile_dir"] is None
        assert kwargs["storage_state_path"] is None
        raise RuntimeError("public search gated")

    written: list[tuple[str, str, list[dict[str, Any]]]] = []

    async def fake_put_cached(source: str, key: str, payload: list[dict[str, Any]]) -> None:
        written.append((source, key, payload))

    async def fake_get_cached(source: str, key: str) -> list[dict[str, Any]] | None:
        assert source == "xhs"
        return None

    async def fake_search_index(self: object, query: str, limit: int) -> list[dict[str, Any]]:
        del self, query, limit
        return indexed

    monkeypatch.setattr(_playwright_session, "fetch", fake_fetch)
    monkeypatch.setattr(xhs_mod, "get_cached", fake_get_cached)
    monkeypatch.setattr(xhs_mod, "put_cached", fake_put_cached)
    monkeypatch.setattr(XHSSearchTool, "_fetch_from_search_index", fake_search_index)

    tool = XHSSearchTool()
    result = await tool.execute(XHSSearchInput(query="tokyo ramen"))

    assert result.ok
    assert result.output is not None
    assert [p.id for p in result.output] == ["idx-no-cookie"]
    assert len(written) == 1
    assert written[0][0] == "xhs"
    assert written[0][1] == "tokyo_ramen"
    assert [post["id"] for post in written[0][2]] == ["idx-no-cookie"]
    assert written[0][2][0]["authenticity_score"] >= 0.35
    assert "public search index hit" in result.notes


@pytest.mark.unit
async def test_public_tier1_empty_continues_to_fixture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PLUS_ONE_TOOLS_MODE", "real")
    monkeypatch.delenv("XHS_COOKIE", raising=False)
    monkeypatch.delenv("XHS_PROFILE_DIR", raising=False)
    monkeypatch.delenv("XHS_STORAGE_STATE", raising=False)
    fixture_payload = [_post("f-empty")]
    fixture_payload[0]["title"] = "Menya Itto 真实体验"
    fixture_payload[0]["body"] = "本地朋友带我去 Menya Itto, 排队40分钟, 但是汤底很稳。"

    async def fake_fetch(*args: object, **kwargs: Any) -> _playwright_session.FetchResult:
        assert kwargs["cookie"] is None
        assert kwargs["profile_dir"] is None
        assert kwargs["storage_state_path"] is None
        return _playwright_session.FetchResult(posts=[])

    async def fake_get_cached(source: str, key: str) -> list[dict[str, Any]] | None:
        assert source == "xhs"
        return []

    async def fake_search_index(self: object, query: str, limit: int) -> list[dict[str, Any]]:
        del self, query, limit
        return []

    async def explode_put(*args: object, **kwargs: object) -> None:
        raise AssertionError("empty search-index miss must not cache an empty payload")

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
    monkeypatch.delenv("XHS_PROFILE_DIR", raising=False)
    monkeypatch.delenv("XHS_STORAGE_STATE", raising=False)
    cached_payload = [_post("c-no-cookie")]

    async def fake_fetch(*args: object, **kwargs: Any) -> Any:
        assert kwargs["cookie"] is None
        assert kwargs["profile_dir"] is None
        assert kwargs["storage_state_path"] is None
        raise RuntimeError("public search gated")

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
