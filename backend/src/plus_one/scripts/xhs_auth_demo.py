"""Tiny XHS auth demo: headed login, then profile-backed crawl.

This script is deliberately separate from the production XHS scraper. It is a
small experiment for validating whether a headed browser login stored in a
persistent profile can be reused by a later crawl, including image caching.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import parse_qs, urlencode, urlparse

from plus_one.core.tools import _playwright_session

ROOT = Path(__file__).resolve().parents[4]
DEFAULT_STATE_FILE = ROOT / "backend" / ".auth" / "xhs-storage-state.json"
DEFAULT_PROFILE_DIR = ROOT / "backend" / ".auth" / "xhs-profile"
DEFAULT_OUTPUT_FILE = ROOT / "tmp-xhs-auth-demo-result.json"
DEFAULT_QUERY = "\u4e1c\u4eac AFURI \u7f8e\u98df\u63a8\u8350"
XHS_HOME_URL = "https://www.xiaohongshu.com/"
XHS_SEARCH_SOURCE = "web_search_result_notes"

PageState = Literal["ok", "login_required", "security_gate"]


class DemoNavigationError(RuntimeError):
    """Navigation/search-entry failed after a page was loaded enough to inspect."""


def classify_page_state(url: str, body_text: str) -> PageState:
    """Classify the loaded XHS page state without raising."""
    if _playwright_session._has_login_wall_text(body_text) or _has_login_panel_text(body_text):
        return "login_required"
    if _playwright_session._is_verification_url(url) or _playwright_session._has_verification_text(
        body_text
    ):
        return "security_gate"
    return "ok"


def _has_login_panel_text(body_text: str) -> bool:
    return (
        ("手机号登录" in body_text or "扫码" in body_text)
        and "登录" in body_text
        and ("登录后推荐" in body_text or "马上登录" in body_text or "获取验证码" in body_text)
    )


def build_crawl_result(
    *,
    query: str,
    state: PageState,
    url: str,
    posts: list[dict[str, Any]],
    detail: dict[str, Any] | None = None,
    diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a stable JSON payload for the demo crawl command."""
    return {
        "ok": state == "ok" and bool(posts),
        "state": state,
        "query": query,
        "url": url,
        "post_count": len(posts),
        "posts": posts,
        "detail": detail,
        "diagnostics": diagnostics or {},
        "finished_at": datetime.now(UTC).isoformat(),
    }


def json_for_stdout(payload: dict[str, Any]) -> str:
    """Return JSON that is safe for Windows legacy console encodings."""
    return json.dumps(payload, ensure_ascii=True, indent=2)


def build_page_diagnostics(
    *,
    url: str,
    body_text: str,
    selector_counts: dict[str, int],
) -> dict[str, Any]:
    """Extract compact page diagnostics for blocked or empty demo crawls."""
    lines = [line.strip() for line in body_text.splitlines() if line.strip()]
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    code = query.get("error_code", [""])[0]
    if not code:
        code = next((line for line in lines if re.fullmatch(r"\d{5,}", line)), "")
    security_message = ""
    if lines and any("安全" in line for line in lines):
        security_message = next(
            (line for line in lines if line and "安全" not in line and not line.isdigit()),
            "",
        )
    return {
        "url_path": parsed.path,
        "body_sample": body_text[:500],
        "selector_counts": selector_counts,
        "security_error_code": code,
        "security_message": security_message,
    }


def _search_url(query: str) -> str:
    return "https://www.xiaohongshu.com/search_result?" + urlencode(
        {"keyword": query, "source": XHS_SEARCH_SOURCE}
    )


async def _selector_counts(page: Any) -> dict[str, int]:
    return dict(
        await page.evaluate(
            r"""
            () => {
              const selectors = [
                'section.note-item',
                'section[data-index]',
                'a[href*="/explore/"]',
                'a[href*="/search_result/"]',
                '[class*="note"]',
                '[class*="feeds"]',
                'img',
                'input',
                'textarea',
              ];
              return Object.fromEntries(selectors.map((selector) => [selector, document.querySelectorAll(selector).length]));
            }
            """
        )
    )


async def _body_text(page: Any) -> str:
    return str(await page.evaluate("() => document.body && document.body.innerText || ''"))


