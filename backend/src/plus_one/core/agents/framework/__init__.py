"""Custom agent framework — cycle + skill + tool primitives.

This package contains the *generic* multi-agent machinery (cycle main loop,
skill registry, tool registry, type protocols). It does NOT contain any
Plus One domain logic — agents that use the framework live in
``plus_one.agents`` (Producer / Joiner / Controller) once they exist.

See ADR-002 for the rationale on building a custom framework instead of
using LangGraph.
"""

from plus_one.core.agents.framework.errors import (
    AgentError,
    CycleAbortedError,
    SkillNotFoundError,
    ToolNotFoundError,
)
from plus_one.core.agents.framework.skills import Skill, SkillRegistry
from plus_one.core.agents.framework.tools import Tool, ToolRegistry, ToolResult
from plus_one.core.agents.framework.types import (
    AgentContext,
    Decision,
    PhaseResult,
)

__all__ = [
    "AgentContext",
    "AgentError",
    "CycleAbortedError",
    "Decision",
    "PhaseResult",
    "Skill",
    "SkillNotFoundError",
    "SkillRegistry",
    "Tool",
    "ToolNotFoundError",
    "ToolRegistry",
    "ToolResult",
]
