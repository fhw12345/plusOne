"""Tests for the cache primitives shared by fixture-backed tools."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from plus_one.core.tools._cache import cache_key, load_json_fixture, slugify


@pytest.mark.unit
def test_slugify_basic() -> None:
    assert slugify("Hello, World!") == "hello_world"
    assert slugify("  multi   space  ") == "multi_space"
    assert slugify("") == "empty"
    # Mixed input keeps the ascii portion (non-ascii dropped to underscores).
    assert slugify("中文 mixed 123") == "mixed_123"


@pytest.mark.unit
def test_cache_key_short_paths_are_human_readable() -> None:
    assert cache_key("Tokyo Ramen", "tonkotsu") == "tokyo_ramen__tonkotsu"


@pytest.mark.unit
def test_cache_key_keeps_empty_positional_placeholder() -> None:
    """Reviewer B2: empty parts now render as '_' so position is preserved.

    Format: each part is slugified (or '_' if empty) and joined with '__'.
    """
    assert cache_key("Tokyo", "", "ramen") == "tokyo_____ramen"


@pytest.mark.unit
def test_cache_key_long_input_hashed() -> None:
    parts = ("a" * 60, "b" * 60)  # joined > 100 chars
    key = cache_key(*parts)
    assert len(key) == 32
    assert all(c in "0123456789abcdef" for c in key)


@pytest.mark.unit
def test_load_json_fixture_returns_empty_on_missing(tmp_path: Path) -> None:
    assert load_json_fixture(tmp_path, "nope") == []


@pytest.mark.unit
def test_load_json_fixture_returns_list(tmp_path: Path) -> None:
    payload = [{"id": "x"}, {"id": "y"}]
    (tmp_path / "ok.json").write_text(json.dumps(payload), encoding="utf-8")
    assert load_json_fixture(tmp_path, "ok") == payload


@pytest.mark.unit
def test_load_json_fixture_rejects_non_list(tmp_path: Path) -> None:
    (tmp_path / "wrong.json").write_text(json.dumps({"items": []}), encoding="utf-8")
    assert load_json_fixture(tmp_path, "wrong") == []


# === Reviewer fixes: CJK collision + positional placeholder collision ====


@pytest.mark.unit
def test_distinct_cjk_queries_get_distinct_cache_keys() -> None:
    """Reviewer B1: previously all non-ascii queries collapsed to 'empty',
    so every Chinese XHS query hit the same fixture file. Now each gets
    a hash-suffixed slug."""
    a = slugify("东京 拉面")
    b = slugify("大阪 拉面")
    assert a != b
    assert a != "empty"
    assert b != "empty"
    # Determinism: same input always yields same slug.
    assert slugify("东京 拉面") == a


@pytest.mark.unit
def test_truly_empty_input_still_maps_to_empty() -> None:
    assert slugify("") == "empty"
    assert slugify("   ") == "empty"


@pytest.mark.unit
def test_cache_key_distinguishes_arity() -> None:
    """Reviewer B2: previously cache_key('a', '') == cache_key('a'),
    risking collision between callers with different arg shapes."""
    one = cache_key("ramen")
    two = cache_key("ramen", "")
    three = cache_key("ramen", "Tokyo")
    assert len({one, two, three}) == 3
