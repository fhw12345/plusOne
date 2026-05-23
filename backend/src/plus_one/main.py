"""FastAPI application entry point.

Routes: /api/auth, /api/admin, /api/profile, /api/companions,
/api/trips, /api/shared, /health.

Startup lifecycle:
  * install access-log scrubber (legacy SSE access_token redaction)
  * install admin-tail log handler (batch-2m)
  * seed admin user if absent
"""

from __future__ import annotations

import logging
import os
import re
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from plus_one import __version__
from plus_one.api.admin import router as admin_router
from plus_one.api.auth import router as auth_router
from plus_one.api.companions import router as companions_router
from plus_one.api.me import router as me_router
from plus_one.api.profile import router as profile_router
from plus_one.api.shared import router as shared_router
from plus_one.api.trips import router as trips_router
from plus_one.config import settings
from plus_one.core.auth.admin_seed import ensure_admin_user
from plus_one.core.logs.buffer import install_admin_tail

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


_ACCESS_TOKEN_RE = re.compile(r"access_token=[^&\s\"]+")


class _ScrubAccessTokenFilter(logging.Filter):
    """Redact ``access_token=<jwt>`` from uvicorn access log lines."""

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
    os.environ.setdefault("PLUS_ONE_ALLOW_REAL_LLM", "1")

    # batch-2v: warn loudly if real-mode tools are enabled but no OS-level
    # proxy env is set — local dev behind GFW needs HTTPS_PROXY to reach
    # reddit.com / googleapis.com. Production VMs leave these unset and
    # connect direct, so we only log; we never abort.
    if os.getenv("PLUS_ONE_TOOLS_MODE", "").lower() == "real" and (
        os.getenv("PLUS_ONE_REDDIT_PROXY") is None
    ):
        structlog.get_logger().warning(
            "reddit_proxy_unset",
            note="PLUS_ONE_REDDIT_PROXY unset; real-mode Reddit may fail outside cloud env",
        )

    # batch-2m: admin log tail handler + secret-redacting filter.
    install_admin_tail()

    # batch-2m: idempotent admin seed.
    try:
        await ensure_admin_user()
    except Exception:
        # Don't crash the app if the DB happens to be unreachable at
        # boot — log it; admin endpoints will return 403 until the row
        # is in place.
        logging.getLogger(__name__).exception("ensure_admin_user_failed")

    yield


app = FastAPI(
    title="Plus One API",
    version=__version__,
    description="AI travel planner backend",
    lifespan=lifespan,
)

_install_access_log_scrubber()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3003",
        "http://127.0.0.1:3003",
    ],  # TODO: load from settings
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(profile_router)
app.include_router(me_router)
app.include_router(companions_router)
app.include_router(trips_router)
app.include_router(shared_router)


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe."""
    return {
        "status": "ok",
        "version": __version__,
        "env": settings.app_env,
    }
