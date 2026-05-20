"""Thin Playwright wrapper used by the XHS real-mode scraper.

Per PRD Batch 2k §5.4 this module is intentionally minimal in v1:

  * A single process-wide ``Browser`` is created lazily on first call
    and reused across requests. v1 is single-worker per ADR-006, so a
    process-level singleton + ``atexit`` cleanup is sufficient.
  * Each request gets a fresh ``BrowserContext`` with a (rotating)
    User-Agent and the caller-supplied cookie blob injected, so
    sessions never leak between requests.
  * Failures (timeouts, 429s, captchas surfaced as response status,
    arbitrary exceptions) bubble up; the caller (``XHSSearchTool``)
    decides how to degrade (tier 2 then tier 3).

The ``fetch`` function below has an exponential-backoff retry loop
(max 3 attempts) for 429 responses only — other failures fail fast so
the tool can fall through to tier 2 / tier 3 quickly rather than
holding the cycle hostage on a sleep loop.

Tests MUST monkeypatch ``fetch`` (and never let real Chromium boot) —
see ``tests/unit/tools/test_xhs_tiers.py``.
"""

from __future__ import annotations

import asyncio
import atexit
import contextlib
import secrets
from dataclasses import dataclass
from typing import Any

import structlog

logger = structlog.get_logger()


# A small rotation pool — enough to look human-ish without pretending we
# have real residential profiles (that's a v2 ADR-003 problem).
_USER_AGENTS: tuple[str, ...] = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
)

_MAX_RETRIES = 3
_BACKOFF_BASE_S = 1.0
_HTTP_TOO_MANY_REQUESTS = 429
_HTTP_CLIENT_ERROR_FLOOR = 400


@dataclass
class FetchResult:
    """Result of one scrape attempt."""

    posts: list[dict[str, Any]]


# Module-level browser singleton stashed in a single-slot list so we
# don't need ``global`` (ruff PLW0603). The list itself is module-level
# immutable. ``Any`` typing keeps mypy happy without forcing every
# import path to load playwright; the real type is
# ``playwright.async_api.Browser``.
_browser_slot: list[Any] = [None]
_pw_ctx_slot: list[Any] = [None]
_browser_lock = asyncio.Lock()


def pick_user_agent(override: str | None = None) -> str:
    """Return the override if provided, else a random UA from the pool."""
    if override:
        return override
    return secrets.choice(_USER_AGENTS)


async def _get_browser() -> Any:
    """Lazily start Playwright + Chromium. Reused across calls."""
    async with _browser_lock:
        if _browser_slot[0] is not None:
            return _browser_slot[0]
        # Local import: keeps fixture-mode imports free of Playwright cost
        # and lets unit tests stub ``fetch`` without playwright installed.
        from playwright.async_api import async_playwright  # noqa: PLC0415

        _pw_ctx_slot[0] = await async_playwright().start()
        _browser_slot[0] = await _pw_ctx_slot[0].chromium.launch(headless=True)
        atexit.register(_atexit_close)
        return _browser_slot[0]


def _atexit_close() -> None:
    """Best-effort cleanup on interpreter shutdown.

    Schedules the async ``close`` on a fresh loop because by atexit the
    original loop is gone. Swallows everything — a noisy shutdown is
    worse than a quiet one.
    """
    with contextlib.suppress(Exception):
        asyncio.run(_aclose())


async def _aclose() -> None:
    if _browser_slot[0] is not None:
        with contextlib.suppress(Exception):
            await _browser_slot[0].close()
        _browser_slot[0] = None
    if _pw_ctx_slot[0] is not None:
        with contextlib.suppress(Exception):
            await _pw_ctx_slot[0].stop()
        _pw_ctx_slot[0] = None


