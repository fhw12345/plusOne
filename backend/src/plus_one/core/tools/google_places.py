"""Google Places — fixture-backed by default, ``googlemaps`` client in real mode.

Mode is resolved per-call via ``get_tools_mode()`` (see ``_mode.py``).
Real-mode behavior:

  * Lazy ``googlemaps.Client`` construction in ``_get_client`` — fails
    loud at ``__init__`` if ``GOOGLE_PLACES_API_KEY`` is missing (via
    ``require_env``).
  * Cache-or-fetch: look up DB cache first, fall back to the
    ``places(query=, location=, language=)`` text search (wrapped in
    ``asyncio.to_thread`` since the ``googlemaps`` client is sync), then
    write the response back to the cache for TTL (30d, set in
    ``_cache_db.py::_TTL_BY_SOURCE``).

Fixture mode is the existing behavior — unchanged for CI / e2e / dev.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any, ClassVar

import structlog
from pydantic import BaseModel, ConfigDict, Field

from plus_one.config import settings
from plus_one.core.agents.framework.tools import ToolResult
from plus_one.core.tools._cache import cache_key, load_json_fixture
from plus_one.core.tools._cache_db import get_cached, put_cached
from plus_one.core.tools._mode import get_tools_mode, require_env

logger = structlog.get_logger()


class Place(BaseModel):
    """A Google Places search result, slimmed down."""

    model_config = ConfigDict(frozen=True)

    place_id: str
    name: str
    formatted_address: str
    rating: float | None = None
    user_ratings_total: int | None = None
    price_level: int | None = None  # 0..4 per Google's PriceLevel enum
    types: tuple[str, ...] = ()
    google_maps_url: str | None = None


class GooglePlacesSearchInput(BaseModel):
    """Args for ``google_places_search``."""

    query: str = Field(min_length=1, max_length=200)
    location_hint: str = Field(default="", description="e.g. 'Tokyo, Japan'")
    limit: int = Field(default=20, ge=1, le=60)


class GooglePlacesSearchTool:
    """Google Places text-search.

    Cache key is built from ``query`` + ``location_hint`` so a fixture
    file ``tokyo_ramen__tokyo_japan.json`` services the query "tokyo
    ramen" with location_hint "Tokyo, Japan". The same cache key is also
    used as the DB cache lookup key in real mode.
    """

    name: ClassVar[str] = "google_places_search"
    input_schema: ClassVar[type[BaseModel]] = GooglePlacesSearchInput
    is_concurrency_safe: ClassVar[bool] = True

    _SOURCE: ClassVar[str] = "google_places"

    def __init__(self, fixtures_dir: Path | None = None) -> None:
        self._fixtures_dir = (fixtures_dir or settings.fixtures_dir) / "google_places"
        # In real mode, fail loud at construction if API key is missing.
        # The client itself is built lazily so fixture mode (CI / e2e /
        # dev) never imports googlemaps needlessly.
        require_env("GOOGLE_PLACES_API_KEY", tool=self.name)
        self._client: Any | None = None

    # === fixture mode (unchanged behavior) ===========================

    def _execute_fixture(self, args: GooglePlacesSearchInput) -> ToolResult[list[Place]]:
        key = cache_key(args.query, args.location_hint)
        raw = load_json_fixture(self._fixtures_dir, key)
        places = [Place.model_validate(item) for item in raw[: args.limit]]
        return ToolResult(
            tool=self.name,
            output=places,
            notes=f"loaded {len(places)} places from cache key {key!r}",
        )

    # === real mode ===================================================

    def _get_client(self) -> Any:
        """Lazily build a ``googlemaps.Client``. Cached on the instance."""
        if self._client is not None:
            return self._client
        # Local import so fixture-mode imports stay cheap and googlemaps
        # stays an optional runtime dep.
        import googlemaps  # noqa: PLC0415

        self._client = googlemaps.Client(key=os.environ["GOOGLE_PLACES_API_KEY"])
        return self._client

    def _fetch_from_places_sync(
        self, query: str, location_hint: str, limit: int
    ) -> list[dict[str, Any]]:
        """Blocking ``googlemaps`` call. Always run via ``asyncio.to_thread``.

        We use the Places text-search endpoint; ``location_hint`` is
        appended to the query as a soft bias since the textsearch API
        accepts free-form location text. We slice to ``limit`` at the
        end so the cache row also stays bounded.
        """
        client = self._get_client()
        full_query = f"{query} {location_hint}".strip() if location_hint else query
        response: dict[str, Any] = client.places(query=full_query, language="en")
        results = response.get("results", []) or []
        out: list[dict[str, Any]] = []
        for r in results[:limit]:
            place_id = str(r.get("place_id", ""))
            maps_url = (
                f"https://www.google.com/maps/place/?q=place_id:{place_id}" if place_id else None
            )
            out.append(
                {
                    "place_id": place_id,
                    "name": str(r.get("name", "")),
                    "formatted_address": str(r.get("formatted_address", "")),
                    "rating": (float(r["rating"]) if r.get("rating") is not None else None),
                    "user_ratings_total": (
                        int(r["user_ratings_total"])
                        if r.get("user_ratings_total") is not None
                        else None
                    ),
                    "price_level": (
                        int(r["price_level"]) if r.get("price_level") is not None else None
                    ),
                    "types": tuple(str(t) for t in (r.get("types") or ())),
                    "google_maps_url": maps_url,
                }
            )
        return out

    async def _execute_real(self, args: GooglePlacesSearchInput) -> ToolResult[list[Place]]:
        key = cache_key(args.query, args.location_hint)
        cached = await get_cached(self._SOURCE, key)
        if cached is not None:
            places = [Place.model_validate(item) for item in cached[: args.limit]]
            logger.info("google_places_cache_hit", key=key, count=len(places))
            return ToolResult(
                tool=self.name,
                output=places,
                notes=f"cache hit {key!r} -> {len(places)} places",
            )

        try:
            raw = await asyncio.to_thread(
                self._fetch_from_places_sync,
                args.query,
                args.location_hint,
                args.limit,
            )
        except Exception as exc:
            logger.warning("google_places_fetch_failed", key=key, error=str(exc))
            return ToolResult(
                tool=self.name,
                ok=False,
                output=None,
                error=f"google places fetch failed: {exc}",
            )

        await put_cached(self._SOURCE, key, raw)
        places = [Place.model_validate(item) for item in raw[: args.limit]]
        return ToolResult(
            tool=self.name,
            output=places,
            notes=f"fetched {len(places)} places via googlemaps, key {key!r}",
        )

    async def execute(self, args: GooglePlacesSearchInput) -> ToolResult[list[Place]]:
        if get_tools_mode() == "fixture":
            return self._execute_fixture(args)
        return await self._execute_real(args)
