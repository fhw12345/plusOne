"""Tool system — typed external operations agents can call.

A *tool* is a typed async callable an agent can invoke (e.g. ``reddit_search``,
``google_places_lookup``). Tools self-report their concurrency safety so the
scheduler can dispatch independent calls in parallel without a centralized
table.

Each tool defines:
  - ``name``: unique id used by skills' ``allowed_tools`` and by registry lookup
  - ``input_schema``: Pydantic model — single source of truth for arg validation
  - ``is_concurrency_safe``: hint for the scheduler (read-only / no shared state)
  - ``execute``: the actual async work

The framework does not run tools; it gives agents a registry. An agent
batches its planned tool calls and hands them to :func:`run_tool_calls`,
which separates safe/unsafe, runs safe ones concurrently and unsafe ones
sequentially.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from plus_one.core.agents.framework.errors import ToolNotFoundError

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

TInput = TypeVar("TInput", bound=BaseModel)
TOutput = TypeVar("TOutput")


class ToolResult[TOut](BaseModel):
    """Wrapped output of a tool call."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    tool: str
    ok: bool = True
    output: TOut | None = None
    error: str | None = None
    notes: str = Field(default="", description="Free-text trace for observability")


@runtime_checkable
class Tool(Protocol[TInput, TOutput]):
    """A typed external operation an agent can call."""

    name: str
    input_schema: type[TInput]
    is_concurrency_safe: bool

    async def execute(self, args: TInput) -> ToolResult[TOutput]:
        """Run the tool. Implementations must catch their own errors and
        return a ``ToolResult(ok=False, error=...)`` instead of raising,
        so the scheduler doesn't have to choose between fail-fast and
        partial-result semantics."""
        ...


class ToolCall(BaseModel):
    """A pending invocation of a tool with concrete args.

    Agents construct these from their plan, and the scheduler runs them.
    Args are kept as a dict here (not the Pydantic model) so that the
    ToolCall itself is JSON-serializable for tracing without circular
    type concerns; the registry validates against the tool's input_schema
    at dispatch time.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    tool: str
    args: dict[str, Any]


class ToolRegistry:
    """Holds the set of tools available to a run.

    Construction is decoupled from registration so test fixtures can build
    tiny registries with just the tools the test cares about.
    """

    def __init__(self) -> None:
        self._tools: dict[str, Tool[Any, Any]] = {}

    def register(self, tool: Tool[Any, Any], *, override: bool = False) -> None:
        """Register a tool. Duplicate names raise unless ``override`` is True."""
        if tool.name in self._tools and not override:
            raise ValueError(
                f"Tool {tool.name!r} already registered; pass override=True to replace"
            )
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool[Any, Any]:
        """Return the tool with ``name`` or raise :class:`ToolNotFoundError`."""
        if name not in self._tools:
            raise ToolNotFoundError(name)
        return self._tools[name]

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name in self._tools

    def __iter__(self) -> Iterator[Tool[Any, Any]]:
        return iter(self._tools.values())

    def __len__(self) -> int:
        return len(self._tools)

    def names(self) -> list[str]:
        return sorted(self._tools.keys())

    async def dispatch(self, call: ToolCall) -> ToolResult[Any]:
        """Validate args + run a single tool call.

        Returns a ToolResult with ``ok=False`` for either a validation
        failure or an exception raised by the tool. We never re-raise
        from here — callers want partial-result semantics across a batch.
        """
        try:
            tool = self.get(call.tool)
        except ToolNotFoundError as exc:
            return ToolResult(tool=call.tool, ok=False, error=str(exc))

        try:
            args = tool.input_schema.model_validate(call.args)
        except Exception as exc:
            # Surface any validation error to the caller as ok=False; the
            # alternative (re-raising) breaks batch dispatch's partial-result
            # contract and forces every caller to wrap each call in try/except.
            return ToolResult(
                tool=call.tool,
                ok=False,
                error=f"input validation failed: {exc}",
            )

        try:
            return await tool.execute(args)
        except Exception as exc:
            # Same rationale as above — tools should already self-handle and
            # return ok=False, but a misbehaving tool that raises is not
            # allowed to bring down a whole batch.
            return ToolResult(
                tool=call.tool,
                ok=False,
                error=f"{type(exc).__name__}: {exc}",
            )


async def run_tool_calls(
    registry: ToolRegistry,
    calls: Iterable[ToolCall],
) -> list[ToolResult[Any]]:
    """Execute a batch of tool calls.

    Concurrency-safe tools run in parallel via :func:`asyncio.gather`;
    unsafe tools run sequentially in submission order. Order in the
    returned list mirrors submission order so callers can correlate
    results with their original plan.
    """
    calls_list = list(calls)
    if not calls_list:
        return []

    safe_indices: list[int] = []
    unsafe_indices: list[int] = []
    for i, call in enumerate(calls_list):
        try:
            tool = registry.get(call.tool)
        except ToolNotFoundError:
            # Treat unknown as unsafe — preserves order, dispatch will
            # report the error.
            unsafe_indices.append(i)
            continue
        (safe_indices if tool.is_concurrency_safe else unsafe_indices).append(i)

    results: list[ToolResult[Any] | None] = [None] * len(calls_list)

    if safe_indices:
        safe_results = await asyncio.gather(
            *(registry.dispatch(calls_list[i]) for i in safe_indices)
        )
        for i, res in zip(safe_indices, safe_results, strict=True):
            results[i] = res

    for i in unsafe_indices:
        results[i] = await registry.dispatch(calls_list[i])

    # Slot-fill is total by construction (every index appeared in exactly one
    # of safe_indices / unsafe_indices). Assert rather than silent-filter so
    # any future regression in the dispatch loop is loud.
    assert all(r is not None for r in results), "internal: some result slot unfilled"
    return [r for r in results if r is not None]
