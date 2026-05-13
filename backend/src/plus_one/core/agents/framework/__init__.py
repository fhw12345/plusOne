"""Custom agent framework — cycle + skill + tool primitives.

This package contains the *generic* multi-agent machinery (cycle main loop,
skill registry, tool registry, type protocols). It does NOT contain any
Plus One domain logic — agents that use the framework live in
``plus_one.agents`` (Producer / Joiner / Controller) once they exist.

See ADR-002 for the rationale on building a custom framework instead of
using LangGraph.
"""

from plus_one.core.agents.framework.cycle import (
    ControllerFn,
    CycleResult,
    JoinerFn,
    ProducerFn,
    ProgressEvent,
    run_cycle,
    stream_cycle,
)
from plus_one.core.agents.framework.errors import (
    AgentError,
    CycleAbortedError,
    SkillNotFoundError,
    ToolNotFoundError,
)
from plus_one.core.agents.framework.skills import (
    Skill,
    SkillRegistry,
    parse_skill_file,
)
from plus_one.core.agents.framework.tools import (
    Tool,
    ToolCall,
    ToolRegistry,
    ToolResult,
    run_tool_calls,
)
from plus_one.core.agents.framework.types import (
    AgentContext,
    Decision,
    PhaseResult,
)

__all__ = [
    "AgentContext",
    "AgentError",
    "ControllerFn",
    "CycleAbortedError",
    "CycleResult",
    "Decision",
    "JoinerFn",
    "PhaseResult",
    "ProducerFn",
    "ProgressEvent",
    "Skill",
    "SkillNotFoundError",
    "SkillRegistry",
    "Tool",
    "ToolCall",
    "ToolNotFoundError",
    "ToolRegistry",
    "ToolResult",
    "parse_skill_file",
    "run_cycle",
    "run_tool_calls",
    "stream_cycle",
]
