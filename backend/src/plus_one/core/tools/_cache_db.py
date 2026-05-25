"""DB-backed tool cache shared by real-mode tools (Reddit / XHS / Places).

Each row keys a single source/query pair (``source`` + ``key_hash``) and
stores the raw tool response list as JSONB. Per-source TTLs live in
``_TTL_BY_SOURCE``; reads that find an expired row return ``None``
(without deleting — a separate cleanup job, deferred, handles GC).

Each read/write opens its own short ``session_scope`` per ADR-006:
agent code must NOT hold a long-lived DB transaction across the
60-90s cycle.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy.dialects.postgresql import insert as pg_insert

from plus_one.core.db.models import ToolCache
from plus_one.core.db.session import session_scope

logger = structlog.get_logger()


# Per-source TTLs (PRD Batch 2k §3.2). New sources MUST be added here
# explicitly so a typo'd source string can't silently disable caching.
_TTL_BY_SOURCE: dict[str, timedelta] = {
    "reddit": timedelta(hours=24),
    "xhs": timedelta(days=7),
    "foursquare": timedelta(days=30),
    "place_image": timedelta(days=30),
}


def _ttl_for(source: str) -> timedelta:
    if source not in _TTL_BY_SOURCE:
        raise KeyError(f"Unknown cache source {source!r}; add to _TTL_BY_SOURCE in _cache_db.py")
    return _TTL_BY_SOURCE[source]


def _hash_key(key: str) -> str:
    """SHA-256 hex of the human-readable cache key.

    Storing the hash (not the raw key) keeps the PK width bounded
    regardless of key length, and matches the ``CHAR(64)`` column.
    """
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


async def get_cached(source: str, key: str) -> list[dict[str, Any]] | None:
    """Return cached payload for ``(source, key)`` or ``None``.

    Returns ``None`` for both "row absent" and "row present but expired".
    """
    key_hash = _hash_key(key)
    now = datetime.now(UTC)
    async with session_scope() as session:
        row = await session.get(ToolCache, (source, key_hash))
        if row is None:
            return None
        if row.expires_at <= now:
            logger.info(
                "tool_cache_expired",
                source=source,
                key=key,
                expires_at=row.expires_at.isoformat(),
            )
            return None
        payload: Any = row.payload
        # Defensive: JSONB always round-trips as list/dict/str/.../None,
        # but if somebody wrote a non-list shape, refuse to return it.
        if not isinstance(payload, list):
            logger.warning(
                "tool_cache_unexpected_shape",
                source=source,
                key=key,
                got=type(payload).__name__,
            )
            return None
        return payload


async def put_cached(source: str, key: str, payload: list[dict[str, Any]]) -> None:
    """Upsert the cache row for ``(source, key)``.

    Resets ``fetched_at`` / ``expires_at`` on every write so a re-fetch
    after expiry extends the TTL forward — not anchored to the original
    insert.
    """
    key_hash = _hash_key(key)
    ttl = _ttl_for(source)
    now = datetime.now(UTC)
    expires_at = now + ttl
    async with session_scope() as session:
        stmt = (
            pg_insert(ToolCache)
            .values(
                source=source,
                key_hash=key_hash,
                payload=payload,
                fetched_at=now,
                expires_at=expires_at,
            )
            .on_conflict_do_update(
                index_elements=["source", "key_hash"],
                set_={
                    "payload": payload,
                    "fetched_at": now,
                    "expires_at": expires_at,
                    "updated_at": now,
                },
            )
        )
        await session.execute(stmt)
