"""Tests for trip_runner — pub/sub queue + status flips.

Doesn't run the real cycle (that's covered in agents tests + future
integration tests); exercises the subscribe / publish / EOF mechanics
that the SSE handler depends on.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from plus_one.services.trip_runner import (
    _drop_queue,
    _publish,
    register,
    subscribe,
)


@pytest.mark.unit
async def test_subscribe_yields_events_in_order() -> None:
    trip_id = uuid4()
    register(trip_id)

    async def producer() -> None:
        await _publish(trip_id, {"name": "started"})
        await _publish(trip_id, {"name": "producer", "depth": 0})
        await _publish(trip_id, {"name": "_eof"})

    task = asyncio.create_task(producer())
    received: list[str] = []
    async for event in subscribe(trip_id):
        received.append(event["name"])  # type: ignore[arg-type]
    await task
    assert received == ["started", "producer"]
    _drop_queue(trip_id)


@pytest.mark.unit
async def test_subscribe_drops_after_eof() -> None:
    """Iterator must complete cleanly on the EOF sentinel."""
    trip_id = uuid4()
    register(trip_id)

    await _publish(trip_id, {"name": "_eof"})
    received = [event async for event in subscribe(trip_id)]
    assert received == []
    _drop_queue(trip_id)


@pytest.mark.unit
async def test_subscribe_to_unknown_trip_returns_immediately() -> None:
    """Reviewer B1: a stale / replay subscribe to an unknown trip must
    NOT create an orphan queue. It should return immediately so the
    SSE handler closes cleanly."""
    trip_id = uuid4()  # never registered
    received = [event async for event in subscribe(trip_id)]
    assert received == []


@pytest.mark.unit
async def test_publish_to_unknown_trip_does_not_raise() -> None:
    """A late publish (queue already dropped) should be a no-op log,
    not an exception that takes down the runner."""
    trip_id = uuid4()  # not registered
    await _publish(trip_id, {"name": "anything"})  # must not raise


@pytest.mark.unit
async def test_register_is_idempotent() -> None:
    trip_id = uuid4()
    register(trip_id)
    register(trip_id)  # second call must not replace the queue
    await _publish(trip_id, {"name": "x"})
    await _publish(trip_id, {"name": "_eof"})
    received = [event async for event in subscribe(trip_id)]
    assert [e["name"] for e in received] == ["x"]
    _drop_queue(trip_id)
