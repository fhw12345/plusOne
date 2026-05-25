"""Unit tests for ``FoursquarePlacesSearchTool`` in real mode.

Strategy: mock the tool's ``httpx.AsyncClient`` via ``_get_client`` and
mock the cache layer (``get_cached`` / ``put_cached``) so we don't need
a DB. This proves the cache-or-fetch branching and require_env behavior
without bringing in respx or live API access.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from plus_one.core.tools import foursquare_places as fsq_mod
from plus_one.core.tools.foursquare_places import (
    FoursquarePlacesSearchTool,
    Place,
    PlacesSearchInput,
)


@pytest.fixture
def real_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLUS_ONE_TOOLS_MODE", "real")
    monkeypatch.setenv("FOURSQUARE_API_KEY", "fake-key")


class _FakeResponse:
    def __init__(self, payload: Any, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> Any:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=httpx.Request("GET", "https://places-api.foursquare.com/places/search"),
                response=httpx.Response(self.status_code),
            )


class _FakeClient:
    def __init__(self, response: _FakeResponse | Exception) -> None:
        self._response = response
        self.calls: list[dict[str, Any]] = []

    async def get(
        self, url: str, *, params: dict[str, Any], headers: dict[str, Any]
    ) -> _FakeResponse:
        self.calls.append({"url": url, "params": params, "headers": headers})
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


# === missing-key fallback ===============================================


@pytest.mark.unit
def test_missing_api_key_in_real_mode_init_is_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLUS_ONE_TOOLS_MODE", "real")
    monkeypatch.delenv("FOURSQUARE_API_KEY", raising=False)
    FoursquarePlacesSearchTool()


@pytest.mark.unit
async def test_missing_api_key_degrades_to_fixture(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("PLUS_ONE_TOOLS_MODE", "real")
    monkeypatch.delenv("FOURSQUARE_API_KEY", raising=False)

    async def fake_get_cached(source: str, key: str) -> None:
        return None

    async def fake_put_cached(*args: object, **kwargs: object) -> None:
        raise AssertionError("must not write when using fixture fallback")

    monkeypatch.setattr(fsq_mod, "get_cached", fake_get_cached)
    monkeypatch.setattr(fsq_mod, "put_cached", fake_put_cached)
    (tmp_path / "foursquare").mkdir()
    (tmp_path / "foursquare" / "tokyo_ramen.json").write_text(
        '[{"place_id":"fixture-missing-key","name":"Fixture Ramen","formatted_address":"Tokyo",'
        '"external_url":"https://foursquare.com/v/fixture-missing-key"}]',
        encoding="utf-8",
    )

    tool = FoursquarePlacesSearchTool(fixtures_dir=tmp_path)
    fake_client = _FakeClient(_FakeResponse({"results": []}))
    monkeypatch.setattr(tool, "_get_client", lambda: fake_client)

    result = await tool.execute(PlacesSearchInput(query="Kagari ramen", location_hint="Tokyo"))

    assert result.ok
    assert result.output is not None
    assert result.output[0].place_id == "fixture-missing-key"
    assert fake_client.calls == []
    assert "missing FOURSQUARE_API_KEY" in result.notes


@pytest.mark.unit
def test_init_in_fixture_mode_does_not_require_creds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PLUS_ONE_TOOLS_MODE", raising=False)
    monkeypatch.delenv("FOURSQUARE_API_KEY", raising=False)
    # Must not raise.
    FoursquarePlacesSearchTool()


# === cache-hit short-circuits http ======================================


@pytest.mark.unit
async def test_cache_hit_skips_http(monkeypatch: pytest.MonkeyPatch, real_mode: None) -> None:
    cached_payload = [
        {
            "place_id": "pid-cached",
            "name": "Cached Ramen",
            "formatted_address": "1-1 Tokyo",
            "categories": ["Ramen"],
            "types": ["Ramen"],
            "external_url": "https://foursquare.com/v/pid-cached",
        }
    ]

    async def fake_get_cached(source: str, key: str) -> list[dict[str, Any]]:
        return cached_payload

    async def fake_put_cached(source: str, key: str, payload: list[dict[str, Any]]) -> None:
        raise AssertionError("put_cached must not run on cache hit")

    monkeypatch.setattr(fsq_mod, "get_cached", fake_get_cached)
    monkeypatch.setattr(fsq_mod, "put_cached", fake_put_cached)

    tool = FoursquarePlacesSearchTool()
    fake_client = _FakeClient(_FakeResponse({"results": []}))
    monkeypatch.setattr(tool, "_get_client", lambda: fake_client)

    result = await tool.execute(
        PlacesSearchInput(query="tokyo ramen", location_hint="Tokyo, Japan")
    )
    assert result.ok
    assert result.output is not None
    assert len(result.output) == 1
    assert result.output[0].place_id == "pid-cached"
    assert fake_client.calls == []
    assert "cache hit" in result.notes


@pytest.mark.unit
async def test_cache_miss_calls_api_and_writes_cache(
    monkeypatch: pytest.MonkeyPatch, real_mode: None
) -> None:
    fsq_response = {
        "results": [
            {
                "fsq_place_id": "fsq-fresh",
                "name": "Fresh Ramen",
                "location": {"formatted_address": "2-2 Tokyo"},
                "latitude": 35.0,
                "longitude": 139.0,
                "categories": [{"short_name": "Ramen"}, {"short_name": "Restaurant"}],
                "distance": 100,
            }
        ]
    }

    async def fake_get_cached(source: str, key: str) -> list[dict[str, Any]] | None:
        return None

    written: list[tuple[str, str, list[dict[str, Any]]]] = []

    async def fake_put_cached(source: str, key: str, payload: list[dict[str, Any]]) -> None:
        written.append((source, key, payload))

    monkeypatch.setattr(fsq_mod, "get_cached", fake_get_cached)
    monkeypatch.setattr(fsq_mod, "put_cached", fake_put_cached)

    tool = FoursquarePlacesSearchTool()
    fake_client = _FakeClient(_FakeResponse(fsq_response))
    monkeypatch.setattr(tool, "_get_client", lambda: fake_client)

    result = await tool.execute(
        PlacesSearchInput(query="tokyo ramen", location_hint="Tokyo, Japan")
    )
    assert result.ok
    assert result.output is not None
    assert result.output[0].place_id == "fsq-fresh"
    assert result.output[0].external_url == "https://foursquare.com/v/fsq-fresh"
    assert result.output[0].photo_url is None
    assert len(written) == 1
    assert written[0][0] == "foursquare"
    # Cache should contain the mapped (not raw) payload.
    cached_payload = written[0][2]
    assert cached_payload[0]["place_id"] == "fsq-fresh"
    assert cached_payload[0]["external_url"] == "https://foursquare.com/v/fsq-fresh"
    assert cached_payload[0]["categories"] == ("Ramen", "Restaurant")
    assert cached_payload[0]["photo_url"] is None
    # Verify the API call used 'near' param.
    assert fake_client.calls[0]["params"]["near"] == "Tokyo, Japan"
    assert fake_client.calls[0]["params"]["query"] == "tokyo ramen"


@pytest.mark.unit
async def test_api_failure_returns_not_ok(monkeypatch: pytest.MonkeyPatch, real_mode: None) -> None:
    async def fake_get_cached(source: str, key: str) -> None:
        return None

    async def fake_put_cached(*args: object, **kwargs: object) -> None:
        raise AssertionError("must not write on failure")

    monkeypatch.setattr(fsq_mod, "get_cached", fake_get_cached)
    monkeypatch.setattr(fsq_mod, "put_cached", fake_put_cached)

    tool = FoursquarePlacesSearchTool()
    err = httpx.HTTPStatusError(
        "boom",
        request=httpx.Request("GET", "https://places-api.foursquare.com/places/search"),
        response=httpx.Response(500),
    )
    fake_client = _FakeClient(err)
    monkeypatch.setattr(tool, "_get_client", lambda: fake_client)

    result = await tool.execute(PlacesSearchInput(query="anything"))
    assert result.ok is False
    assert result.error is not None
    assert "foursquare" in result.error.lower()


@pytest.mark.unit
async def test_api_failure_degrades_to_fixture(
    monkeypatch: pytest.MonkeyPatch,
    real_mode: None,
    tmp_path,
) -> None:
    async def fake_get_cached(source: str, key: str) -> None:
        return None

    async def fake_put_cached(*args: object, **kwargs: object) -> None:
        raise AssertionError("must not write when using fixture fallback")

    monkeypatch.setattr(fsq_mod, "get_cached", fake_get_cached)
    monkeypatch.setattr(fsq_mod, "put_cached", fake_put_cached)
    (tmp_path / "foursquare").mkdir()
    (tmp_path / "foursquare" / "tokyo_ramen.json").write_text(
        '[{"place_id":"fixture-1","name":"Fixture Ramen","formatted_address":"Tokyo",'
        '"external_url":"https://foursquare.com/v/fixture-1"}]',
        encoding="utf-8",
    )

    tool = FoursquarePlacesSearchTool(fixtures_dir=tmp_path)
    err = httpx.HTTPStatusError(
        "boom",
        request=httpx.Request("GET", "https://places-api.foursquare.com/places/search"),
        response=httpx.Response(400),
    )
    fake_client = _FakeClient(err)
    monkeypatch.setattr(tool, "_get_client", lambda: fake_client)

    result = await tool.execute(PlacesSearchInput(query="Kagari ramen", location_hint="Tokyo"))

    assert result.ok
    assert result.output is not None
    assert result.output[0].place_id == "fixture-1"
    assert "degraded to fixture" in result.notes


# === fixture mode untouched =============================================


@pytest.mark.unit
async def test_fixture_mode_unchanged(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """In fixture mode, execute() must NOT touch http or the DB cache."""
    monkeypatch.delenv("PLUS_ONE_TOOLS_MODE", raising=False)

    async def explode(*args: object, **kwargs: object) -> None:
        raise AssertionError("real-mode helper called in fixture mode")

    monkeypatch.setattr(fsq_mod, "get_cached", explode)
    monkeypatch.setattr(fsq_mod, "put_cached", explode)

    (tmp_path / "foursquare").mkdir()
    (tmp_path / "foursquare" / "tokyo_ramen___.json").write_text(
        '[{"place_id":"f1","name":"Ramen Shop","formatted_address":"Tokyo",'
        '"external_url":"https://foursquare.com/v/f1"}]'
    )

    tool = FoursquarePlacesSearchTool(fixtures_dir=tmp_path)
    result = await tool.execute(PlacesSearchInput(query="Tokyo ramen"))
    assert result.ok
    assert result.output is not None
    assert result.output[0].place_id == "f1"
    assert result.output[0].external_url == "https://foursquare.com/v/f1"


# === fetch payload normalization ========================================


@pytest.mark.unit
async def test_fetch_normalizes_response(monkeypatch: pytest.MonkeyPatch, real_mode: None) -> None:
    """Verify ``_fetch_from_api`` reads the Foursquare shape and converts
    it to the cache payload schema (external_url synthesis, categories
    from short_name, rating None, slices to limit)."""
    tool = FoursquarePlacesSearchTool()

    fsq_response = {
        "results": [
            {
                "fsq_place_id": "p1",
                "name": "Spot 1",
                "location": {"formatted_address": "1 Tokyo"},
                "latitude": 35.1,
                "longitude": 139.1,
                "categories": [
                    {"short_name": "Ramen"},
                    {"short_name": "Restaurant"},
                ],
                "distance": 50,
            },
            {
                "fsq_place_id": "p2",
                "name": "Spot 2",
                "location": {"formatted_address": "2 Tokyo"},
            },
            {
                "fsq_place_id": "p3",
                "name": "Spot 3",
                "location": {"formatted_address": "3 Tokyo"},
            },
        ]
    }
    fake_client = _FakeClient(_FakeResponse(fsq_response))
    monkeypatch.setattr(tool, "_get_client", lambda: fake_client)

    out = await tool._fetch_from_api(
        PlacesSearchInput(query="ramen", location_hint="Tokyo, Japan", limit=2)
    )

    assert fake_client.calls[0]["params"]["query"] == "ramen"
    assert fake_client.calls[0]["params"]["near"] == "Tokyo, Japan"
    assert fake_client.calls[0]["params"]["limit"] == 2
    assert "Bearer fake-key" in fake_client.calls[0]["headers"]["Authorization"]

    assert len(out) == 2  # limit honored
    assert out[0]["place_id"] == "p1"
    assert out[0]["external_url"] == "https://foursquare.com/v/p1"
    assert out[0]["categories"] == ("Ramen", "Restaurant")
    assert out[0]["types"] == ("Ramen", "Restaurant")
    assert out[0]["rating"] is None
    assert out[0]["price_level"] is None
    assert out[0]["distance_m"] == 50
    assert out[0]["latitude"] == pytest.approx(35.1)
    assert out[0]["photo_url"] is None
    # Second item missing categories etc — defaults work
    assert out[1]["place_id"] == "p2"
    assert out[1]["categories"] == ()
    assert out[1]["rating"] is None
    # Place model accepts the output
    place = Place.model_validate(out[0])
    assert place.external_url == "https://foursquare.com/v/p1"
