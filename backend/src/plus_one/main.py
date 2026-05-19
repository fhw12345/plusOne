"""FastAPI application entry point.

Minimal skeleton for now: just a /health endpoint. Routes will be added
in follow-up PRs as feature areas come online.
"""

from __future__ import annotations

import logging
import os
import re
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from plus_one import __version__
from plus_one.api.auth import router as auth_router
from plus_one.api.trips import router as trips_router
from plus_one.config import settings

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


_ACCESS_TOKEN_RE = re.compile(r"access_token=[^&\s\"]+")


class _ScrubAccessTokenFilter(logging.Filter):
    """Redact ``access_token=<jwt>`` from uvicorn access log lines.

    The SSE endpoint accepts the JWT via query param because EventSource
    cannot set headers; default uvicorn access-log format includes the
    full request line, which would otherwise expose the token in stdout.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str) and "access_token=" in record.msg:
            record.msg = _ACCESS_TOKEN_RE.sub("access_token=REDACTED", record.msg)
        if record.args:
            record.args = tuple(
                _ACCESS_TOKEN_RE.sub("access_token=REDACTED", a) if isinstance(a, str) else a
                for a in record.args
            )
        return True


def _install_access_log_scrubber() -> None:
    """Install the SSE-token scrubber on ``uvicorn.access`` (idempotent)."""
    access_logger = logging.getLogger("uvicorn.access")
    for existing in access_logger.filters:
        if isinstance(existing, _ScrubAccessTokenFilter):
            return
    access_logger.addFilter(_ScrubAccessTokenFilter())


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown hooks."""
    # Default to "real LLM allowed" so prod entry points satisfy the
    # MaestroProvider guard. Use ``setdefault`` so test harnesses
    # (Playwright e2e, etc.) can pre-export ``PLUS_ONE_ALLOW_REAL_LLM=0``
    # to force-fail provider construction and exercise the
    # ``cycle_aborted`` code path without hitting Maestro.
    os.environ.setdefault("PLUS_ONE_ALLOW_REAL_LLM", "1")
    # TODO: warm up DB pool, Redis connection, Langfuse client
    yield
    # TODO: graceful shutdown


app = FastAPI(
    title="Plus One API",
    version=__version__,
    description="AI travel planner backend",
    lifespan=lifespan,
)

_install_access_log_scrubber()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # TODO: load from settings
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(trips_router)


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe."""
    return {
        "status": "ok",
        "version": __version__,
        "env": settings.app_env,
    }