async def _goto_search(page: Any, query: str, *, entry: str, timeout_s: float) -> None:
    if entry == "home":
        await page.goto(XHS_HOME_URL, wait_until="domcontentloaded", timeout=int(timeout_s * 1000))
        await _playwright_session._random_page_wait(page, 1.2, 2.8)
        body_text = await _body_text(page)
        state = classify_page_state(page.url, body_text)
        if state != "ok":
            raise DemoNavigationError(f"xhs home entry blocked: {state}")
        await _playwright_session._human_mouse_pause(page)
        search_box = page.locator(
            'textarea[placeholder*="搜索"]:visible, '
            'textarea[placeholder*="问题"]:visible, '
            'input[placeholder*="搜索"]:visible, '
            'input[type="search"]:visible, '
            '[contenteditable="true"]:visible'
        ).first
        try:
            await search_box.wait_for(state="visible", timeout=min(int(timeout_s * 1000), 10_000))
        except Exception as exc:
            raise DemoNavigationError("xhs home entry search box not visible") from exc
        await search_box.click(timeout=5_000)
        await page.keyboard.press("Control+A")
        await page.keyboard.type(
            query, delay=int(_playwright_session._random_delay_seconds(0.045, 0.12) * 1000)
        )
        await _playwright_session._random_page_wait(page, 0.35, 1.1)
        await page.keyboard.press("Enter")
        await _playwright_session._random_page_wait(page, 1.8, 3.8)
        return
    await page.goto(
        _search_url(query), wait_until="domcontentloaded", timeout=int(timeout_s * 1000)
    )


async def _demo_search_dwell(page: Any, args: argparse.Namespace) -> None:
    await _playwright_session._random_page_wait(page, max(0.5, args.dwell_s * 0.5), args.dwell_s)
    await _playwright_session._wait_for_lazy_content_images(page, min_images=1, timeout_s=2.0)
    for _ in range(max(0, args.scrolls)):
        body_text = await _body_text(page)
        if classify_page_state(page.url, body_text) != "ok":
            return
        await _playwright_session._human_mouse_pause(page)
        await _playwright_session._human_scroll_page(page)
        await _playwright_session._wait_for_lazy_content_images(page, min_images=1, timeout_s=2.0)


async def login_command(args: argparse.Namespace) -> None:
    """Open a headed browser, let the user login, then save storage state."""
    from playwright.async_api import async_playwright  # noqa: PLC0415

    state_file = Path(args.state_file)
    state_file.parent.mkdir(parents=True, exist_ok=True)
    profile_dir = Path(args.profile_dir) if args.profile_dir else None

    async with async_playwright() as pw:
        browser = None
        if profile_dir is not None:
            profile_dir.mkdir(parents=True, exist_ok=True)
            context = await pw.chromium.launch_persistent_context(
                profile_dir,
                headless=False,
                locale="zh-CN",
                timezone_id="Asia/Shanghai",
                user_agent=_playwright_session.pick_user_agent(device_profile="desktop"),
            )
        else:
            browser = await pw.chromium.launch(headless=False)
            context = await browser.new_context(locale="zh-CN", timezone_id="Asia/Shanghai")
        page = await context.new_page()
        await page.goto(
            XHS_HOME_URL, wait_until="domcontentloaded", timeout=int(args.timeout_s * 1000)
        )
        print("A headed XHS browser is open. Log in or solve the security check there.")
        await asyncio.to_thread(input, "Press Enter here after XHS search works in that browser...")
        await context.storage_state(path=str(state_file))
        await context.close()
        if browser is not None:
            await browser.close()

    print(f"saved storage state: {state_file}")


async def crawl_command(args: argparse.Namespace) -> dict[str, Any]:
    """Run one crawl using a logged-in persistent profile or storage state."""
    from playwright.async_api import async_playwright  # noqa: PLC0415

    profile_dir = Path(args.profile_dir) if args.profile_dir else None
    state_file = Path(args.state_file)
    if profile_dir is None and not await asyncio.to_thread(state_file.exists):
        raise FileNotFoundError(f"storage state not found: {state_file}")

    async with async_playwright() as pw:
        context, browser, auth_mode = await _open_demo_context(
            pw,
            profile_dir=profile_dir,
            state_file=state_file,
            headed=args.headed,
        )
        try:
            result = await _crawl_with_context(context, args, auth_mode=auth_mode)
        finally:
            await context.close()
            if browser is not None:
                await browser.close()

    output_file = Path(args.output_file)
    await asyncio.to_thread(
        output_file.write_text,
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json_for_stdout(result))
    print(f"wrote result: {output_file}")
    return result


async def _open_demo_context(
    pw: Any,
    *,
    profile_dir: Path | None,
    state_file: Path,
    headed: bool,
) -> tuple[Any, Any | None, str]:
    if profile_dir is not None:
        await asyncio.to_thread(profile_dir.mkdir, parents=True, exist_ok=True)
        context = await pw.chromium.launch_persistent_context(
            profile_dir,
            headless=not headed,
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            user_agent=_playwright_session.pick_user_agent(device_profile="desktop"),
        )
        return context, None, "persistent_profile"

    browser = await pw.chromium.launch(headless=not headed)
    context = await browser.new_context(
        storage_state=str(state_file),
        locale="zh-CN",
        timezone_id="Asia/Shanghai",
        user_agent=_playwright_session.pick_user_agent(device_profile="desktop"),
    )
    return context, browser, "storage_state"


