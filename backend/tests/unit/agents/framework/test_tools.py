"""Tests for the tool registry + concurrency-aware scheduler."""

from __future__ import annotations

import asyncio

import pytest
from pydantic import BaseModel

from plus_one.core.agents.framework.errors import ToolNotFoundError
from plus_one.core.agents.framework.tools import (
    ToolCall,
    ToolRegistry,
    ToolResult,
    run_tool_calls,
)


class _Args(BaseModel):
    msg: str
    delay: float = 0.0


class _SafeEcho:
    """A read-only tool that echoes its input after an optional delay."""

    name = "safe_echo"
    input_schema = _Args
    is_concurrency_safe = True

    async def execute(self, args: _Args) -> ToolResult[str]:
        if args.delay:
            await asyncio.sleep(args.delay)
        return ToolResult(tool=self.name, output=args.msg)


class _UnsafeWriter:
    """A tool that mutates external state (so it must run sequentially)."""

    name = "unsafe_writer"
    input_schema = _Args
    is_concurrency_safe = False

    def __init__(self) -> None:
        self.log: list[str] = []

    async def execute(self, args: _Args) -> ToolResult[int]:
        self.log.append(args.msg)
        return ToolResult(tool=self.name, output=len(self.log))


class _Boom:
    """A tool that raises — scheduler must surface this as ok=False."""

    name = "boom"
    input_schema = _Args
    is_concurrency_safe = True

    async def execute(self, args: _Args) -> ToolResult[str]:
        raise RuntimeError(f"boom on {args.msg}")


@pytest.mark.unit
def test_register_and_get() -> None:
    reg = ToolRegistry()
    t = _SafeEcho()
    reg.register(t)
    assert "safe_echo" in reg
    assert reg.get("safe_echo") is t


@pytest.mark.unit
def test_get_missing_raises() -> None:
    reg = ToolRegistry()
    with pytest.raises(ToolNotFoundError):
        reg.get("nope")


@pytest.mark.unit
def test_register_duplicate_rejected() -> None:
    reg = ToolRegistry()
    reg.register(_SafeEcho())
    with pytest.raises(ValueError, match="already registered"):
        reg.register(_SafeEcho())


@pytest.mark.unit
async def test_dispatch_validates_input_schema() -> None:
    reg = ToolRegistry()
    reg.register(_SafeEcho())
    res = await reg.dispatch(ToolCall(tool="safe_echo", args={"wrong_field": "x"}))
    assert not res.ok
    assert res.error is not None
    assert "validation" in res.error.lower()


@pytest.mark.unit
async def test_dispatch_unknown_tool_returns_error_not_raise() -> None:
    reg = ToolRegistry()
    res = await reg.dispatch(ToolCall(tool="ghost", args={}))
    assert not res.ok
    assert res.error is not None
    assert "ghost" in res.error


@pytest.mark.unit
async def test_dispatch_catches_tool_exception() -> None:
    reg = ToolRegistry()
    reg.register(_Boom())
    res = await reg.dispatch(ToolCall(tool="boom", args={"msg": "hi"}))
    assert not res.ok
    assert res.error is not None
    assert "RuntimeError" in res.error


@pytest.mark.unit
async def test_dispatch_happy_path() -> None:
    reg = ToolRegistry()
    reg.register(_SafeEcho())
    res = await reg.dispatch(ToolCall(tool="safe_echo", args={"msg": "hello"}))
    assert res.ok
    assert res.output == "hello"


@pytest.mark.unit
async def test_run_tool_calls_returns_results_in_submission_order() -> None:
    reg = ToolRegistry()
    reg.register(_SafeEcho())

    calls = [
        ToolCall(tool="safe_echo", args={"msg": "a"}),
        ToolCall(tool="safe_echo", args={"msg": "b"}),
        ToolCall(tool="safe_echo", args={"msg": "c"}),
    ]
    results = await run_tool_calls(reg, calls)
    assert [r.output for r in results] == ["a", "b", "c"]


@pytest.mark.unit
async def test_run_tool_calls_runs_safe_in_parallel() -> None:
    reg = ToolRegistry()
    reg.register(_SafeEcho())

    # If executed sequentially, total wall time would be ~3 * 0.05s = 0.15s.
    # In parallel it should be close to 0.05s. Check it's well below 0.12s.
    calls = [ToolCall(tool="safe_echo", args={"msg": str(i), "delay": 0.05}) for i in range(3)]
    start = asyncio.get_event_loop().time()
    results = await run_tool_calls(reg, calls)
    elapsed = asyncio.get_event_loop().time() - start
    assert all(r.ok for r in results)
    assert elapsed < 0.12, f"safe tools should run in parallel; took {elapsed:.3f}s"


@pytest.mark.unit
async def test_run_tool_calls_runs_unsafe_sequentially_in_order() -> None:
    reg = ToolRegistry()
    writer = _UnsafeWriter()
    reg.register(writer)

    calls = [ToolCall(tool="unsafe_writer", args={"msg": m}) for m in ["x", "y", "z"]]
    results = await run_tool_calls(reg, calls)
    assert [r.output for r in results] == [1, 2, 3]
    assert writer.log == ["x", "y", "z"]


@pytest.mark.unit
async def test_run_tool_calls_mixed_safe_and_unsafe_preserve_submission_order() -> None:
    reg = ToolRegistry()
    reg.register(_SafeEcho())
    reg.register(_UnsafeWriter())

    calls = [
        ToolCall(tool="safe_echo", args={"msg": "a"}),
        ToolCall(tool="unsafe_writer", args={"msg": "b"}),
        ToolCall(tool="safe_echo", args={"msg": "c"}),
    ]
    results = await run_tool_calls(reg, calls)
    # Each result lands in its submission slot regardless of which queue ran it
    assert results[0].output == "a"
    assert results[1].output == 1  # writer log length
    assert results[2].output == "c"


@pytest.mark.unit
async def test_run_tool_calls_empty_returns_empty() -> None:
    reg = ToolRegistry()
    assert await run_tool_calls(reg, []) == []
