"""Foursquare Places — fixture-backed by default, ``httpx`` client in real mode.

Mode is resolved per-call via ``get_tools_mode()`` (see ``_mode.py``).
Real-mode behavior:

  * Lazy ``httpx.AsyncClient`` construction in ``_get_client`` — fails
    loud at ``__init__`` if ``FOURSQUARE_API_KEY`` is missing (via
    ``require_env``).
  * Cache-or-fetch: look up DB cache first, fall back to the Foursquare
    ``/places/search`` HTTPS endpoint, then write the response back to
    the cache for TTL (30d, set in ``_cache_db.py::_TTL_BY_SOURCE``).

Fixture mode is the existing behavior — unchanged for CI / e2e / dev.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, ClassVar

import httpx
import structlog
from pydantic import BaseModel, ConfigDict, Field

from plus_one.config import settings
from plus_one.core.agents.framework.tools import ToolResult
from plus_one.core.tools._cache import cache_key, load_json_fixture
from plus_one.core.tools._cache_db import get_cached, put_cached
from plus_one.core.tools._mode import get_tools_mode, require_env

logger = structlog.get_logger()


_FSQ_SEARCH_URL = "https://places-api.foursquare.com/places/search"
_FSQ_API_VERSION = "2025-06-17"


class Place(BaseModel):
    """A Foursquare Places search result, slimmed down."""

    model_config = ConfigDict(frozen=True)

    place_id: str
    name: str
    formatted_address: str

    # Foursquare-native (free tier)
    latitude: float | None = None
    longitude: float | None = None
    categories: tuple[str, ...] = ()
    distance_m: int | None = None

    # Legacy fields — permanently None on Foursquare basic tier.
    rating: float | None = None
    user_ratings_total: int | None = None
    price_level: int | None = None

    # Provider-neutral
    types: tuple[str, ...] = ()
    external_url: str | None = None


class PlacesSearchInput(BaseModel):
    """Args for ``places_search``."""

    query: str = Field(min_length=1, max_length=200)
    location_hint: str = Field(default="", description="e.g. 'Tokyo, Japan'")
    limit: int = Field(default=20, ge=1, le=60)


class FoursquarePlacesSearchTool:
    """Foursquare Places text-search.

    Cache key is built from ``query`` + ``location_hint`` so a fixture
    file ``tokyo_ramen__tokyo_japan.json`` services the query "tokyo
    ramen" with location_hint "Tokyo, Japan". The same cache key is also
    used as the DB cache lookup key in real mode.
    """

    name: ClassVar[str] = "places_search"
    input_schema: ClassVar[type[BaseModel]] = PlacesSearchInput
    is_concurrency_safe: ClassVar[bool] = True

    _SOURCE: ClassVar[str] = "foursquare"

    def __init__(self, fixtures_dir: Path | None = None) -> None:
        self._fixtures_dir = (fixtures_dir or settings.fixtures_dir) / "foursquare"
        # In real mode, fail loud at construction if API key is missing.
        # The client itself is built lazily so fixture mode (CI / e2e /
        # dev) never opens a TCP socket needlessly.
        require_env("FOURSQUARE_API_KEY", tool=self.name)
        self._client: httpx.AsyncClient | None = None

    # === fixture mode (unchanged behavior) ===========================

    def _execute_fixture(self, args: PlacesSearchInput) -> ToolResult[list[Place]]:
        key = cache_key(args.query, args.location_hint)
        raw = load_json_fixture(self._fixtures_dir, key)
        places = [Place.model_validate(item) for item in raw[: args.limit]]
        return ToolResult(
            tool=self.name,
            output=places,
            notes=f"loaded {len(places)} places from cache key {key!r}",
        )

    # === real mode ===================================================

    def _get_client(self) -> httpx.AsyncClient:
        """Lazily build an ``httpx.AsyncClient``. Cached on the instance."""
        if self._client is not None:
            return self._client
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=5.0))
        return self._client

    async def _fetch_from_api(self, args: PlacesSearchInput) -> list[dict[str, Any]]:
        """Call Foursquare ``/places/search`` and map results to ``Place`` dicts.

        ``location_hint`` is forwarded as the ``near`` query param when
        non-empty; we never send an empty ``near`` (FSQ would 400). We
        slice to ``args.limit`` at the end so the cache row also stays
        bounded.
        """
        params: dict[str, Any] = {"query": args.query, "limit": args.limit}
        if args.location_hint:
            params["near"] = args.location_hint

        headers = {
            "Authorization": f"Bearer {os.environ['FOURSQUARE_API_KEY']}",
            "X-Places-Api-Version": _FSQ_API_VERSION,
            "Accept": "application/json",
        }

        client = self._get_client()
        response = await client.get(_FSQ_SEARCH_URL, params=params, headers=headers)
        response.raise_for_status()

        payload = response.json()
        results = payload.get("results", []) or []
        out: list[dict[str, Any]] = []
        for r in results[: args.limit]:
            fsq_id = r.get("fsq_place_id")
            location = r.get("location") or {}
            categories_raw = r.get("categories") or []
            categories = tuple(
                str(c.get("short_name", ""))
                for c in categories_raw
                if c.get("short_name")
            )
            external_url = f"https://foursquare.com/v/{fsq_id}" if fsq_id else None
            out.append(
                {
                    "place_id": str(fsq_id or ""),
                    "name": str(r.get("name", "")),
                    "formatted_address": str(location.get("formatted_address", "")),
                    "latitude": (
                        float(r["latitude"]) if r.get("latitude") is not None else None
                    ),
                    "longitude": (
                        float(r["longitude"]) if r.get("longitude") is not None else None
                    ),
                    "categories": categories,
                    "distance_m": (
                        int(r["distance"]) if r.get("distance") is not None else None
                    ),
                    "rating": None,
                    "user_ratings_total": None,
                    "price_level": None,
                    "types": categories,
                    "external_url": external_url,
                }
            )
        return out

    async def _execute_real(self, args: PlacesSearchInput) -> ToolResult[list[Place]]:
        key = cache_key(args.query, args.location_hint)
        cached = await get_cached(self._SOURCE, key)
        if cached is not None:
            places = [Place.model_validate(item) for item in cached[: args.limit]]
            logger.info("foursquare_cache_hit", key=key, count=len(places))
            return ToolResult(
                tool=self.name,
                output=places,
                notes=f"cache hit {key!r} -> {len(places)} places",
            )

        try:
            raw = await self._fetch_from_api(args)
        except Exception as exc:
            logger.warning("foursquare_fetch_failed", key=key, error=str(exc))
            return ToolResult(
                tool=self.name,
                ok=False,
                output=None,
                error=f"foursquare places fetch failed: {exc}",
            )

        await put_cached(self._SOURCE, key, raw)
        places = [Place.model_validate(item) for item in raw[: args.limit]]
        return ToolResult(
            tool=self.name,
            output=places,
            notes=f"fetched {len(places)} places via foursquare, key {key!r}",
        )

    async def execute(self, args: PlacesSearchInput) -> ToolResult[list[Place]]:
        if get_tools_mode() == "fixture":
            return self._execute_fixture(args)
        return await self._execute_real(args)
