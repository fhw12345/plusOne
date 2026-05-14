"""Domain payload types shared across Producer / Joiner / Controller.

These are the actual Plus One payloads (``Candidate``, ``Evidence``,
``JoinedItem``, ``Classification``) that flow through the cycle's
generic ``PhaseResult[T]`` envelope.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# What the Joiner's classification can be. Matches the PRD's "local
# gems vs tourist traps" framing, with two safety hatches:
#   - "neutral" for genuinely-fine-but-not-special places
#   - "insufficient" so the Joiner can defer when evidence is thin
Classification = Literal["local_gem", "tourist_trap", "neutral", "insufficient"]


class Evidence(BaseModel):
    """One supporting source for a Joiner classification."""

    model_config = ConfigDict(frozen=True)

    source: Literal["reddit", "xiaohongshu", "google_places"]
    url: str = Field(description="Permalink back to the original")
    snippet: str = Field(description="Quoted ~1-line excerpt that justifies the classification")
    sentiment: float | None = Field(
        default=None,
        ge=-1.0,
        le=1.0,
        description="-1 (very negative) to 1 (very positive); null for factual sources",
    )
