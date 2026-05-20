"""Unit tests for ``GooglePlacesSearchTool`` in real mode.

Strategy: stub out ``_fetch_from_places_sync`` (which is the only place
the tool talks to ``googlemaps``) and mock the cache layer
(``get_cached`` / ``put_cached``) so we don't need a DB. This proves
the cache-or-fetch branching and require_env behavior without bringing
in vcrpy or live API access.
"""

from __future__ import annotations

from typing import Any

import pytest

from plus_one.core.tools import google_places as gp_mod
from plus_one.core.tools.google_places import (
    GooglePlacesSearchInput,
    GooglePlacesSearchTool,
)


@pytest.fixture
def real_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLUS_ONE_TOOLS_MODE", "real")
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "fake-key")


# === require_env at __init__ ============================================


@pytest.mark.unit
def test_missing_api_key_in_real_mode_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLUS_ONE_TOOLS_MODE", "real")
    monkeypatch.delenv("GOOGLE_PLACES_API_KEY", raising=False)
    with pytest.raises(RuntimeError) as exc_info:
        GooglePlacesSearchTool()
    msg = str(exc_info.value)
    assert "google_places_search" in msg
    assert "GOOGLE_PLACES_API_KEY" in msg


@pytest.mark.unit
def test_init_in_fixture_mode_does_not_require_creds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PLUS_ONE_TOOLS_MODE", raising=False)
    monkeypatch.delenv("GOOGLE_PLACES_API_KEY", raising=False)
    # Must not raise.
    GooglePlacesSearchTool()


# === cache-hit short-circuits googlemaps ================================


@pytest.mark.unit
async def test_cache_hit_skips_googlemaps(monkeypatch: pytest.MonkeyPatch, real_mode: None) -> None:
    cached_payload = [
        {
            "place_id": "pid-cached",
            "name": "Cached Ramen",
            "formatted_address": "1-1 Tokyo",
            "rating": 4.5,
            "user_ratings_total": 1234,
            "price_level": 2,
            "types": ["restaurant"],
            "google_maps_url": "https://maps.example/cached",
        }
    ]

    async def fake_get_cached(source: str, key: str) -> list[dict[str, Any]]:
        return cached_payload

    async def fake_put_cached(source: str, key: str, payload: list[dict[str, Any]]) -> None:
        raise AssertionError("put_cached must not run on cache hit")

    fetch_called = False

    def fake_fetch(*args: object, **kwargs: object) -> list[dict[str, Any]]:
        nonlocal fetch_called
        fetch_called = True
        return []

    monkeypatch.setattr(gp_mod, "get_cached", fake_get_cached)
    monkeypatch.setattr(gp_mod, "put_cached", fake_put_cached)

    tool = GooglePlacesSearchTool()
    monkeypatch.setattr(tool, "_fetch_from_places_sync", fake_fetch)

    result = await tool.execute(
        GooglePlacesSearchInput(query="tokyo ramen", location_hint="Tokyo, Japan")
    )
    assert result.ok
    assert result.output is not None
    assert len(result.output) == 1
    assert result.output[0].place_id == "pid-cached"
    assert fetch_called is False
    assert "cache hit" in result.notes


@pytest.mark.unit
async def test_cache_miss_calls_googlemaps_and_writes_cache(
    monkeypatch: pytest.MonkeyPatch, real_mode: None
) -> None:
    fetched_payload = [
        {
            "place_id": "pid-fresh",
            "name": "Fresh Ramen",
            "formatted_address": "2-2 Tokyo",
            "rating": 4.7,
            "user_ratings_total": 99,
            "price_level": 1,
            "types": ["restaurant", "food"],
            "google_maps_url": "https://maps.example/fresh",
        }
    ]

    async def fake_get_cached(source: str, key: str) -> list[dict[str, Any]] | None:
        return None

    written: list[tuple[str, str, list[dict[str, Any]]]] = []

    async def fake_put_cached(source: str, key: str, payload: list[dict[str, Any]]) -> None:
        written.append((source, key, payload))

    def fake_fetch(query: str, location_hint: str, limit: int) -> list[dict[str, Any]]:
        assert query == "tokyo ramen"
        assert location_hint == "Tokyo, Japan"
        return fetched_payload

    monkeypatch.setattr(gp_mod, "get_cached", fake_get_cached)
    monkeypatch.setattr(gp_mod, "put_cached", fake_put_cached)

    tool = GooglePlacesSearchTool()
    monkeypatch.setattr(tool, "_fetch_from_places_sync", fake_fetch)

    result = await tool.execute(
        GooglePlacesSearchInput(query="tokyo ramen", location_hint="Tokyo, Japan")
    )
    assert result.ok
    assert result.output is not None
    assert result.output[0].place_id == "pid-fresh"
    assert len(written) == 1
    assert written[0][0] == "google_places"
    assert written[0][2] == fetched_payload


