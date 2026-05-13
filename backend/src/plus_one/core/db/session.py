"""Async engine + session factory + FastAPI dependency.

The session is created via ``async_sessionmaker`` and yielded as a
context-managed dependency. Repositories receive an ``AsyncSession`` and
must NOT commit themselves — commit/rollback is the dependency's job, so
that an HTTP handler that calls multiple repositories sees one atomic
transaction by default.
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

    Pool sizing is conservative for a single-machine local-host project
    (per ADR-006). Production at scale would tune this differently.
    """
    return create_async_engine(
        settings.database_url,
        echo=False,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
    )


async_engine: AsyncEngine = _build_engine()
async_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=async_engine,
    expire_on_commit=False,
    autoflush=False,
)


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Context-manage a session: commit on clean exit, rollback on exception.

    Use this in scripts / tasks that don't go through FastAPI DI.
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


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: yields a session, commits on success, rolls back on error.

    Usage::

        @app.get("/foo")
        async def foo(session: Annotated[AsyncSession, Depends(get_session)]):
            ...
    """
    async with session_scope() as session:
        yield session
