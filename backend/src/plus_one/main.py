"""FastAPI application entry point.

Minimal skeleton for now: just a /health endpoint. Routes will be added
in follow-up PRs as feature areas come online.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from plus_one import __version__
from plus_one.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown hooks."""
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


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe."""
    return {
        "status": "ok",
        "version": __version__,
        "env": settings.app_env,
    }
