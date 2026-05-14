"""Google Places — fixture-backed factual lookup for v1.

Returns address / rating / price level / opening hours summary for places
that match a text query within a region. Live API wiring deferred.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from plus_one.config import settings
from plus_one.core.agents.framework.tools import ToolResult
from plus_one.core.tools._cache import cache_key, load_json_fixture


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
    """Fixture-backed Google Places text-search."""

    name: ClassVar[str] = "google_places_search"
    input_schema: ClassVar[type[BaseModel]] = GooglePlacesSearchInput
    is_concurrency_safe: ClassVar[bool] = True

    def __init__(self, fixtures_dir: Path | None = None) -> None:
        self._fixtures_dir = (fixtures_dir or settings.fixtures_dir) / "google_places"

    async def execute(self, args: GooglePlacesSearchInput) -> ToolResult[list[Place]]:
        key = cache_key(args.query, args.location_hint)
        raw = load_json_fixture(self._fixtures_dir, key)
        places = [Place.model_validate(item) for item in raw[: args.limit]]
        return ToolResult(
            tool=self.name,
            output=places,
            notes=f"loaded {len(places)} places from cache key {key!r}",
        )
