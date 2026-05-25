"""Free place-image resolver for itinerary cards.

The resolver deliberately avoids paid Places Photos APIs and social-media
hotlink scraping. It tries public, attribution-friendly sources in order:

1. local fixture file (fixture mode / deterministic e2e)
2. Wikimedia Commons search
3. Openverse image search

Real-mode results are cached in the existing DB-backed tool cache. Any
network or parse failure returns ``None`` so image enrichment never poisons
the trip cycle.
"""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any, ClassVar

import httpx
import structlog
from pydantic import BaseModel, ConfigDict, Field

from plus_one.config import settings
from plus_one.core.tools._cache import cache_key, load_json_fixture
from plus_one.core.tools._cache_db import get_cached, put_cached
from plus_one.core.tools._mode import get_tools_mode

logger = structlog.get_logger()

_COMMONS_API = "https://commons.wikimedia.org/w/api.php"
_OPENVERSE_API = "https://api.openverse.engineering/v1/images/"
_UA = "plus-one-image-resolver/0.1 (free public image lookup)"
_MIN_RELEVANT_TERM_CHARS = 3


class PlaceImage(BaseModel):
    """One resolved image URL plus lightweight attribution metadata."""

    model_config = ConfigDict(frozen=True)

    image_url: str
    source: str
    title: str = ""
    license: str | None = None
    creator: str | None = None
    page_url: str | None = None


class PlaceImageInput(BaseModel):
    """Args for ``PlaceImageResolver.resolve``."""

    name: str = Field(min_length=1, max_length=200)
    location_hint: str = Field(default="", max_length=200)
    category: str = Field(default="", max_length=100)


