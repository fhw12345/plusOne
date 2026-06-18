"""Thin Playwright wrapper used by the XHS real-mode scraper.

Per PRD Batch 2k §5.4 this module is intentionally minimal in v1:

  * A single process-wide ``Browser`` is created lazily for temporary
    contexts. If ``XHS_PROFILE_DIR`` is configured, we instead create one
    process-wide persistent ``BrowserContext`` backed by that user-data
    directory so XHS can keep durable browser-environment state.
  * Temporary requests get a fresh ``BrowserContext`` with a (rotating)
    User-Agent. Persistent-profile requests open a fresh page in the shared
    context and close only that page after the scrape.
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
import hashlib
import json
import os
import secrets
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlencode, urlparse

import structlog

from plus_one.config import settings

logger = structlog.get_logger()


_MOBILE_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 "
    "Mobile/15E148 Safari/604.1"
)

# A small desktop rotation pool retained for explicit desktop diagnostics.
_DESKTOP_USER_AGENTS: tuple[str, ...] = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
)

_MAX_RETRIES = 3
_DETAIL_EVALUATE_RETRIES = 3
_BACKOFF_BASE_S = 1.0
_HTTP_TOO_MANY_REQUESTS = 429
_HTTP_CLIENT_ERROR_FLOOR = 400
_XHS_NOTE_PATH_MARKERS = ("/explore/", "/search_result/", "/discovery/item/")
_XHS_HOME_URL = "https://www.xiaohongshu.com/explore"
_XHS_SEARCH_SOURCE = "web_search_result_notes"
_XHS_PUBLIC_SEARCH_GATE_TEXT = "登录后查看搜索结果"
_XHS_LOGIN_WALL_TEXT = (
    _XHS_PUBLIC_SEARCH_GATE_TEXT  # Backwards-compatible alias for older helpers/tests.
)
_XHS_VERIFY_TEXT_MARKERS = (
    "安全验证",
    "安全限制",
    "请选择最符合描述",
    "请求太频繁",
    "稍后再试",
    "当前账号存在异常",
    "切换账号后重试",
)
_NAVIGATION_INTERRUPTED_EVALUATE_MARKERS = (
    "execution context was destroyed",
    "most likely because of a navigation",
    "cannot find context with specified id",
)
_XHS_NOT_FOUND_TEXT = "你访问的页面不见了"
_XHS_MAX_IMAGE_BYTES = 6 * 1024 * 1024
_XHS_IMAGE_EXT_BY_TYPE = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
_RANDOM_DELAY_BUCKETS = 10_000


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
_persistent_context_slot: list[Any] = [None]
_persistent_profile_dir_slot: list[str | None] = [None]
_browser_lock = asyncio.Lock()
_persistent_context_lock = asyncio.Lock()
_atexit_registered = False


def pick_user_agent(override: str | None = None, *, device_profile: str = "mobile") -> str:
    """Return the override if provided, else a random UA from the pool."""
    if override:
        return override
    if device_profile == "desktop":
        return secrets.choice(_DESKTOP_USER_AGENTS)
    return _MOBILE_USER_AGENT


def _normalise_device_profile(raw: str | None) -> str:
    value = (raw or "desktop").strip().lower()
    return "desktop" if value == "desktop" else "mobile"


def _device_profile_for_fetch(profile_dir: str | None) -> str:
    raw = os.getenv("XHS_DEVICE_PROFILE")
    if raw:
        return _normalise_device_profile(raw)
    # The XHS search URL used here is the PC web route. Default to desktop web
    # even without a persistent profile so public search probes use the same
    # route a normal browser tab can open.
    return "desktop"


def _headless_for_fetch() -> bool:
    """Allow headed local diagnostics without changing production defaults."""
    return os.getenv("XHS_HEADLESS", "1").strip().lower() not in {"0", "false", "no"}


def _start_minimized_for_fetch() -> bool:
    """Keep headed local XHS scraping from stealing focus while it runs."""
    return os.getenv("XHS_START_MINIMIZED", "1").strip().lower() not in {"0", "false", "no"}


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _random_delay_seconds(min_s: float, max_s: float) -> float:
    low = max(0.0, min_s)
    high = max(low, max_s)
    span = high - low
    if span <= 0:
        return low
    jitter = secrets.randbelow(_RANDOM_DELAY_BUCKETS) / _RANDOM_DELAY_BUCKETS
    return low + span * jitter


async def _random_page_wait(page: Any, min_s: float, max_s: float) -> None:
    delay_s = _random_delay_seconds(min_s, max_s)
    if delay_s <= 0:
        return
    await page.wait_for_timeout(int(delay_s * 1000))


async def _viewport_size(page: Any) -> tuple[int, int]:
    with contextlib.suppress(Exception):
        viewport = page.viewport_size
        if viewport:
            return int(viewport.get("width") or 1280), int(viewport.get("height") or 720)
    with contextlib.suppress(Exception):
        size = await page.evaluate(
            "() => ({width: window.innerWidth || 1280, height: window.innerHeight || 720})"
        )
        if isinstance(size, dict):
            return int(size.get("width") or 1280), int(size.get("height") or 720)
    return 1280, 720


async def _human_mouse_pause(page: Any) -> None:
    """Small cursor movement plus pause to let client-side lazy loading settle."""
    width, height = await _viewport_size(page)
    max_x = max(1, width - 48)
    max_y = max(1, int(height * 0.72) - 80)
    x = 24 + secrets.randbelow(max_x)
    y = 80 + secrets.randbelow(max_y)
    steps = 4 + secrets.randbelow(8)
    with contextlib.suppress(Exception):
        await page.mouse.move(x, y, steps=steps)
    await _random_page_wait(page, 0.15, 0.7)


async def _human_scroll_page(page: Any) -> None:
    """Scroll like a reader so XHS cards/images have a chance to lazy-load."""
    _, height = await _viewport_size(page)
    delta = int(max(260, height * _random_delay_seconds(0.45, 0.9)))
    try:
        await page.mouse.wheel(0, delta)
    except Exception:
        with contextlib.suppress(Exception):
            await page.evaluate(
                "(top) => window.scrollBy({top, behavior: 'smooth'})",
                delta,
            )
    await _random_page_wait(page, 0.8, 2.2)


async def _wait_for_lazy_content_images(
    page: Any,
    *,
    min_images: int = 1,
    timeout_s: float = 3.0,
) -> None:
    with contextlib.suppress(Exception):
        await page.wait_for_function(
            r"""
            (minImages) => Array.from(document.images).filter((img) => {
              const src = String(img.currentSrc || img.src || img.getAttribute('data-src') || '').toLowerCase();
              return src.includes('xhscdn.com')
                && !/(avatar|favicon|icon|logo)/.test(src)
                && img.naturalWidth > 0
                && img.naturalHeight > 0;
            }).length >= minImages
            """,
            max(1, min_images),
            timeout=max(500, int(timeout_s * 1000)),
        )


async def _random_sleep(min_s: float, max_s: float) -> None:
    delay_s = _random_delay_seconds(min_s, max_s)
    if delay_s <= 0:
        return
    await asyncio.sleep(delay_s)


async def _search_page_dwell(page: Any, profile_dir: str | None) -> None:
    await _random_page_wait(
        page,
        _float_env("XHS_SEARCH_DWELL_MIN_S", 4.0),
        _float_env("XHS_SEARCH_DWELL_MAX_S", 9.0),
    )
    await _maybe_minimize_profile_window(profile_dir, delay_s=0.0)


async def _detail_page_dwell(page: Any, profile_dir: str | None) -> None:
    await _random_page_wait(
        page,
        _float_env("XHS_DETAIL_DWELL_MIN_S", 3.0),
        _float_env("XHS_DETAIL_DWELL_MAX_S", 7.0),
    )
    await _maybe_minimize_profile_window(profile_dir, delay_s=0.0)


async def _detail_gap_sleep() -> None:
    await _random_sleep(
        _float_env("XHS_DETAIL_GAP_MIN_S", 2.0),
        _float_env("XHS_DETAIL_GAP_MAX_S", 6.0),
    )


def _search_result_url(query: str) -> str:
    return "https://www.xiaohongshu.com/search_result?" + urlencode(
        {"keyword": query, "source": _XHS_SEARCH_SOURCE}
    )


def _use_home_search_entry(profile_dir: str | None) -> bool:
    raw = os.getenv("XHS_SEARCH_ENTRY", "")
    value = raw.strip().lower()
    if value in {"direct", "url"}:
        return False
    if value in {"home", "homepage", "interactive"}:
        return True
    return bool(profile_dir)


async def _goto_xhs_search(
    page: Any,
    query: str,
    *,
    timeout_s: float,
    profile_dir: str | None,
) -> int:
    """Navigate to XHS search using the least-gated route for the context."""
    if _use_home_search_entry(profile_dir):
        try:
            return await _goto_xhs_search_from_home(
                page, query, timeout_s=timeout_s, profile_dir=profile_dir
            )
        except Exception as exc:
            if _is_gate_exception(exc):
                raise
            logger.warning("xhs_home_search_entry_failed", query=query, error=str(exc)[:300])

    response = await page.goto(
        _search_result_url(query),
        wait_until="domcontentloaded",
        timeout=int(timeout_s * 1000),
    )
    return response.status if response is not None else 0


async def _goto_xhs_search_from_home(
    page: Any,
    query: str,
    *,
    timeout_s: float,
    profile_dir: str | None,
) -> int:
    response = await page.goto(
        _XHS_HOME_URL, wait_until="domcontentloaded", timeout=int(timeout_s * 1000)
    )
    await _maybe_minimize_profile_window(profile_dir, delay_s=0.05)
    await _random_page_wait(page, 1.2, 2.8)
    body_text = await _page_body_text(page)
    _raise_for_gate_url(page.url)
    _raise_for_gate_text(body_text)

    search_box = page.locator(
        'textarea[placeholder*="搜索"]:visible, '
        'textarea[placeholder*="问题"]:visible, '
        'input[placeholder*="搜索"]:visible, '
        'input[type="search"]:visible, '
        '[contenteditable="true"]:visible'
    ).first
    await search_box.wait_for(state="visible", timeout=min(int(timeout_s * 1000), 12_000))
    with contextlib.suppress(Exception):
        await search_box.scroll_into_view_if_needed(timeout=3_000)
    await search_box.click(timeout=min(int(timeout_s * 1000), 5_000))
    await page.keyboard.press("Control+A")
    await page.keyboard.type(query, delay=int(_random_delay_seconds(0.045, 0.12) * 1000))
    await _random_page_wait(page, 0.4, 1.2)
    await page.keyboard.press("Enter")
    await _maybe_minimize_profile_window(profile_dir, delay_s=0.1)
    await _wait_for_search_landing(page, timeout_s=timeout_s)
    return response.status if response is not None else 0


async def _wait_for_search_landing(page: Any, *, timeout_s: float) -> None:
    deadline = asyncio.get_running_loop().time() + min(timeout_s, 20.0)
    while asyncio.get_running_loop().time() < deadline:
        body_text = await _page_body_text(page)
        _raise_for_gate_url(page.url)
        _raise_for_gate_text(body_text)
        if "search_result" in urlparse(page.url).path:
            return
        with contextlib.suppress(Exception):
            await page.wait_for_load_state("domcontentloaded", timeout=1_000)
        await _random_page_wait(page, 0.4, 1.0)
    raise RuntimeError("xhs home search did not reach search results")


async def _search_result_card_count(page: Any) -> int:
    try:
        return int(
            await page.locator(
                "section.note-item, section[data-index], "
                'a[href*="/search_result/"], a[href*="/explore/"]'
            ).count()
        )
    except Exception:
        return 0


def _quote_powershell_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _minimize_chrome_windows_for_profile(profile_dir: str) -> None:
    """Best-effort Windows focus guard for headed persistent Playwright runs."""
    if os.name != "nt":
        return

    profile_literal = _quote_powershell_string(profile_dir)
    script = f"""
