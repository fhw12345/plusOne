"""Shared Pydantic request/response models for profile + companions APIs.

These mirror the JSONB shapes accepted by the ``Profile`` and ``Companion``
ORM rows, but enforce bounds + nested shape at the HTTP boundary. The DB
layer stays schemaless on purpose (see PRD §3 — JSONB rationale).

``extra="forbid"`` on every model is intentional: rejects unknown keys so
a future field rename can't silently swallow client typos.
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003 — used at runtime as Pydantic field type
from uuid import UUID  # noqa: TC003 — used at runtime as Pydantic field type

from pydantic import BaseModel, ConfigDict, Field


class Demographics(BaseModel):
    model_config = ConfigDict(extra="forbid")
    age_range: str | None = Field(default=None, max_length=20)
    language: str | None = Field(default=None, max_length=10)


class TravelStyle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    budget_sensitivity: str | None = Field(default=None, max_length=20)
    pace: str | None = Field(default=None, max_length=20)
    comfort: str | None = Field(default=None, max_length=20)


class ExplicitPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")
    loves: list[str] = Field(default_factory=list, max_length=50)
    hates: list[str] = Field(default_factory=list, max_length=50)


class VisitedCity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    city: str = Field(min_length=1, max_length=100)
    year: int = Field(ge=1900, le=2100)
    rating: int | None = Field(default=None, ge=1, le=5)
    feedback: str | None = Field(default=None, max_length=500)


class CompanionConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dietary: list[str] = Field(default_factory=list, max_length=20)
    mobility: str | None = Field(default=None, max_length=50)
    # km / day
    max_walking: int | None = Field(default=None, ge=0, le=100)


# === Profile ============================================================


class ProfileResponse(BaseModel):
    """GET /api/profile response.

    ``implicit_preferences`` is intentionally omitted — it's a v2 server-only
    column not consumer-readable in MVP.
    """

    model_config = ConfigDict(extra="forbid")

    demographics: Demographics
    travel_style: TravelStyle
    explicit_preferences: ExplicitPreferences
    visited_cities: list[VisitedCity]


class ProfileUpdateBody(BaseModel):
    """PUT /api/profile body — whole-document semantics.

    Client sends the full profile object; server upserts. ``extra="forbid"``
    rejects attempts to write ``implicit_preferences`` from the client.
    """

    model_config = ConfigDict(extra="forbid")

    demographics: Demographics = Field(default_factory=Demographics)
    travel_style: TravelStyle = Field(default_factory=TravelStyle)
    explicit_preferences: ExplicitPreferences = Field(default_factory=ExplicitPreferences)
    visited_cities: list[VisitedCity] = Field(default_factory=list, max_length=100)


# === Companion ==========================================================


class CompanionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    name: str
    explicit_preferences: ExplicitPreferences
    constraints: CompanionConstraints
    created_at: datetime
    updated_at: datetime


class CompanionsListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    companions: list[CompanionResponse]


class CompanionCreateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    explicit_preferences: ExplicitPreferences = Field(default_factory=ExplicitPreferences)
    constraints: CompanionConstraints = Field(default_factory=CompanionConstraints)


class CompanionUpdateBody(BaseModel):
    """PUT /api/companions/{id} body — whole-document semantics, no id field."""

    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    explicit_preferences: ExplicitPreferences = Field(default_factory=ExplicitPreferences)
    constraints: CompanionConstraints = Field(default_factory=CompanionConstraints)
