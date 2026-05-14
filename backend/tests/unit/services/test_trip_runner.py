"""Tests for trip_runner — pub/sub queue + status flips.

Doesn't run the real cycle (that's covered in agents tests + future
integration tests); exercises the subscribe / publish / EOF mechanics
that the SSE handler depends on.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from plus_one.services.trip_runner import _drop_queue, _publish, subscribe


@pytest.mark.unit
async def test_subscribe_yields_events_in_order() -> None:
    trip_id = uuid4()

    async def producer() -> None:
        await _publish(trip_id, {"name": "started"})
        await _publish(trip_id, {"name": "producer", "depth": 0})
        await _publish(trip_id, {"name": "_eof"})

    task = asyncio.create_task(producer())
    received: list[str] = []
    async for event in subscribe(trip_id):
        received.append(event["name"])  # type: ignore[arg-type]
    await task  # ensure producer completed cleanly
    assert received == ["started", "producer"]
    _drop_queue(trip_id)


@pytest.mark.unit
async def test_subscribe_drops_after_eof() -> None:
    """Iterator must complete cleanly on the EOF sentinel."""
    trip_id = uuid4()

    await _publish(trip_id, {"name": "_eof"})
    received = [event async for event in subscribe(trip_id)]
    assert received == []
    _drop_queue(trip_id)
