"""Unit tests for the in-process rate limiters (batch-2m)."""

from __future__ import annotations

import asyncio

import pytest

from plus_one.core.auth.rate_limit import MinIntervalLimiter, TokenBucket


@pytest.mark.unit
async def test_min_interval_limiter_first_call_allowed() -> None:
    limiter = MinIntervalLimiter(min_interval_seconds=0.1)
    assert await limiter.allow("a") is True


@pytest.mark.unit
async def test_min_interval_limiter_second_call_blocked() -> None:
    limiter = MinIntervalLimiter(min_interval_seconds=10.0)
    assert await limiter.allow("a") is True
    assert await limiter.allow("a") is False


@pytest.mark.unit
async def test_min_interval_limiter_unblocks_after_interval() -> None:
    limiter = MinIntervalLimiter(min_interval_seconds=0.05)
    assert await limiter.allow("a") is True
    await asyncio.sleep(0.07)
    assert await limiter.allow("a") is True


@pytest.mark.unit
async def test_min_interval_limiter_per_key_isolation() -> None:
    limiter = MinIntervalLimiter(min_interval_seconds=10.0)
    assert await limiter.allow("a") is True
    assert await limiter.allow("b") is True
    assert await limiter.allow("a") is False


@pytest.mark.unit
async def test_token_bucket_admits_up_to_max() -> None:
    bucket = TokenBucket(max_calls=3, window_seconds=10.0)
    assert [await bucket.allow("u") for _ in range(3)] == [True, True, True]
    assert await bucket.allow("u") is False