$sig = @'
using System;
using System.Runtime.InteropServices;
public static class Win32Window {{
  [DllImport("user32.dll")]
  public static extern bool ShowWindowAsync(IntPtr hWnd, int nCmdShow);
}}
'@
Add-Type -TypeDefinition $sig -ErrorAction SilentlyContinue
$profile = {profile_literal}
$pattern = '*' + [System.Management.Automation.WildcardPattern]::Escape($profile) + '*'
Get-CimInstance Win32_Process | Where-Object {{ $_.Name -eq 'chrome.exe' -and $_.CommandLine -like $pattern }} | ForEach-Object {{
  $p = Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue
  if ($p -and $p.MainWindowHandle -ne 0) {{
    [Win32Window]::ShowWindowAsync($p.MainWindowHandle, 6) | Out-Null
  }}
}}
"""
    try:
        subprocess.run(  # noqa: S603 - fixed local PowerShell helper for headed diagnostics.
            [
                _powershell_executable(),
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                script,
            ],
            check=False,
            capture_output=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            text=True,
            timeout=5,
        )
    except Exception as exc:  # pragma: no cover - local Windows best effort
        logger.debug("xhs_window_minimize_failed", error=str(exc))


def _powershell_executable() -> str:
    system_root = os.environ.get("SYSTEMROOT", r"C:\Windows")
    bundled = Path(system_root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    if bundled.exists():
        return str(bundled)
    return shutil.which("powershell.exe") or "powershell.exe"


def _resolved_profile_path(profile_dir: str) -> str:
    return str(Path(profile_dir).expanduser().resolve())


async def _maybe_minimize_profile_window(profile_dir: str | None, *, delay_s: float = 0.0) -> None:
    if not profile_dir or _headless_for_fetch() or not _start_minimized_for_fetch():
        return
    if os.name != "nt":
        return
    if delay_s > 0:
        await asyncio.sleep(delay_s)
    profile_path = await asyncio.to_thread(_resolved_profile_path, profile_dir)
    await asyncio.to_thread(_minimize_chrome_windows_for_profile, profile_path)


def _raise_for_gate_text(body_text: str) -> None:
    if _has_public_search_gate_text(body_text):
        raise RuntimeError("xhs public search gate: search results are gated by XHS")
    if _has_verification_text(body_text):
        raise RuntimeError("xhs verification required: current browser session hit a safety check")
    if _XHS_NOT_FOUND_TEXT in body_text:
        raise RuntimeError("xhs search page not found for this device profile")


def _raise_for_gate_url(page_url: str) -> None:
    if _is_verification_url(page_url):
        raise RuntimeError("xhs verification required: current browser session hit a safety check")


def _has_login_wall_text(body_text: str) -> bool:
    return _has_public_search_gate_text(body_text)


def _has_public_search_gate_text(body_text: str) -> bool:
    return _XHS_PUBLIC_SEARCH_GATE_TEXT in body_text


def _has_verification_text(body_text: str) -> bool:
    return any(marker in body_text for marker in _XHS_VERIFY_TEXT_MARKERS)


def _is_verification_url(page_url: str) -> bool:
    parsed = urlparse(page_url)
    if (
        parsed.path in {"/website-login/error", "/website-login/captcha"}
        or "/captcha" in parsed.path
    ):
        return True
    decoded_url = unquote(page_url)
    return any(marker in decoded_url for marker in _XHS_VERIFY_TEXT_MARKERS)


def _is_gate_exception(exc: Exception) -> bool:
    text = str(exc).lower()
    return (
        "verification required" in text
        or "public search gate" in text
        or "login wall" in text  # Historical error text; keep old reports/caches readable.
        or "safety check" in text
    )


def _context_kwargs(
    *,
    user_agent: str,
    storage_state_path: str | None,
    device_profile: str,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "user_agent": user_agent,
        "locale": "zh-CN",
        "timezone_id": "Asia/Shanghai",
    }
    if device_profile == "mobile":
        kwargs.update(
            {
                "viewport": {"width": 390, "height": 844},
                "screen": {"width": 390, "height": 844},
                "device_scale_factor": 3,
                "is_mobile": True,
                "has_touch": True,
            }
        )
    if storage_state_path:
        kwargs["storage_state"] = storage_state_path
    return kwargs


def _browser_launch_kwargs(*, headless: bool | None = None) -> dict[str, Any]:
    resolved_headless = _headless_for_fetch() if headless is None else headless
    kwargs: dict[str, Any] = {"headless": resolved_headless}
    channel = os.getenv("XHS_BROWSER_CHANNEL", "").strip()
    if channel:
        kwargs["channel"] = channel
    if _start_minimized_for_fetch() and not resolved_headless:
        kwargs["args"] = ["--start-minimized"]
    return kwargs


def _ensure_profile_path(profile_dir: str) -> tuple[Path, str]:
    profile_path = Path(profile_dir).expanduser()
    profile_path.mkdir(parents=True, exist_ok=True)
    return profile_path, str(profile_path.resolve())


async def _get_browser() -> Any:
    """Lazily start Playwright + Chromium. Reused across calls."""
    global _atexit_registered  # noqa: PLW0603
    async with _browser_lock:
        if _browser_slot[0] is not None:
            return _browser_slot[0]
        # Local import: keeps fixture-mode imports free of Playwright cost
        # and lets unit tests stub ``fetch`` without playwright installed.
        if _pw_ctx_slot[0] is None:
            from playwright.async_api import async_playwright  # noqa: PLC0415

            _pw_ctx_slot[0] = await async_playwright().start()
        _browser_slot[0] = await _pw_ctx_slot[0].chromium.launch(**_browser_launch_kwargs())
        if not _atexit_registered:
            atexit.register(_atexit_close)
            _atexit_registered = True
        return _browser_slot[0]


async def _get_persistent_context(
    *,
    profile_dir: str,
    user_agent: str,
    device_profile: str,
) -> Any:
    """Return the shared persistent XHS browser context for ``profile_dir``."""
    global _atexit_registered  # noqa: PLW0603
    profile_path, profile_key = _ensure_profile_path(profile_dir)
    async with _persistent_context_lock:
        if (
            _persistent_context_slot[0] is not None
            and _persistent_profile_dir_slot[0] == profile_key
        ):
            return _persistent_context_slot[0]

        if _persistent_context_slot[0] is not None:
            with contextlib.suppress(Exception):
                await _persistent_context_slot[0].close()
            _persistent_context_slot[0] = None
            _persistent_profile_dir_slot[0] = None

        if _pw_ctx_slot[0] is None:
            from playwright.async_api import async_playwright  # noqa: PLC0415

            _pw_ctx_slot[0] = await async_playwright().start()
        _persistent_context_slot[0] = await _pw_ctx_slot[0].chromium.launch_persistent_context(
            profile_path,
            **_browser_launch_kwargs(),
            **_context_kwargs(
                user_agent=user_agent,
                storage_state_path=None,
                device_profile=device_profile,
            ),
        )
        await _maybe_minimize_profile_window(profile_key, delay_s=0.2)
        _persistent_profile_dir_slot[0] = profile_key
        if not _atexit_registered:
            atexit.register(_atexit_close)
            _atexit_registered = True
        return _persistent_context_slot[0]


async def _open_scrape_context(
    *,
    user_agent: str,
    storage_state_path: str | None,
    profile_dir: str | None,
    device_profile: str,
) -> tuple[Any, bool]:
    """Return ``(context, should_close_context)`` for one scrape attempt."""
    if profile_dir:
        context = await _get_persistent_context(
            profile_dir=profile_dir,
            user_agent=user_agent,
            device_profile=device_profile,
        )
        return context, False

    browser = await _get_browser()
    context = await browser.new_context(
        **_context_kwargs(
            user_agent=user_agent,
            storage_state_path=storage_state_path,
            device_profile=device_profile,
        )
    )
    return context, True


def _atexit_close() -> None:
    """Best-effort cleanup on interpreter shutdown.

    Schedules the async ``close`` on a fresh loop because by atexit the
    original loop is gone. Swallows everything — a noisy shutdown is
    worse than a quiet one.
    """
    with contextlib.suppress(Exception):
        asyncio.run(_aclose())


async def _aclose() -> None:
    if _persistent_context_slot[0] is not None:
        with contextlib.suppress(Exception):
            await _persistent_context_slot[0].close()
        _persistent_context_slot[0] = None
        _persistent_profile_dir_slot[0] = None
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
    limit: int,
    cookie: str | None = None,
    storage_state_path: str | None = None,
    profile_dir: str | None = None,
    user_agent: str | None = None,
    timeout_s: float = 30.0,
    cache_images: bool = False,
    images_per_post: int = 3,
) -> FetchResult:
    """Scrape XHS search results for ``query``.

    Raises on hard failure (timeout, persistent 429, captcha-like
    response). The caller is responsible for falling back to tier 2 /
    tier 3 on exception.

    v1 implementation note: the exact DOM-scraping logic is intentionally
    minimal. We navigate to the search URL, wait for a note card or public
    search gate, parse anchors that match note-detail URLs, then best-effort open
    each note detail page to fill body/images/counts. Search cards expose a
    hidden ``/explore/<id>`` URL and a visible ``/search_result/<id>`` URL with
    the ``xsec_token`` required by the detail route; we keep the tokenized URL
    for enrichment. If XHS changes their markup the unit tests still mock this
    function, but a manual dev test will surface the breakage as "tier 1
    returned 0 posts -> tier 2 / tier 3".
    """
    device_profile = _device_profile_for_fetch(profile_dir)
    ua = pick_user_agent(user_agent, device_profile=device_profile)

    last_exc: Exception | None = None
    for attempt in range(1, _MAX_RETRIES + 1):
        page: Any | None = None
        context: Any | None = None
        close_context = True
        try:
            context, close_context = await _open_scrape_context(
                user_agent=ua,
                storage_state_path=storage_state_path,
                profile_dir=profile_dir,
                device_profile=device_profile,
            )
            # Inject the cookie blob. We accept opaque cookie strings of
            # either "k=v; k2=v2" form (browser cookie header) or a JSON
            # list of cookie dicts. Anything else: best-effort, log and
            # try to navigate anyway — XHS may still gate via JS.
            if cookie and not profile_dir:
                await _inject_cookie(context, cookie)
            page = await context.new_page()
            await _maybe_minimize_profile_window(profile_dir, delay_s=0.1)
            page.set_default_timeout(int(timeout_s * 1000))
            page.set_default_navigation_timeout(int(timeout_s * 1000))

            status = await _goto_xhs_search(
                page,
                query,
                timeout_s=timeout_s,
                profile_dir=profile_dir,
            )
            await _maybe_minimize_profile_window(profile_dir, delay_s=0.05)

            if status == _HTTP_TOO_MANY_REQUESTS:
                logger.warning("xhs_rate_limited", attempt=attempt, status=status, query=query)
                if attempt == _MAX_RETRIES:
                    raise RuntimeError(f"xhs rate limited after {attempt} attempts")
                # Exponential backoff with jitter.
                jitter = secrets.randbelow(1000) / 1000.0
                await asyncio.sleep(_BACKOFF_BASE_S * (2 ** (attempt - 1)) + jitter)
                continue

            if status >= _HTTP_CLIENT_ERROR_FLOOR:
                raise RuntimeError(f"xhs returned http {status}")

            await _search_page_dwell(page, profile_dir)
            body_text = await _page_body_text(page)
            _raise_for_gate_url(page.url)
            _raise_for_gate_text(body_text)

            # Best-effort DOM extraction. Schema is documented in
            # ``XHSPost``.
            posts = await _scrape_search_posts(page, limit, timeout_s)
            posts = await _maybe_enrich_posts_from_details(
                context,
                list(posts)[:limit],
                timeout_s,
                profile_dir=profile_dir,
            )
            if cache_images:
                posts = await _cache_post_images_with_context(
                    context,
                    list(posts)[:limit],
                    images_per_post=images_per_post,
                    timeout_s=timeout_s,
                )
            return FetchResult(posts=list(posts)[:limit])

        except Exception as exc:
            last_exc = exc
            # Only 429s get retried (handled via ``continue`` above);
            # any other failure bails immediately so the
            # tier-2/tier-3 fallback isn't blocked on a long retry.
            raise
        finally:
            if page is not None:
                with contextlib.suppress(Exception):
                    await page.close()
            if close_context and context is not None:
                with contextlib.suppress(Exception):
                    await context.close()

    # Loop fell through only via 429 path; re-raise the last seen.
    raise RuntimeError(f"xhs fetch exhausted retries: {last_exc!r}")


async def _inject_cookie(context: Any, cookie: str) -> None:
    """Best-effort cookie injection.

    Accepts either a raw header-style cookie string (``a=b; c=d``), a
    JSON browser-cookie dict/list, or ``{"cookies": [...]}``.
    Caller-controlled string; failures are logged and swallowed (the
    navigation might still succeed for queries that are not publicly gated).
    """
    cookies = _parse_cookie_blob(cookie)
    if not cookies:
        logger.warning("xhs_cookie_empty_after_parse")
        return
    try:
        await context.add_cookies(cookies)
    except Exception as exc:
        logger.warning("xhs_cookie_inject_failed", error=str(exc))


async def _page_body_text(page: Any) -> str:
    """Read body text across XHS client redirects without failing the scrape."""
    last_exc: Exception | None = None
    for _ in range(3):
        try:
            return str(await page.evaluate("() => document.body && document.body.innerText || ''"))
        except Exception as exc:
            last_exc = exc
            with contextlib.suppress(Exception):
                await page.wait_for_load_state("domcontentloaded", timeout=2000)
            await asyncio.sleep(0.2)
    raise RuntimeError(f"xhs body text unavailable after navigation: {last_exc}")


async def _scrape_search_posts(page: Any, limit: int, timeout_s: float) -> list[dict[str, Any]]:
    """Wait for XHS' lazy card grid, then parse posts after reader-like scrolling."""
    deadline = asyncio.get_running_loop().time() + min(timeout_s, 12.0)
    posts: list[dict[str, Any]] = []
    scrolls_remaining = max(0, _int_env("XHS_SEARCH_SCROLLS", 2))
    while asyncio.get_running_loop().time() < deadline:
        with contextlib.suppress(Exception):
            await page.wait_for_function(
                """
                () => document.querySelector('section.note-item, section[data-index], a[href*="/search_result/"], a[href*="/explore/"]')
                   || document.body.innerText.includes('登录后查看搜索结果')
                   || document.body.innerText.includes('扫码')
                """,
                timeout=min(
                    int(max(deadline - asyncio.get_running_loop().time(), 0.5) * 1000), 3000
                ),
            )
        body_text = await _page_body_text(page)
        _raise_for_gate_url(page.url)
        _raise_for_gate_text(body_text)

        await _wait_for_lazy_content_images(page, min_images=1, timeout_s=1.5)
        raw = await page.evaluate(_SCRAPE_JS, limit)
        posts = list(raw)[:limit]
        posts_with_images = [post for post in posts if post.get("images")]
        if len(posts) >= limit and posts_with_images:
            return posts

        if scrolls_remaining <= 0:
            return posts
        scrolls_remaining -= 1
        await _human_mouse_pause(page)
        await _human_scroll_page(page)
    return posts