async def _crawl_with_context(
    context: Any, args: argparse.Namespace, *, auth_mode: str
) -> dict[str, Any]:
    page = await context.new_page()
    page.set_default_timeout(int(args.timeout_s * 1000))
    page.set_default_navigation_timeout(int(args.timeout_s * 1000))
    try:
        navigation_error = await _try_goto_search(page, args)
        await _demo_search_dwell(page, args)
        body_text = await _body_text(page)
        state = classify_page_state(page.url, body_text)
        diagnostics = await _crawl_diagnostics(
            page,
            body_text=body_text,
            navigation_error=navigation_error,
            auth_mode=auth_mode,
            args=args,
        )
        posts, detail = await _extract_posts_and_detail(context, page, state, args)
        return build_crawl_result(
            query=args.query,
            state=state,
            url=page.url,
            posts=posts,
            detail=detail,
            diagnostics=diagnostics,
        )
    finally:
        await page.close()


async def _try_goto_search(page: Any, args: argparse.Namespace) -> str:
    try:
        await _goto_search(page, args.query, entry=args.entry, timeout_s=args.timeout_s)
        return ""
    except DemoNavigationError as exc:
        return str(exc)


async def _crawl_diagnostics(
    page: Any,
    *,
    body_text: str,
    navigation_error: str,
    auth_mode: str,
    args: argparse.Namespace,
) -> dict[str, Any]:
    diagnostics = build_page_diagnostics(
        url=page.url,
        body_text=body_text,
        selector_counts=await _selector_counts(page),
    )
    if navigation_error:
        diagnostics["navigation_error"] = navigation_error
    diagnostics["auth_mode"] = auth_mode
    diagnostics["search_scrolls"] = args.scrolls
    diagnostics["cache_images"] = bool(args.cache_images)
    diagnostics["images_per_post"] = args.images_per_post
    return diagnostics


