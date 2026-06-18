"""Unit tests for the free/public place image resolver."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from plus_one.core.tools import place_images as image_mod
from plus_one.core.tools.place_images import PlaceImageInput, PlaceImageResolver


class _FakeClient:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def get(self, url: str, *, params: dict[str, Any]) -> httpx.Response:
        self.calls.append((url, params))
        body = self.responses.pop(0)
        return httpx.Response(200, json=body, request=httpx.Request("GET", url))


@pytest.mark.unit
async def test_fixture_mode_resolves_by_name_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    monkeypatch.setenv("PLUS_ONE_TOOLS_MODE", "fixture")
    (tmp_path / "place_images").mkdir()
    (tmp_path / "place_images" / "ichiran_shibuya.json").write_text(
        '[{"image_url":"https://img.example/ichiran.jpg","source":"fixture","title":"Ichiran"}]',
        encoding="utf-8",
    )

    resolver = PlaceImageResolver(fixtures_dir=tmp_path)
    image = await resolver.resolve(
        PlaceImageInput(name="Ichiran Shibuya", location_hint="Tokyo tonkotsu ramen")
    )

    assert image is not None
    assert image.image_url == "https://img.example/ichiran.jpg"
    assert image.source == "fixture"


@pytest.mark.unit
async def test_cache_hit_skips_http(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLUS_ONE_TOOLS_MODE", "real")

    async def fake_get_cached(source: str, key: str) -> list[dict[str, Any]]:
        assert source == "place_image"
        assert key == "tsuta__tokyo__ramen"
        return [
            {
                "image_url": "https://img.example/cached.jpg",
                "source": "cache",
                "title": "Tsuta",
            }
        ]

    async def explode_put(*args: object, **kwargs: object) -> None:
        raise AssertionError("put_cached must not run on cache hit")

    fake_client = _FakeClient([])
    monkeypatch.setattr(image_mod, "get_cached", fake_get_cached)
    monkeypatch.setattr(image_mod, "put_cached", explode_put)

    resolver = PlaceImageResolver()
    monkeypatch.setattr(resolver, "_get_client", lambda: fake_client)

    image = await resolver.resolve(PlaceImageInput(name="Tsuta", location_hint="Tokyo", category="ramen"))

    assert image is not None
    assert image.image_url == "https://img.example/cached.jpg"
    assert fake_client.calls == []


@pytest.mark.unit
async def test_commons_response_maps_image_and_writes_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PLUS_ONE_TOOLS_MODE", "real")
    commons_body = {
        "query": {
            "pages": [
                {
                    "title": "File:Ichiran ramen by SkyChen in Shibuya, Tokyo.jpg",
                    "imageinfo": [
                        {
                            "thumburl": "https://upload.wikimedia.org/ichiran.jpg",
                            "descriptionurl": "https://commons.wikimedia.org/wiki/File:Ichiran.jpg",
                            "extmetadata": {
                                "LicenseShortName": {"value": "CC BY 2.0"},
                                "Artist": {"value": "<a>SkyChen</a>"},
                            },
                        }
                    ],
                }
            ]
        }
    }
    fake_client = _FakeClient([commons_body])
    written: list[tuple[str, str, list[dict[str, Any]]]] = []

    async def fake_get_cached(source: str, key: str) -> None:
        return None

    async def fake_put_cached(source: str, key: str, payload: list[dict[str, Any]]) -> None:
        written.append((source, key, payload))

    monkeypatch.setattr(image_mod, "get_cached", fake_get_cached)
    monkeypatch.setattr(image_mod, "put_cached", fake_put_cached)

    resolver = PlaceImageResolver()
    monkeypatch.setattr(resolver, "_get_client", lambda: fake_client)

    image = await resolver.resolve(
        PlaceImageInput(name="Ichiran Shibuya", location_hint="Tokyo", category="ramen")
    )

    assert image is not None
    assert image.image_url == "https://upload.wikimedia.org/ichiran.jpg"
    assert image.source == "wikimedia_commons"
    assert image.license == "CC BY 2.0"
    assert image.creator == "SkyChen"
    assert fake_client.calls[0][0] == image_mod._COMMONS_API
    assert written[0][0] == "place_image"
    assert written[0][2][0]["image_url"] == "https://upload.wikimedia.org/ichiran.jpg"


@pytest.mark.unit
async def test_openverse_fallback_when_commons_is_irrelevant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PLUS_ONE_TOOLS_MODE", "real")
    commons_body = {
        "query": {
            "pages": [
                {
                    "title": "File:Unrelated shrine.jpg",
                    "imageinfo": [{"thumburl": "https://upload.wikimedia.org/shrine.jpg"}],
                }
            ]
        }
    }
    openverse_body = {
        "results": [
            {
                "title": "Tsuta ramen counter",
                "thumbnail": "https://openverse.example/tsuta.jpg",
                "source": "flickr",
                "license": "by",
                "creator": "Alice",
                "foreign_landing_url": "https://flickr.example/tsuta",
            }
        ]
    }
    fake_client = _FakeClient([commons_body, openverse_body])

    async def fake_get_cached(source: str, key: str) -> None:
        return None

    async def fake_put_cached(source: str, key: str, payload: list[dict[str, Any]]) -> None:
        return None

    monkeypatch.setattr(image_mod, "get_cached", fake_get_cached)
    monkeypatch.setattr(image_mod, "put_cached", fake_put_cached)

    resolver = PlaceImageResolver()
    monkeypatch.setattr(resolver, "_get_client", lambda: fake_client)

    image = await resolver.resolve(PlaceImageInput(name="Tsuta", location_hint="Tokyo"))

    assert image is not None
    assert image.image_url == "https://openverse.example/tsuta.jpg"
    assert image.source == "openverse:flickr"
    assert [call[0] for call in fake_client.calls] == [image_mod._COMMONS_API, image_mod._OPENVERSE_API]


@pytest.mark.unit
async def test_real_mode_ignores_generic_fixture_after_provider_failures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    monkeypatch.setenv("PLUS_ONE_TOOLS_MODE", "real")
    (tmp_path / "place_images").mkdir()
    (tmp_path / "place_images" / "tokyo_ramen.json").write_text(
        '[{"image_url":"https://img.example/tokyo-ramen.jpg","source":"fixture","title":"Ramen"}]',
        encoding="utf-8",
    )

    async def fake_get_cached(source: str, key: str) -> None:
        return None

    written: list[tuple[str, str, list[dict[str, Any]]]] = []

    async def fake_put_cached(source: str, key: str, payload: list[dict[str, Any]]) -> None:
        written.append((source, key, payload))

    monkeypatch.setattr(image_mod, "get_cached", fake_get_cached)
    monkeypatch.setattr(image_mod, "put_cached", fake_put_cached)

    resolver = PlaceImageResolver(fixtures_dir=tmp_path)

    async def fail_live(args: PlaceImageInput) -> None:
        del args

    monkeypatch.setattr(resolver, "_resolve_live", fail_live)

    image = await resolver.resolve(PlaceImageInput(name="Kagari", location_hint="Tokyo", category="ramen"))

    assert image is None
    assert written == []


@pytest.mark.unit
async def test_real_mode_ignores_irrelevant_cached_image(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PLUS_ONE_TOOLS_MODE", "real")

    async def fake_get_cached(source: str, key: str) -> list[dict[str, Any]]:
        assert source == "place_image"
        assert key == "menya_itto__tokyo__ramen"
        return [
            {
                "image_url": "https://upload.wikimedia.org/ichiran.jpg",
                "source": "wikimedia_commons",
                "title": "File:Ichiran ramen by SkyChen in Shibuya, Tokyo.jpg",
            }
        ]

    async def fake_put_cached(source: str, key: str, payload: list[dict[str, Any]]) -> None:
        del source, key, payload
        raise AssertionError("irrelevant cached image should not be re-cached")

    monkeypatch.setattr(image_mod, "get_cached", fake_get_cached)
    monkeypatch.setattr(image_mod, "put_cached", fake_put_cached)

    resolver = PlaceImageResolver()

    async def no_live_image(args: PlaceImageInput) -> None:
        del args

    monkeypatch.setattr(resolver, "_resolve_live", no_live_image)

    image = await resolver.resolve(
        PlaceImageInput(name="Menya Itto", location_hint="Tokyo", category="ramen")
    )

    assert image is None


@pytest.mark.unit
async def test_fixture_mode_can_use_generic_fixture(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    monkeypatch.setenv("PLUS_ONE_TOOLS_MODE", "fixture")
    (tmp_path / "place_images").mkdir()
    (tmp_path / "place_images" / "tokyo_ramen.json").write_text(
        '[{"image_url":"https://img.example/tokyo-ramen.jpg","source":"fixture","title":"Ramen"}]',
        encoding="utf-8",
    )

    resolver = PlaceImageResolver(fixtures_dir=tmp_path)
    image = await resolver.resolve(PlaceImageInput(name="Kagari", location_hint="Tokyo", category="ramen"))

    assert image is not None
    assert image.image_url == "https://img.example/tokyo-ramen.jpg"
    assert image.source == "fixture"
