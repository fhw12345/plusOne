"""Itinerary scheduler models (batch-3a).

The scheduler LLM produces an ``ItineraryPlan`` that groups approved
``JoinedItem`` indices into days x periods. Models are deliberately
flat / JSON-friendly so they round-trip cleanly through the Report
``content.day_plan`` JSONB column. See ``docs/prd/trip-detail-itinerary.md``.
"""

from __future__ import annotations

from datetime import date  # noqa: TC003 — runtime use as Pydantic field annotation
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class DaySlot(BaseModel):
    """One item placement on one day at one period."""

    period: Literal["morning", "afternoon", "evening", "late_night"]
    # Index into the ORIGINAL items[] list (not the eligible-only filtered
    # subset). The scheduler prompt is fed indices verbatim so this stays
    # consistent end-to-end.
    item_index: int = Field(ge=0)
    note: str | None = None


class DayPlan(BaseModel):
    """One calendar day's slate of items."""

    day_index: int = Field(ge=1)
    date: date | None = None
    theme: str | None = None
    slots: list[DaySlot] = Field(default_factory=list)


class ItineraryPlan(BaseModel):
    """Full multi-day plan returned by the scheduler LLM."""

    days: list[DayPlan] = Field(default_factory=list)

    @model_validator(mode="after")
    def _no_duplicate_item_indices(self) -> ItineraryPlan:
        """Reject plans where the same ``item_index`` appears twice.

        The scheduler prompt instructs the LLM that every eligible item
        appears in exactly one slot. Duplicates almost always indicate
        the model double-counted; treating it as a validation error lets
        the runner fall back to the flat view (AC-12).
        """
        seen: set[int] = set()
        for day in self.days:
            for slot in day.slots:
                if slot.item_index in seen:
                    raise ValueError(f"duplicate item_index {slot.item_index} across slots")
                seen.add(slot.item_index)
        return self