@pytest.mark.unit
async def test_googlemaps_failure_returns_not_ok(
    monkeypatch: pytest.MonkeyPatch, real_mode: None
) -> None:
    async def fake_get_cached(source: str, key: str) -> None:
        return None

    async def fake_put_cached(*args: object, **kwargs: object) -> None:
        raise AssertionError("must not write on failure")

    def fake_fetch(*args: object, **kwargs: object) -> list[dict[str, Any]]:
        raise RuntimeError("places api boom")

    monkeypatch.setattr(gp_mod, "get_cached", fake_get_cached)
    monkeypatch.setattr(gp_mod, "put_cached", fake_put_cached)

    tool = GooglePlacesSearchTool()
    monkeypatch.setattr(tool, "_fetch_from_places_sync", fake_fetch)

    result = await tool.execute(GooglePlacesSearchInput(query="anything"))
    assert result.ok is False
    assert result.error is not None
    assert "boom" in result.error


# === fixture mode untouched =============================================


@pytest.mark.unit
async def test_fixture_mode_unchanged(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """In fixture mode, execute() must NOT touch googlemaps or the DB cache."""
    monkeypatch.delenv("PLUS_ONE_TOOLS_MODE", raising=False)

    async def explode(*args: object, **kwargs: object) -> None:
        raise AssertionError("real-mode helper called in fixture mode")

    monkeypatch.setattr(gp_mod, "get_cached", explode)
    monkeypatch.setattr(gp_mod, "put_cached", explode)

    (tmp_path / "google_places").mkdir()
    # cache_key includes the empty location_hint trailing param -> filename
    # 'tokyo_ramen___.json' per existing _cache.py conventions.
    (tmp_path / "google_places" / "tokyo_ramen___.json").write_text(
        '[{"place_id":"f1","name":"Ramen Shop","formatted_address":"Tokyo"}]'
    )

    tool = GooglePlacesSearchTool(fixtures_dir=tmp_path)
    result = await tool.execute(GooglePlacesSearchInput(query="Tokyo ramen"))
    assert result.ok
    assert result.output is not None
    assert result.output[0].place_id == "f1"


# === sync fetch payload normalization ===================================


@pytest.mark.unit
def test_fetch_normalizes_googlemaps_response(
    monkeypatch: pytest.MonkeyPatch, real_mode: None
) -> None:
    """Verify ``_fetch_from_places_sync`` reads the googlemaps shape and
    converts it to the cache payload schema (drops extra keys, fills
    google_maps_url, slices to limit)."""
    tool = GooglePlacesSearchTool()

    captured_kwargs: dict[str, Any] = {}

    class _FakeClient:
        def places(self, **kwargs: Any) -> dict[str, Any]:
            captured_kwargs.update(kwargs)
            return {
                "results": [
                    {
                        "place_id": "p1",
                        "name": "Spot 1",
                        "formatted_address": "1 Tokyo",
                        "rating": 4.5,
                        "user_ratings_total": 100,
                        "price_level": 2,
                        "types": ["restaurant", "food"],
                        "extra_unused_key": "ignored",
                    },
                    {
                        "place_id": "p2",
                        "name": "Spot 2",
                        "formatted_address": "2 Tokyo",
                    },
                    {
                        "place_id": "p3",
                        "name": "Spot 3",
                        "formatted_address": "3 Tokyo",
                    },
                ]
            }

    fake_client = _FakeClient()
    monkeypatch.setattr(tool, "_get_client", lambda: fake_client)

    out = tool._fetch_from_places_sync("ramen", "Tokyo, Japan", limit=2)
    assert captured_kwargs["query"] == "ramen Tokyo, Japan"
    assert captured_kwargs["language"] == "en"
    assert len(out) == 2  # limit honored
    assert out[0]["place_id"] == "p1"
    assert out[0]["rating"] == 4.5
    assert out[0]["types"] == ("restaurant", "food")
    assert out[0]["google_maps_url"] is not None
    assert "p1" in out[0]["google_maps_url"]
    # Second item missing rating etc — defaults to None
    assert out[1]["rating"] is None
    assert out[1]["price_level"] is None
