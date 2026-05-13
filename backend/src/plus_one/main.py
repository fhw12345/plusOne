"""FastAPI application entry point.

Minimal skeleton for now: just a /health endpoint. Routes will be added
in follow-up PRs as feature areas come online.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from plus_one import __version__
from plus_one.api.auth import router as auth_router
from plus_one.config import settings

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown hooks."""
    # Production entry point opt-in: real LLM access is allowed for this
    # process. Tests never go through this lifespan and therefore never set
    # the flag, so a stray MaestroProvider() in a test will still raise.
    os.environ["PLUS_ONE_ALLOW_REAL_LLM"] = "1"
    # TODO: warm up DB pool, Redis connection, Langfuse client
    yield
    # TODO: graceful shutdown


app = FastAPI(
    title="Plus One API",
    version=__version__,
    description="AI travel planner backend",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # TODO: load from settings
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe."""
    return {
        "status": "ok",
        "version": __version__,
        "env": settings.app_env,
    }