def _parse_cookie_blob(cookie: str) -> list[dict[str, Any]]:
    raw = cookie.strip()
    if not raw:
        return []
    if raw.lower().startswith("cookie:"):
        raw = raw.partition(":")[2].strip()
    if raw.startswith("[") or raw.startswith("{"):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.warning("xhs_cookie_json_decode_failed", error=str(exc))
            return []
        source = parsed.get("cookies", parsed) if isinstance(parsed, dict) else parsed
        if isinstance(source, dict):
            source = [source]
        if isinstance(source, list):
            parsed_cookies = [
                _normalise_cookie_dict(item) for item in source if isinstance(item, dict)
            ]
            return [item for item in parsed_cookies if item]
        return []

    cookies: list[dict[str, Any]] = []
    for piece in raw.split(";"):
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
    return cookies


def _normalise_cookie_dict(item: dict[str, Any]) -> dict[str, Any]:
    name = str(item.get("name") or "")
    value = str(item.get("value") or "")
    if not name:
        return {}
    return {
        "name": name,
        "value": value,
        "domain": str(item.get("domain") or ".xiaohongshu.com"),
        "path": str(item.get("path") or "/"),
    }


async def _enrich_posts_from_details(
    context: Any,
    posts: list[dict[str, Any]],
    timeout_s: float,
    *,
    profile_dir: str | None = None,
) -> list[dict[str, Any]]:
    """Best-effort enrich search-card hits by opening note detail pages."""
    enriched: list[dict[str, Any]] = []
    detail_timeout_ms = min(int(timeout_s * 1000), 8000)
    for index, post in enumerate(posts):
        url = str(post.get("url") or "")
        if not url:
            enriched.append(post)
            continue
        detail_page = await context.new_page()
        await _maybe_minimize_profile_window(profile_dir, delay_s=0.05)
        try:
            detail_page.set_default_timeout(detail_timeout_ms)
            detail_page.set_default_navigation_timeout(detail_timeout_ms)
            response = await detail_page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=detail_timeout_ms,
            )
            await _maybe_minimize_profile_window(profile_dir, delay_s=0.05)
            status = response.status if response is not None else 0
            if status >= _HTTP_CLIENT_ERROR_FLOOR:
                raise RuntimeError(f"xhs detail returned http {status}")
            await _detail_page_dwell(detail_page, profile_dir)
            await _human_mouse_pause(detail_page)
            if os.getenv("XHS_DETAIL_SCROLL", "1").strip().lower() not in {"0", "false", "no"}:
                await _human_scroll_page(detail_page)
            await _wait_for_lazy_content_images(detail_page, min_images=1, timeout_s=2.5)
            with contextlib.suppress(Exception):
                await detail_page.wait_for_function(
                    r"""
                    () => {
                      const visible = document.body && document.body.innerText || '';
                      const textReady = document.querySelector('#detail-title, [class*=note-content]');
                      const imageReady = Array.from(
                        document.querySelectorAll('meta[property="og:image"], img, source')
                      ).some((el) => {
                        const values = ['content', 'src', 'data-src', 'currentSrc', 'srcset']
                          .map((attr) => el.getAttribute(attr) || el[attr] || '')
                          .flatMap((raw) => String(raw).split(',').map((part) => part.trim().split(/\s+/)[0]));
                        return values.some((src) => /xhscdn\.com/i.test(src) && !/avatar/i.test(src));
                      });
                      return (textReady && imageReady)
                        || visible.includes('登录')
                        || visible.includes('扫码');
                    }
                    """,
                    timeout=detail_timeout_ms,
                )
            detail = await _evaluate_detail_with_retry(detail_page, detail_timeout_ms)
            enriched.append(_merge_detail(post, detail))
        except Exception as exc:
            logger.warning(
                "xhs_detail_enrich_failed",
                post_id=post.get("id"),
                url=url,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            enriched.append(post)
        finally:
            with contextlib.suppress(Exception):
                await detail_page.close()
        if index < len(posts) - 1:
            await _detail_gap_sleep()
    return enriched


async def _evaluate_detail_with_retry(page: Any, timeout_ms: int) -> Any:
    last_exc: Exception | None = None
    for attempt in range(_DETAIL_EVALUATE_RETRIES):
        try:
            return await page.evaluate(_DETAIL_SCRAPE_JS)
        except Exception as exc:
            last_exc = exc
            is_last_attempt = attempt == _DETAIL_EVALUATE_RETRIES - 1
            if not _is_navigation_interrupted_evaluate(exc) or is_last_attempt:
                raise
            with contextlib.suppress(Exception):
                await page.wait_for_load_state("domcontentloaded", timeout=min(timeout_ms, 2000))
            with contextlib.suppress(Exception):
                await page.wait_for_timeout(250 + attempt * 250)
    raise RuntimeError(f"xhs detail evaluate unavailable after navigation: {last_exc}")


def _is_navigation_interrupted_evaluate(exc: Exception) -> bool:
    text = str(exc).casefold()
    return any(marker in text for marker in _NAVIGATION_INTERRUPTED_EVALUATE_MARKERS)


async def _maybe_enrich_posts_from_details(
    context: Any,
    posts: list[dict[str, Any]],
    timeout_s: float,
    *,
    profile_dir: str | None = None,
) -> list[dict[str, Any]]:
    if os.getenv("XHS_DETAIL_ENRICH", "1").strip().lower() in {"0", "false", "no"}:
        return posts
    try:
        max_posts = max(0, int(os.getenv("XHS_DETAIL_ENRICH_LIMIT", "2")))
    except ValueError:
        max_posts = 2
    if max_posts <= 0:
        return posts
    head = posts[:max_posts]
    tail = posts[max_posts:]
    enriched = await _enrich_posts_from_details(
        context,
        head,
        min(timeout_s, _float_env("XHS_DETAIL_TIMEOUT_S", 12.0)),
        profile_dir=profile_dir,
    )
    return [*enriched, *tail]


async def _cache_post_images_with_context(
    context: Any,
    posts: list[dict[str, Any]],
    *,
    images_per_post: int,
    timeout_s: float,
) -> list[dict[str, Any]]:
    """Download XHS note images through the active browser context.

    The DB cache stores app-served ``/media/...`` URLs in ``images`` and
    preserves original CDN URLs under ``source_images`` for traceability.
    """
    if images_per_post <= 0:
        return posts

    cached_posts: list[dict[str, Any]] = []
    for post in posts:
        source_images = _clean_content_images(post.get("images"))
        cached_images: list[dict[str, Any]] = []
        display_images: list[str] = []
        for source_url in source_images[:images_per_post]:
            cached = await _cache_one_image_with_context(context, source_url, timeout_s=timeout_s)
            if cached is None:
                continue
            cached_images.append(cached)
            display_images.append(str(cached["url"]))

        updated = dict(post)
        updated["source_images"] = source_images
        updated["cached_images"] = cached_images
        updated["images"] = display_images
        cached_posts.append(updated)
    return cached_posts


async def _cache_one_image_with_context(
    context: Any,
    source_url: str,
    *,
    timeout_s: float,
) -> dict[str, Any] | None:
    if not _is_likely_xhs_content_image(source_url):
        return None

    digest = hashlib.sha256(source_url.encode("utf-8")).hexdigest()
    base_dir = settings.media_dir / "xhs" / digest[:2]
    base_dir.mkdir(parents=True, exist_ok=True)

    existing = next(base_dir.glob(f"{digest}.*"), None)
    if existing is not None:
        return _cached_image_record(
            source_url=source_url,
            path=existing,
            byte_count=existing.stat().st_size,
            content_type=_content_type_from_suffix(existing.suffix),
        )

    downloaded = await _download_image_with_context(context, source_url, timeout_s=timeout_s)
    if downloaded is None:
        return None
    content, content_type, ext = downloaded

    if not content or len(content) > _XHS_MAX_IMAGE_BYTES:
        return None

    path = base_dir / f"{digest}{ext}"
    path.write_bytes(content)
    return _cached_image_record(
        source_url=source_url,
        path=path,
        byte_count=len(content),
        content_type=content_type or _content_type_from_suffix(ext),
    )


async def _download_image_with_context(
    context: Any,
    source_url: str,
    *,
    timeout_s: float,
) -> tuple[bytes, str, str] | None:
    try:
        response = await context.request.get(
            source_url,
            headers={
                "Referer": "https://www.xiaohongshu.com/",
                "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            },
            timeout=max(1000, int(timeout_s * 1000)),
        )
        content_type = (
            str(response.headers.get("content-type", "")).split(";", 1)[0].lower().strip()
        )
        ext = _XHS_IMAGE_EXT_BY_TYPE.get(content_type) or _image_ext_from_url(source_url)
        if (
            not response.ok
            or ext is None
            or _content_length_too_large(response.headers.get("content-length"))
        ):
            return None
        return await response.body(), content_type, ext
    except Exception as exc:
        logger.warning(
            "xhs_image_cache_failed",
            host=urlparse(source_url).netloc,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return None


def _cached_image_record(
    *,
    source_url: str,
    path: Path,
    byte_count: int,
    content_type: str,
) -> dict[str, Any]:
    return {
        "source_url": source_url,
        "url": _media_url(path),
        "bytes": byte_count,
        "content_type": content_type,
        "fetched_at": _now_iso(),
    }


def _content_length_too_large(raw: str | None) -> bool:
    if not raw:
        return False
    try:
        return int(raw) > _XHS_MAX_IMAGE_BYTES
    except ValueError:
        return False


def _image_ext_from_url(source_url: str) -> str | None:
    lowered = urlparse(source_url).path.lower()
    if ".jpg" in lowered or ".jpeg" in lowered:
        return ".jpg"
    if ".png" in lowered:
        return ".png"
    if ".webp" in lowered or "!webp" in lowered:
        return ".webp"
    if ".gif" in lowered:
        return ".gif"
    return None


def _media_url(path: Path) -> str:
    rel = path.resolve().relative_to(settings.media_dir.resolve()).as_posix()
    return f"/media/{rel}"


def _content_type_from_suffix(suffix: str) -> str:
    for content_type, ext in _XHS_IMAGE_EXT_BY_TYPE.items():
        if suffix.lower() == ext:
            return content_type
    return "application/octet-stream"


def _now_iso() -> str:
    from datetime import UTC, datetime  # noqa: PLC0415

    return datetime.now(UTC).isoformat()


def _merge_detail(post: dict[str, Any], detail: Any) -> dict[str, Any]:
    if not isinstance(detail, dict):
        return post
    detail_url = detail.get("url")
    if isinstance(detail_url, str) and not _is_xhs_note_url(detail_url):
        return post
    if isinstance(detail_url, str) and not _same_xhs_note(post, detail_url):
        return post
    merged = dict(post)
    for key in ("author", "title", "body"):
        value = detail.get(key)
        if isinstance(value, str) and value.strip():
            merged[key] = value.strip()
    if isinstance(detail_url, str) and detail_url.strip():
        merged["url"] = _canonicalise_xhs_note_url(detail_url.strip())
    else:
        merged["url"] = _canonicalise_xhs_note_url(str(post.get("url") or ""))
    merged.pop("xhs_index_stub", None)
    for key in ("likes", "comments"):
        value = detail.get(key)
        if isinstance(value, int) and value >= 0:
            merged[key] = value
    clean_images = _clean_content_images(detail.get("images"), post.get("images"))
    if clean_images:
        merged["images"] = clean_images[:8]
    return merged


def _is_xhs_note_url(url: str) -> bool:
    parsed = urlparse(url)
    if "xiaohongshu.com" not in parsed.netloc:
        return False
    return any(marker in parsed.path for marker in _XHS_NOTE_PATH_MARKERS)


def _same_xhs_note(post: dict[str, Any], detail_url: str) -> bool:
    detail_id = _xhs_note_id_from_url(detail_url)
    if not detail_id:
        return False
    post_id = str(post.get("id") or "").strip()
    if post_id and post_id == detail_id:
        return True
    return _xhs_note_id_from_url(str(post.get("url") or "")) == detail_id


def _xhs_note_id_from_url(url: str) -> str:
    parsed = urlparse(url)
    if "xiaohongshu.com" not in parsed.netloc:
        return ""
    parts = [part for part in parsed.path.split("/") if part]
    for marker in ("explore", "search_result", "item"):
        if marker in parts:
            index = parts.index(marker)
            if index + 1 < len(parts):
                return parts[index + 1]
    return ""


def _canonicalise_xhs_note_url(url: str) -> str:
    parsed = urlparse(url)
    if "xiaohongshu.com" not in parsed.netloc or "/search_result/" not in parsed.path:
        return url
    return parsed._replace(path=parsed.path.replace("/search_result/", "/explore/", 1)).geturl()


def _is_likely_xhs_content_image(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    lowered = url.lower()
    if any(marker in lowered for marker in ("avatar", "favicon", "icon", "logo")):
        return False
    host = parsed.netloc.lower()
    if host.startswith("fe-platform.") and parsed.path.startswith("/platform/"):
        return False
    return "xhscdn.com" in host or (
        host.endswith(".xiaohongshu.com") and parsed.path.startswith("/discovery/")
    )


def _clean_content_images(*sources: Any) -> list[str]:
    images: list[str] = []
    for source in sources:
        if not isinstance(source, list | tuple):
            continue
        for item in source:
            if not isinstance(item, str) or not _is_likely_xhs_content_image(item):
                continue
            if item not in images:
                images.append(item)
    return images


# Kept as a module constant so a future test could swap it without
# touching ``fetch``. Returns a list of {id, author, title, body,
# likes, comments, url, images} dicts matching ``XHSPost`` field names.
_SCRAPE_JS = r"""
(limit) => {
  const out = [];
  const seen = new Set();
  const parseNoteHref = (href) => {
    const raw = String(href || '');
    const match = raw.match(/\/(?:explore|search_result)\/([a-z0-9]+)/i);
    if (!match) return null;
    return {
      id: match[1],
      url: new URL(raw, 'https://www.xiaohongshu.com').toString(),
      hasToken: raw.includes('xsec_token='),
      isSearchResult: raw.includes('/search_result/'),
    };
  };
  const visibleEnough = (el) => {
    const rect = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
  };
  const parseCount = (raw) => {
    const text = String(raw || '').replace(/,/g, '').trim().toLowerCase();
    const match = text.match(/(\d+(?:\.\d+)?)/);
    if (!match) return 0;
    const value = Number(match[1]);
    if (!Number.isFinite(value)) return 0;
    if (text.includes('万')) return Math.round(value * 10000);
    if (text.includes('k')) return Math.round(value * 1000);
    return Math.round(value);
  };
  const cards = Array.from(document.querySelectorAll('section.note-item, section[data-index], section'));
  for (const card of cards) {
    if (out.length >= limit) break;
    const anchors = Array.from(
      card.querySelectorAll('a[href*="/explore/"], a[href*="/search_result/"]')
    );
    const candidates = anchors
      .map((anchor) => ({anchor, parsed: parseNoteHref(anchor.getAttribute('href'))}))
      .filter((item) => item.parsed);
    if (!candidates.length) continue;
    candidates.sort((a, b) => {
      const aScore = (visibleEnough(a.anchor) ? 4 : 0)
        + (a.parsed.hasToken ? 2 : 0)
        + (a.parsed.isSearchResult ? 1 : 0);
      const bScore = (visibleEnough(b.anchor) ? 4 : 0)
        + (b.parsed.hasToken ? 2 : 0)
        + (b.parsed.isSearchResult ? 1 : 0);
      return bScore - aScore;
    });
    const best = candidates[0].parsed;
    const id = best.id;
    if (seen.has(id)) continue;
    seen.add(id);
    const titleEl = card.querySelector('.title, [class*="title"]');
    const authorEl = card.querySelector('[class*="author"], [class*="user"]');
    const likeEl = card.querySelector('[class*="like"], [class*="count"]');
    const imageEl = card.querySelector('img[data-xhs-img], img:not(.author-avatar)');
    const imageSrc = imageEl && (imageEl.currentSrc || imageEl.src || imageEl.getAttribute('data-src')) || '';
    out.push({
      id: id,
      author: (authorEl && authorEl.textContent || '').trim() || 'unknown',
      title: (titleEl && titleEl.textContent || '').trim() || '',
      body: '',
      likes: parseCount(likeEl && likeEl.textContent),
      comments: 0,
      url: best.url,
      images: /^https?:\/\//.test(imageSrc) ? [imageSrc] : [],
    });
  }
  return out;
}
"""


_DETAIL_SCRAPE_JS = r"""
() => {
  const textOf = (selectors) => {
    for (const selector of selectors) {
      const el = document.querySelector(selector);
      const text = (el && el.textContent || '').trim();
      if (text) return text;
    }
    return '';
  };
  const parseCount = (raw) => {
    const text = String(raw || '').replace(/,/g, '').trim().toLowerCase();
    const match = text.match(/(\d+(?:\.\d+)?)/);
    if (!match) return 0;
    const value = Number(match[1]);
    if (!Number.isFinite(value)) return 0;
    if (text.includes('万')) return Math.round(value * 10000);
    if (text.includes('k')) return Math.round(value * 1000);
    return Math.round(value);
  };
  const metaContent = (selector) => {
    const el = document.querySelector(selector);
    return (el && el.getAttribute('content') || '').trim();
  };
  const isContentImage = (src) => {
    const text = String(src || '').toLowerCase();
    return /^https?:\/\//.test(text)
      && text.includes('xhscdn.com')
      && !/(avatar|favicon|icon|logo)/.test(text);
  };
  const imageValues = (el) => {
    const values = [];
    for (const attr of ['content', 'src', 'data-src', 'currentSrc', 'srcset']) {
      const raw = el.getAttribute(attr) || el[attr] || '';
      if (raw) values.push(String(raw));
    }
    return values.flatMap((raw) => String(raw).split(',').map((part) => part.trim().split(/\s+/)[0]));
  };
  const title = textOf([
    '#detail-title',
    '[class*="title"]',
  ]) || metaContent('meta[property="og:title"]');
  const body = textOf([
    '#detail-desc',
    '[class*="note-content"]',
    '[class*="desc"]',
    '[class*="content"]',
  ]) || metaContent('meta[name="description"]') || metaContent('meta[property="og:description"]');
  const author = textOf([
    '[class*="author"] [class*="name"]',
    '[class*="user"] [class*="name"]',
    '[class*="nickname"]',
    '[class*="author"]',
  ]);
  const images = Array.from(document.querySelectorAll('meta[property="og:image"], img, source'))
    .flatMap(imageValues)
    .filter(isContentImage)
    .filter((src, index, all) => all.indexOf(src) === index)
    .slice(0, 8);
  const visible = document.body && document.body.innerText || '';
  const likeMatch = visible.match(/(?:赞|点赞|喜欢)\s*([\d.,]+\s*(?:万|k)?)/i);
  const commentMatch = visible.match(/(?:评论)\s*([\d.,]+\s*(?:万|k)?)/i);
  return {
    author,
    title,
    body,
    likes: parseCount(likeMatch && likeMatch[1]),
    comments: parseCount(commentMatch && commentMatch[1]),
    url: location.href,
    images,
  };
}
"""
