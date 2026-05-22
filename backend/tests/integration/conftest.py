"""Shared fixtures for batch-2m auth integration tests.

A per-test ``AsyncSession`` against the local Postgres + a TestClient
with the session injected via ``dependency_overrides``. The SMTP sender
is monkeypatched globally to a recording fake so no real email goes out.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from plus_one.api.admin import (
    get_frontend_log_limiter as _admin_get_frontend_log_limiter,
)
from plus_one.api.admin import router as admin_router
from plus_one.api.auth import (
    get_request_code_limiter as _auth_get_request_code_limiter,
)
from plus_one.api.auth import router as auth_router
from plus_one.config import settings
from plus_one.core.auth.rate_limit import MinIntervalLimiter, TokenBucket
from plus_one.core.db.models import EmailCode, User
from plus_one.core.db.session import get_request_session

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


# === SMTP capture =========================================================

SmtpCall = tuple[str, str]


class SmtpSpy:
    """Records ``send_code_email(to=, code=)`` invocations."""

    def __init__(self) -> None:
        self.calls: list[SmtpCall] = []
        self.fail_with: Exception | None = None

    async def __call__(self, *, to: str, code: str) -> None:
        if self.fail_with is not None:
            raise self.fail_with
        self.calls.append((to, code))


@pytest.fixture
def smtp_spy(monkeypatch: pytest.MonkeyPatch) -> SmtpSpy:
    """Replace the real SMTP sender wherever the auth router uses it."""
    spy = SmtpSpy()
    from plus_one.api import auth as auth_mod

    monkeypatch.setattr(auth_mod, "send_code_email", spy)
    return spy


# === Rate limiter reset ===================================================


@pytest.fixture(autouse=True)
def _reset_rate_limiters() -> None:
    """Drop in-process counters between tests so order doesn't leak."""
    _auth_get_request_code_limiter().reset()
    _admin_get_frontend_log_limiter().reset()


# === DB plumbing ==========================================================


@pytest_asyncio.fixture
async def db_engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=2,
        max_overflow=2,
    )
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    factory = async_sessionmaker(bind=db_engine, expire_on_commit=False, autoflush=False)
    session = factory()
    try:
        yield session
    finally:
        await session.rollback()
        await session.close()


@pytest_asyncio.fixture
async def clean_db(db_session: AsyncSession) -> AsyncSession:
    """Truncate auth-relevant rows so tests start from a known state.

    Keeps the admin row if present (it's idempotent on app startup). We
    only blow away rows the auth tests themselves create.
    """
    await db_session.execute(delete(EmailCode))
    await db_session.execute(delete(User).where(User.email.like("auth-test-%@example.com")))
    await db_session.commit()
    return db_session


@pytest_asyncio.fixture
async def client(clean_db: AsyncSession) -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(admin_router)

    async def fake_get_session() -> AsyncIterator[AsyncSession]:
        yield clean_db

    app.dependency_overrides[get_request_session] = fake_get_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# === Tiny helpers =========================================================


@pytest.fixture
def unique_email() -> Callable[[], str]:
    def _gen() -> str:
        return f"auth-test-{uuid.uuid4().hex[:10]}@example.com"

    return _gen


@pytest.fixture
def good_password() -> str:
    # 12 chars, letter + digit — satisfies the §6 password rules.
    return "hunter2pass!"


@pytest.fixture
def good_username() -> Callable[[], str]:
    def _gen() -> str:
        return "u_" + uuid.uuid4().hex[:10]

    return _gen


__all__ = [
    "MinIntervalLimiter",
    "SmtpSpy",
    "TokenBucket",
]
