"""Admin log routes — SSE + frontend log push. batch-2m."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio

from plus_one.core.auth.jwt import create_access_token
from plus_one.core.auth.passwords import hash_password
from plus_one.core.db.models import User
from plus_one.core.logs.buffer import clear_for_test

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession


@pytest_asyncio.fixture
async def admin_user(
    db_session: AsyncSession,
    unique_email: Callable[[], str],
    good_username: Callable[[], str],
) -> User:
    user = User(
        email=unique_email(),
        username=good_username(),
        password_hash=hash_password("admin_password_1234"),
        is_admin=True,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest_asyncio.fixture
async def regular_user(
    db_session: AsyncSession,
    unique_email: Callable[[], str],
    good_username: Callable[[], str],
) -> User:
    user = User(
        email=unique_email(),
        username=good_username(),
        password_hash=hash_password("regular_password_1234"),
        is_admin=False,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    return user


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


@pytest.fixture(autouse=True)
def _clear_ring() -> None:
    clear_for_test()


@pytest.mark.integration
async def test_admin_logs_frontend_non_admin_403(client: AsyncClient, regular_user: User) -> None:
    r = await client.post(
        "/api/admin/logs/frontend",
        headers=_auth(regular_user),
        json={"entries": [{"ts": "2026-05-21T12:00:00Z", "level": "log", "message": "hi"}]},
    )
    assert r.status_code == 403


@pytest.mark.integration
async def test_admin_logs_frontend_admin_204(client: AsyncClient, admin_user: User) -> None:
    r = await client.post(
        "/api/admin/logs/frontend",
        headers=_auth(admin_user),
        json={"entries": [{"ts": "2026-05-21T12:00:00Z", "level": "log", "message": "hello"}]},
    )
    assert r.status_code == 204


@pytest.mark.integration
async def test_admin_logs_frontend_oversize_413(client: AsyncClient, admin_user: User) -> None:
    # Push past the 4 KB body limit.
    huge = "x" * (5 * 1024)
    r = await client.post(
        "/api/admin/logs/frontend",
        headers={**_auth(admin_user), "content-type": "application/json"},
        content=huge.encode("utf-8"),
    )
    assert r.status_code == 413


@pytest.mark.integration
async def test_admin_logs_frontend_batch_overflow_422(
    client: AsyncClient, admin_user: User
) -> None:
    entries = [{"ts": "2026-05-21T12:00:00Z", "level": "log", "message": str(i)} for i in range(51)]
    r = await client.post(
        "/api/admin/logs/frontend",
        headers=_auth(admin_user),
        json={"entries": entries},
    )
    assert r.status_code == 422


@pytest.mark.integration
async def test_admin_logs_stream_non_admin_403(client: AsyncClient, regular_user: User) -> None:
    r = await client.get("/api/admin/logs/stream", headers=_auth(regular_user))
    assert r.status_code == 403


@pytest.mark.integration
async def test_admin_logs_stream_admin_200_text_event_stream(
    client: AsyncClient, admin_user: User
) -> None:
    # Use the streaming context to read at least one chunk then bail —
    # otherwise the SSE generator runs forever.
    async with client.stream("GET", "/api/admin/logs/stream", headers=_auth(admin_user)) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        # Force at least one read so we don't leave the gen suspended.
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(r.aread(), timeout=0.5)
