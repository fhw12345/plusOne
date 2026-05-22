"""Admin-only routes — log live tail + frontend log push (batch-2m).

  GET  /api/admin/logs/stream    — SSE, replay last 1000 then live tail
  POST /api/admin/logs/frontend  — admins push browser console events
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Annotated, Literal

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    status,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from plus_one.core.auth.admin import RequireAdmin, RequireAdminSse
from plus_one.core.auth.rate_limit import TokenBucket
from plus_one.core.logs.buffer import (
    LogEntry,
    push,
    snapshot,
    subscribe,
    unsubscribe,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

router = APIRouter(prefix="/api/admin", tags=["admin"])
logger = logging.getLogger(__name__)


# Per-user 50 req/sec for the frontend log POST.
_FRONTEND_LOG_LIMITER = TokenBucket(max_calls=50, window_seconds=1.0)


def get_frontend_log_limiter() -> TokenBucket:
    return _FRONTEND_LOG_LIMITER


# === Schemas ==============================================================


class FrontendLogEntryIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ts: datetime
    level: Literal["log", "info", "warn", "error", "debug"]
    message: str = Field(min_length=1, max_length=2000)


class FrontendLogBatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entries: list[FrontendLogEntryIn] = Field(min_length=1, max_length=50)


_LEVEL_NORMALIZE = {
    "log": "INFO",
    "info": "INFO",
    "warn": "WARN",
    "error": "ERROR",
    "debug": "DEBUG",
}


# === SSE stream ===========================================================


def _format_event(entry: LogEntry) -> str:
    payload = json.dumps(
        {
            "ts": entry.ts.isoformat(),
            "level": entry.level,
            "source": entry.source,
            "message": entry.message,
            "logger": entry.logger,
        }
    )
    return f"event: log\ndata: {payload}\n\n"


@router.get(
    "/logs/stream",
    summary="SSE live-tail of the admin log ring buffer",
)
async def logs_stream(
    request: Request,
    user: RequireAdminSse,
) -> StreamingResponse:
    del user  # access check only

    async def event_generator() -> AsyncIterator[str]:
        queue = subscribe()
        try:
            for entry in snapshot():
                yield _format_event(entry)

            heartbeat = 15.0
            while True:
                if await request.is_disconnected():
                    return
                try:
                    entry = await asyncio.wait_for(queue.get(), timeout=heartbeat)
                except TimeoutError:
                    yield ": heartbeat\n\n"
                    continue
                yield _format_event(entry)
        except asyncio.CancelledError:
            logger.info("admin_logs_sse_disconnected")
            raise
        finally:
            unsubscribe(queue)

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    }
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers=headers,
    )


# === Frontend log push ====================================================

# 4 KB body limit per PRD §10.
_MAX_BODY_BYTES = 4 * 1024


@router.post(
    "/logs/frontend",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Admin-only: push a batch of browser console events to the ring",
)
async def post_frontend_logs(
    request: Request,
    user: RequireAdmin,
    limiter: Annotated[TokenBucket, Depends(get_frontend_log_limiter)],
) -> None:
    raw = await request.body()
    if len(raw) > _MAX_BODY_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="body_too_large",
        )

    try:
        data = json.loads(raw.decode("utf-8")) if raw else {}
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="invalid_json",
        ) from exc

    try:
        batch = FrontendLogBatchIn.model_validate(data)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="invalid_batch",
        ) from exc

    if not await limiter.allow(str(user.id)):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="rate_limited"
        )

    for entry in batch.entries:
        ts = entry.ts if entry.ts.tzinfo else entry.ts.replace(tzinfo=UTC)
        push(
            LogEntry(
                ts=ts,
                level=_LEVEL_NORMALIZE.get(entry.level, "INFO"),
                source="frontend",
                message=entry.message,
                logger=None,
            )
        )