async def fetch(
    query: str,
    *,
    cookie: str,
    limit: int,
    user_agent: str | None = None,
    timeout_s: float = 30.0,
) -> FetchResult:
    """Scrape XHS search results for ``query``.

    Raises on hard failure (timeout, persistent 429, captcha-like
    response). The caller is responsible for falling back to tier 2 /
    tier 3 on exception.

    v1 implementation note: the exact DOM-scraping logic is intentionally
    minimal — we navigate to the search URL, wait for the network to be
    idle, and parse anchors that match the note-detail URL pattern. If
    XHS changes their markup the test mocks still pass (we mock this
    whole function), but a manual dev test will surface the breakage as
    "tier 1 returned 0 posts -> tier 2 / tier 3".
    """
    ua = pick_user_agent(user_agent)
    browser = await _get_browser()

    last_exc: Exception | None = None
    for attempt in range(1, _MAX_RETRIES + 1):
        context = await browser.new_context(user_agent=ua)
        try:
            # Inject the cookie blob. We accept opaque cookie strings of
            # either "k=v; k2=v2" form (browser cookie header) or a JSON
            # list of cookie dicts. Anything else: best-effort, log and
            # try to navigate anyway — XHS may still gate via JS.
            await _inject_cookie(context, cookie)
            page = await context.new_page()
            page.set_default_timeout(int(timeout_s * 1000))

            url = (
                "https://www.xiaohongshu.com/search_result"
                f"?keyword={query}&source=web_search_result_notes"
            )
            response = await page.goto(url, wait_until="networkidle")
            status = response.status if response is not None else 0

            if status == _HTTP_TOO_MANY_REQUESTS:
                logger.warning("xhs_rate_limited", attempt=attempt, status=status, query=query)
                await context.close()
                if attempt == _MAX_RETRIES:
                    raise RuntimeError(f"xhs rate limited after {attempt} attempts")
                # Exponential backoff with jitter.
                jitter = secrets.randbelow(1000) / 1000.0
                await asyncio.sleep(_BACKOFF_BASE_S * (2 ** (attempt - 1)) + jitter)
                continue

            if status >= _HTTP_CLIENT_ERROR_FLOOR:
                raise RuntimeError(f"xhs returned http {status}")

            # Best-effort DOM extraction. Schema is documented in
            # ``XHSPost``.
            posts = await page.evaluate(_SCRAPE_JS, limit)
            await context.close()
            return FetchResult(posts=list(posts)[:limit])

        except Exception as exc:
            last_exc = exc
            with contextlib.suppress(Exception):
                await context.close()
            # Only 429s get retried (handled via ``continue`` above);
            # any other failure bails immediately so the
            # tier-2/tier-3 fallback isn't blocked on a long retry.
            raise

    # Loop fell through only via 429 path; re-raise the last seen.
    raise RuntimeError(f"xhs fetch exhausted retries: {last_exc!r}")


async def _inject_cookie(context: Any, cookie: str) -> None:
    """Best-effort cookie injection.

    Accepts a raw header-style cookie string. We split on ``;`` and add
    each pair as a domain cookie. Caller-controlled string; failures
    are logged and swallowed (the navigation might still succeed for
    queries that don't gate on auth).
    """
    cookies = []
    for piece in cookie.split(";"):
        if "=" not in piece:
            continue
        name, _, value = piece.strip().partition("=")
        if not name:
            continue
        cookies.append(
            {
                "name": name,
                "value": value,
                "domain": ".xiaohongshu.com",
                "path": "/",
            }
        )
    if not cookies:
        logger.warning("xhs_cookie_empty_after_parse")
        return
    try:
        await context.add_cookies(cookies)
    except Exception as exc:
        logger.warning("xhs_cookie_inject_failed", error=str(exc))


# Kept as a module constant so a future test could swap it without
# touching ``fetch``. Returns a list of {id, author, title, body,
# likes, comments, url, images} dicts matching ``XHSPost`` field names.
_SCRAPE_JS = """
(limit) => {
  const out = [];
  const seen = new Set();
  const anchors = document.querySelectorAll('a[href*="/explore/"]');
  for (const a of anchors) {
    if (out.length >= limit) break;
    const href = a.getAttribute('href') || '';
    const m = href.match(/\\/explore\\/([a-z0-9]+)/i);
    if (!m) continue;
    const id = m[1];
    if (seen.has(id)) continue;
    seen.add(id);
    const card = a.closest('section') || a.parentElement || a;
    const titleEl = card.querySelector('.title, [class*="title"]');
    const authorEl = card.querySelector('[class*="author"], [class*="user"]');
    const likeEl = card.querySelector('[class*="like"], [class*="count"]');
    out.push({
      id: id,
      author: (authorEl && authorEl.textContent || '').trim() || 'unknown',
      title: (titleEl && titleEl.textContent || '').trim() || '',
      body: '',
      likes: parseInt((likeEl && likeEl.textContent || '0').replace(/[^0-9]/g, ''), 10) || 0,
      comments: 0,
      url: 'https://www.xiaohongshu.com' + href,
      images: [],
    });
  }
  return out;
}
"""