class PlaceImageResolver:
    """Best-effort free image resolver.

    Not exposed as a framework Tool because the joiner uses it as a
    deterministic enrichment step after places lookup rather than as LLM
    evidence. The public method stays small for unit tests.
    """

    _SOURCE: ClassVar[str] = "place_image"

    def __init__(self, fixtures_dir: Path | None = None) -> None:
        self._fixtures_dir = (fixtures_dir or settings.fixtures_dir) / "place_images"
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(12.0, connect=5.0),
            headers={"User-Agent": _UA, "Accept": "application/json"},
            follow_redirects=True,
        )
        return self._client

    def _fixture(self, args: PlaceImageInput) -> PlaceImage | None:
        for candidate_key in _fixture_keys(args):
            raw = load_json_fixture(self._fixtures_dir, candidate_key)
            if not raw:
                continue
            try:
                return PlaceImage.model_validate(raw[0])
            except Exception as exc:
                logger.warning("place_image_fixture_invalid", name=args.name, error=str(exc))
                return None
        return None

    async def resolve(self, args: PlaceImageInput) -> PlaceImage | None:
        if get_tools_mode() == "fixture":
            return self._fixture(args)

        key = cache_key(args.name, args.location_hint, args.category)
        try:
            cached = await get_cached(self._SOURCE, key)
        except Exception as exc:
            logger.warning("place_image_cache_lookup_failed", key=key, error=str(exc))
            cached = None
        if cached:
            try:
                return PlaceImage.model_validate(cached[0])
            except Exception as exc:
                logger.warning("place_image_cache_invalid", key=key, error=str(exc))

        image = await self._resolve_live(args)
        if image is None:
            image = self._fixture(args)
            if image is not None:
                logger.warning("place_image_degraded_to_fixture", name=args.name, key=key)
        if image is not None:
            try:
                await put_cached(self._SOURCE, key, [image.model_dump(mode="json")])
            except Exception as exc:
                logger.warning("place_image_cache_write_failed", key=key, error=str(exc))
        return image

    async def _resolve_live(self, args: PlaceImageInput) -> PlaceImage | None:
        for fetcher in (self._fetch_commons, self._fetch_openverse):
            try:
                image = await fetcher(args)
            except Exception as exc:
                logger.warning(
                    "place_image_provider_failed",
                    provider=fetcher.__name__,
                    name=args.name,
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
                image = None
            if image is not None:
                return image
        return None

    async def _fetch_commons(self, args: PlaceImageInput) -> PlaceImage | None:
        query = _search_query(args)
        response = await self._get_client().get(
            _COMMONS_API,
            params={
                "action": "query",
                "format": "json",
                "formatversion": "2",
                "generator": "search",
                "gsrsearch": query,
                "gsrnamespace": "6",
                "gsrlimit": "4",
                "prop": "imageinfo",
                "iiprop": "url|extmetadata",
                "iiurlwidth": "900",
            },
        )
        response.raise_for_status()
        pages = response.json().get("query", {}).get("pages", []) or []
        terms = _important_terms(args.name)
        for page in pages:
            title = str(page.get("title") or "")
            if not _looks_relevant(title, terms):
                continue
            info = (page.get("imageinfo") or [{}])[0]
            image_url = info.get("thumburl") or info.get("url")
            if not isinstance(image_url, str) or not image_url.startswith("http"):
                continue
            meta = info.get("extmetadata") or {}
            return PlaceImage(
                image_url=image_url,
                source="wikimedia_commons",
                title=title,
                license=_meta_value(meta, "LicenseShortName"),
                creator=_strip_html(_meta_value(meta, "Artist")),
                page_url=str(info.get("descriptionurl") or "") or None,
            )
        return None

    async def _fetch_openverse(self, args: PlaceImageInput) -> PlaceImage | None:
        query = _search_query(args)
        response = await self._get_client().get(
            _OPENVERSE_API,
            params={"q": query, "page_size": 5, "license_type": "commercial,modification"},
        )
        response.raise_for_status()
        results = response.json().get("results", []) or []
        terms = _important_terms(args.name)
        for result in results:
            title = str(result.get("title") or "")
            if not _looks_relevant(title, terms):
                continue
            image_url = result.get("thumbnail") or result.get("url")
            if not isinstance(image_url, str) or not image_url.startswith("http"):
                continue
            return PlaceImage(
                image_url=image_url,
                source=f"openverse:{result.get('source') or 'unknown'}",
                title=title,
                license=str(result.get("license") or "") or None,
                creator=str(result.get("creator") or "") or None,
                page_url=str(result.get("foreign_landing_url") or "") or None,
            )
        return None


def _search_query(args: PlaceImageInput) -> str:
    parts = [args.name, args.location_hint, args.category]
    return " ".join(p for p in parts if p).strip()


def _fixture_keys(args: PlaceImageInput) -> tuple[str, ...]:
    keys = [cache_key(args.name, args.location_hint)]
    if args.category:
        keys.append(cache_key(args.name, args.category))
    keys.append(cache_key(args.name))
    lower = _search_query(args).lower()
    if "tokyo" in lower and "ramen" in lower:
        keys.append("tokyo_ramen")

    unique: list[str] = []
    for item in keys:
        if item not in unique:
            unique.append(item)
    return tuple(unique)


def _important_terms(name: str) -> tuple[str, ...]:
    stop = {"the", "and", "of", "at", "in", "store", "restaurant", "ramen"}
    terms = []
    for raw in name.replace("(", " ").replace(")", " ").replace("-", " ").split():
        term = raw.strip().lower()
        if len(term) < _MIN_RELEVANT_TERM_CHARS or term in stop:
            continue
        terms.append(term)
    return tuple(terms[:4])


def _looks_relevant(title: str, terms: tuple[str, ...]) -> bool:
    if not terms:
        return True
    haystack = title.lower()
    return any(term in haystack for term in terms)


def _meta_value(meta: dict[str, Any], key: str) -> str | None:
    raw = meta.get(key)
    if isinstance(raw, dict) and isinstance(raw.get("value"), str):
        return raw["value"]
    return None


def _strip_html(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = html.unescape(value)
    cleaned = re.sub(r"<[^>]*>", " ", cleaned)
    cleaned = " ".join(cleaned.split())
    return cleaned[:200]
