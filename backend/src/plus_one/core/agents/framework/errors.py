"""Errors raised by the agent framework.

All framework-level errors derive from :class:`AgentError` so callers can
catch the family. Domain-level agent errors should subclass
:class:`AgentError` too.
"""

from __future__ import annotations


class AgentError(Exception):
    """Base class for framework + agent errors."""


class SkillNotFoundError(AgentError):
    """Requested skill is not registered."""

    def __init__(self, name: str) -> None:
        super().__init__(f"Skill not found: {name!r}")
        self.name = name


class ToolNotFoundError(AgentError):
    """Requested tool is not registered."""

    def __init__(self, name: str) -> None:
        super().__init__(f"Tool not found: {name!r}")
        self.name = name


class CycleAbortedError(AgentError):
    """The cycle main loop was stopped by a non-progress signal.

    Examples:
      - Producer returned no candidates
      - Controller decided "no value in continuing" before the depth cap
      - A user-supplied stop signal fired

    Distinct from a normal "controller said stop, results are valid" exit:
    this means the cycle did not produce a usable result.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"Cycle aborted: {reason}")
        self.reason = reason
