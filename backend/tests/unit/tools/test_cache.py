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
    assert slugify("中文 mixed 123") == "mixed_123"  # non-ascii dropped


@pytest.mark.unit
def test_cache_key_short_paths_are_human_readable() -> None:
    assert cache_key("Tokyo Ramen", "tonkotsu") == "tokyo_ramen__tonkotsu"


@pytest.mark.unit
def test_cache_key_skips_empty_components() -> None:
    assert cache_key("Tokyo", "", "ramen") == "tokyo__ramen"


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
