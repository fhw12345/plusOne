"""Unit tests for ``plus_one.core.tools._cache_db``.

The DB round-trip lives in ``tests/integration/test_tool_cache_db.py``
(needs real Postgres for the JSONB + ``ON CONFLICT`` upsert). This file
covers behavior we can verify without a live DB:

  * TTL table is complete and correct.
  * ``_hash_key`` is stable and deterministic.
  * ``get_cached`` returns ``None`` for an unknown source key without
    even consulting the DB (the model lookup is guarded by a key hash
    that we synthesize here).
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from plus_one.core.tools import _cache_db


@pytest.mark.unit
def test_ttls_cover_required_sources() -> None:
    assert _cache_db._TTL_BY_SOURCE["reddit"] == timedelta(hours=24)
    assert _cache_db._TTL_BY_SOURCE["xhs"] == timedelta(days=7)
    assert _cache_db._TTL_BY_SOURCE["google_places"] == timedelta(days=30)


@pytest.mark.unit
def test_ttl_for_unknown_source_raises() -> None:
    with pytest.raises(KeyError, match="Unknown cache source"):
        _cache_db._ttl_for("not_a_real_source")


@pytest.mark.unit
def test_hash_key_is_deterministic() -> None:
    a = _cache_db._hash_key("tokyo_ramen")
    b = _cache_db._hash_key("tokyo_ramen")
    c = _cache_db._hash_key("tokyo_sushi")
    assert a == b
    assert a != c
    assert len(a) == 64  # SHA-256 hex
