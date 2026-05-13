"""Core types for the agent framework.

These are framework-internal data shapes that flow between the cycle phases
and into / out of agents. They are deliberately minimal — domain payloads
(e.g. "candidate place", "joined item") are defined by the agents that use
the framework, not here.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Decision(BaseModel):
    """Output of the Controller phase.

    The cycle main loop reads ``should_continue`` and either loops once more
    or returns. ``reasoning`` is for the human reading the trace; ``summary``
    is fed back to the Producer on the next iteration as compressed history.
    """

    should_continue: bool
    reasoning: str = Field(default="", description="Why we made this call")
    summary: str = Field(
        default="",
        description="Compressed history of the cycle so far — fed to next iteration",
    )
    next_focus: str | None = Field(
        default=None,
        description="Optional hint to next Producer about where to look next",
    )


class PhaseResult[TPayload](BaseModel):
    """Result of a single cycle phase (Producer / Joiner / Controller).

    Generic over the payload type so each phase can return its own shape.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    payload: TPayload
    notes: str = Field(default="", description="Free-text trace for observability")


class AgentContext(BaseModel):
    """Per-cycle execution context shared across phases.

    Holds the user query, a running summary of what's happened, and arbitrary
    scratchpad state. Each cycle iteration mutates ``depth`` and ``summary``;
    everything else is generally read-only after construction.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    query: str = Field(description="The user's original input that started the cycle")
    depth: int = Field(default=0, ge=0, description="Iteration count, 0 on entry")
    max_depth: int = Field(default=4, ge=1, description="Hard cap on iterations")
    summary: str = Field(
        default="",
        description="Running summary; updated by Controller each iteration",
    )
    scratch: dict[str, Any] = Field(
        default_factory=dict,
        description="Free-form per-cycle storage for agents",
    )

    def at_depth_cap(self) -> bool:
        return self.depth >= self.max_depth
