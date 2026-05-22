"""In-process rate limiters (batch-2m).

Single-replica dev assumption. For multi-replica deployment, swap with
Redis-backed counters — same RateLimiter interface.

Two patterns:

  * :class:`MinIntervalLimiter` — "1 request per N seconds per key"
    (used for /api/auth/request-code: 1/60s per email).
  * :class:`TokenBucket` — "N requests per window per key" with sliding
    timestamps (used for /api/admin/logs/frontend: 50/sec per user).

Both are async-safe via a single asyncio.Lock; ok for dev scale.
"""

from __future__ import annotations

import asyncio
import collections
import time


class MinIntervalLimiter:
    """1 request per ``min_interval_seconds`` per key.

    :meth:`allow` returns True iff enough time has passed since this
    key's last allowed call. Otherwise returns False without recording —
    so callers can re-try later without polluting the timestamp.
    """

    def __init__(self, min_interval_seconds: float) -> None:
        self._interval = float(min_interval_seconds)
        self._last: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def allow(self, key: str) -> bool:
        now = time.monotonic()
        async with self._lock:
            prev = self._last.get(key)
            if prev is not None and (now - prev) < self._interval:
                return False
            self._last[key] = now
            return True

    def reset(self) -> None:
        """Test helper — drop all tracked keys."""
        self._last.clear()


class TokenBucket:
    """Sliding-window N requests per window per key.

    Stores per-key deques of monotonic timestamps. On each call, evict
    timestamps older than ``window_seconds`` then admit if the count is
    under ``max_calls``.
    """

    def __init__(self, max_calls: int, window_seconds: float) -> None:
        self._max = int(max_calls)
        self._window = float(window_seconds)
        self._hist: dict[str, collections.deque[float]] = {}
        self._lock = asyncio.Lock()

    async def allow(self, key: str) -> bool:
        now = time.monotonic()
        cutoff = now - self._window
        async with self._lock:
            dq = self._hist.get(key)
            if dq is None:
                dq = collections.deque()
                self._hist[key] = dq
            while dq and dq[0] < cutoff:
                dq.popleft()
            if len(dq) >= self._max:
                return False
            dq.append(now)
            return True

    def reset(self) -> None:
        self._hist.clear()
