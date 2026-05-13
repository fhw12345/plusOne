"""Async engine + session factories + FastAPI dependencies.

Two distinct session policies live here:

  * :func:`get_request_session` — one session per HTTP request, commits
    on clean exit. Right for short REST endpoints (POST /trips form
    submit, GET /profile, etc.) where the whole handler is one logical
    transaction.

  * :func:`session_scope` (context manager) — one session for one short
    write unit. Use this from background workers / agent code that need
    to commit incrementally (e.g. flip Trip.status to 'running', later
    insert a Report row, later flip status to 'complete'). Holding a
    single transaction for the whole 60-90s cycle would lock rows for
    the duration and burn pool slots — see ADR-006 + reviewer feedback
    on PR #3.

Session pooling is also tuned via env so dev (small box) vs production
(future deployment) can pick different sizes without code changes.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from plus_one.config import settings

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


def _build_engine() -> AsyncEngine:
    """Create the async engine.

    Pool sizing comes from settings so different deployment shapes can
    tune without code changes. ``application_name`` lands in
    ``pg_stat_activity`` so we can attribute connections to this app
    when debugging contention.
    """
    return create_async_engine(
        settings.database_url,
        echo=False,
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_pool_max_overflow,
        connect_args={
            "server_settings": {
                "application_name": f"plus_one-{settings.app_env}",
                # Kill any single statement that runs longer than this.
                # Per-phase timeout in the agent cycle handles the cycle
                # level (see core/agents/framework/cycle.py); this is
                # the DB-level safety net for runaway queries.
                "statement_timeout": str(settings.db_statement_timeout_ms),
            },
        },
    )


async_engine: AsyncEngine = _build_engine()
async_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=async_engine,
    expire_on_commit=False,
    autoflush=False,
)


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """One session, one short transaction. Commits on clean exit, rolls back on error.

    Use in background workers / agent code where each logical write
    should commit immediately rather than ride along with a long-lived
    HTTP request.

    Example::

        async with session_scope() as s:
            trip = await s.get(Trip, trip_id)
            trip.status = "running"
            # auto-commit at exit
    """
    session = async_session_factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def get_request_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency for short HTTP request handlers.

    Yields a session, commits on success, rolls back on error.

    Do NOT use this for SSE streaming endpoints — those should hold no
    transaction across the cycle. SSE handlers should call
    :func:`session_scope` per write instead.

    Usage::

        @app.get("/foo")
        async def foo(session: Annotated[AsyncSession, Depends(get_request_session)]):
            ...
    """
    async with session_scope() as session:
        yield session


# Backwards-compatible alias for callers that already imported the old name.
get_session = get_request_session