async def _extract_posts_and_detail(
    context: Any,
    page: Any,
    state: PageState,
    args: argparse.Namespace,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    if state != "ok":
        return [], None

    posts = list(await page.evaluate(_SEARCH_DEMO_JS, args.limit))[: args.limit]
    detail = None
    if args.detail and posts:
        detail = await _fetch_detail(
            context,
            str(posts[0].get("url") or ""),
            args.timeout_s,
            scroll=not args.no_detail_scroll,
        )
    if args.cache_images and posts:
        posts_for_cache = _posts_with_detail_images(posts, detail)
        posts = await _playwright_session._cache_post_images_with_context(
            context,
            posts_for_cache,
            images_per_post=args.images_per_post,
            timeout_s=args.timeout_s,
        )
        detail = _detail_with_cached_images(detail, posts[0] if posts else None)
    return posts, detail


async def _fetch_detail(
    context: Any,
    url: str,
    timeout_s: float,
    *,
    scroll: bool,
) -> dict[str, Any] | None:
    if not url:
        return None
    page = await context.new_page()
    try:
        page.set_default_timeout(int(timeout_s * 1000))
        page.set_default_navigation_timeout(int(timeout_s * 1000))
        await page.goto(url, wait_until="domcontentloaded", timeout=int(timeout_s * 1000))
        await _playwright_session._random_page_wait(page, 1.8, 4.0)
        body_text = await _body_text(page)
        state = classify_page_state(page.url, body_text)
        if state != "ok":
            return {"state": state, "url": page.url, "body": "", "images": []}
        await _playwright_session._human_mouse_pause(page)
        if scroll:
            await _playwright_session._human_scroll_page(page)
        await _playwright_session._wait_for_lazy_content_images(page, min_images=1, timeout_s=2.5)
        detail = await page.evaluate(_DETAIL_DEMO_JS)
        if isinstance(detail, dict):
            detail["state"] = "ok"
            return detail
        return None
    finally:
        await page.close()


def _posts_with_detail_images(
    posts: list[dict[str, Any]],
    detail: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not posts or not isinstance(detail, dict):
        return posts
    first = dict(posts[0])
    for key in ("title", "body"):
        value = detail.get(key)
        if isinstance(value, str) and value.strip():
            first[key] = value.strip()
    images = detail.get("images")
    if isinstance(images, list) and images:
        first["images"] = images
    return [first, *posts[1:]]


def _detail_with_cached_images(
    detail: dict[str, Any] | None,
    first_post: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(detail, dict) or not isinstance(first_post, dict):
        return detail
    updated = dict(detail)
    updated["source_images"] = first_post.get("source_images") or detail.get("images") or []
    updated["cached_images"] = first_post.get("cached_images") or []
    display_images = first_post.get("images")
    if isinstance(display_images, list):
        updated["images"] = display_images
    return updated


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Demo headed XHS login -> persistent-profile crawl"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    login = sub.add_parser("login", help="open headed browser and export storage state")
    login.add_argument("--state-file", default=str(DEFAULT_STATE_FILE))
    login.add_argument("--profile-dir", default=str(DEFAULT_PROFILE_DIR))
    login.add_argument("--timeout-s", type=float, default=60.0)

    crawl = sub.add_parser("crawl", help="run one crawl with the logged-in profile")
    crawl.add_argument("--state-file", default=str(DEFAULT_STATE_FILE))
    crawl.add_argument("--query", default=DEFAULT_QUERY)
    crawl.add_argument("--limit", type=int, default=5)
    crawl.add_argument("--timeout-s", type=float, default=20.0)
    crawl.add_argument("--dwell-s", type=float, default=4.0)
    crawl.add_argument("--output-file", default=str(DEFAULT_OUTPUT_FILE))
    crawl.add_argument("--detail", action="store_true", help="open the first result detail page")
    crawl.add_argument("--entry", choices=("direct", "home"), default="home")
    crawl.add_argument(
        "--profile-dir",
        default=str(DEFAULT_PROFILE_DIR),
        help="persistent browser profile to reuse; pass an empty value to use storage_state instead",
    )
    crawl.add_argument("--headed", action="store_true", help="show the browser while crawling")
    crawl.add_argument(
        "--cache-images",
        action="store_true",
        help="download note images into the local media cache",
    )
    crawl.add_argument("--images-per-post", type=int, default=3)
    crawl.add_argument(
        "--scrolls", type=int, default=2, help="reader-like search result scrolls before extraction"
    )
    crawl.add_argument(
        "--no-detail-scroll", action="store_true", help="skip the reader-like detail-page scroll"
    )
    return parser


async def async_main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if args.command == "login":
        await login_command(args)
        return
    if args.command == "crawl":
        await crawl_command(args)
        return
    raise ValueError(f"unknown command: {args.command}")


def main() -> None:
    asyncio.run(async_main())


_SEARCH_DEMO_JS = r"""
(limit) => {
  const out = [];
  const seen = new Set();
  const parseHref = (href) => {
    const raw = String(href || '');
    const match = raw.match(/\/(?:explore|search_result)\/([a-z0-9]+)/i);
    if (!match) return null;
    return {id: match[1], url: new URL(raw, 'https://www.xiaohongshu.com').toString()};
  };
  const cards = Array.from(document.querySelectorAll('section.note-item, section[data-index], section'));
  for (const card of cards) {
    if (out.length >= limit) break;
    const anchor = Array.from(card.querySelectorAll('a[href*="/explore/"], a[href*="/search_result/"]'))
      .map((a) => ({a, parsed: parseHref(a.getAttribute('href'))}))
      .filter((item) => item.parsed)
      .sort((left, right) => Number(right.parsed.url.includes('xsec_token=')) - Number(left.parsed.url.includes('xsec_token=')))[0];
    if (!anchor) continue;
    const id = anchor.parsed.id;
    if (seen.has(id)) continue;
    seen.add(id);
    const img = card.querySelector('img[data-xhs-img], img:not(.author-avatar)');
    const src = img && (img.currentSrc || img.src || img.getAttribute('data-src')) || '';
    out.push({
      id,
      title: (card.querySelector('.title, [class*="title"]')?.textContent || '').trim(),
      author: (card.querySelector('[class*="author"], [class*="user"]')?.textContent || '').trim(),
      url: anchor.parsed.url,
      images: /^https?:\/\//.test(src) ? [src] : [],
    });
  }
  return out;
}
"""


_DETAIL_DEMO_JS = r"""
() => {
  const textOf = (selectors) => {
    for (const selector of selectors) {
      const text = (document.querySelector(selector)?.textContent || '').trim();
      if (text) return text;
    }
    return '';
  };
  const images = Array.from(document.querySelectorAll('meta[property="og:image"], img, source'))
    .flatMap((el) => ['content', 'src', 'data-src', 'currentSrc', 'srcset']
      .map((attr) => el.getAttribute(attr) || el[attr] || '')
      .flatMap((raw) => String(raw).split(',').map((part) => part.trim().split(/\s+/)[0])))
    .filter((src) => /^https?:\/\//.test(src) && src.includes('xhscdn.com') && !/(avatar|favicon|icon|logo)/i.test(src))
    .filter((src, index, all) => all.indexOf(src) === index)
    .slice(0, 8);
  return {
    url: location.href,
    title: textOf(['#detail-title', '[class*="title"]']),
    body: textOf(['#detail-desc', '[class*="note-content"]', '[class*="desc"]', '[class*="content"]']),
    images,
  };
}
"""


if __name__ == "__main__":
    main()
