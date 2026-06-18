"""Tests for the LLM provider layer (Maestro + role mapping + parsers + mock)."""

from __future__ import annotations

import asyncio
import builtins
from typing import TYPE_CHECKING

import pytest
from pydantic import BaseModel

from plus_one.core import llm as llm_pkg
from plus_one.core.llm.parsers import LLMParseError, parse_with_fallback
from plus_one.core.llm.provider import Message, Response
from plus_one.core.llm.roles import ROLES, list_roles, resolve_model

if TYPE_CHECKING:
    from plus_one.core.llm.testing import MockLLMProvider


class _DemoSchema(BaseModel):
    title: str
    score: int


@pytest.mark.unit
def test_resolve_model_returns_configured_value_for_known_role() -> None:
    for role in list_roles():
        assert resolve_model(role) == ROLES[role]


@pytest.mark.unit
def test_resolve_model_falls_back_for_unknown_role() -> None:
    assert resolve_model("nope_does_not_exist") == ROLES["conversational"]


@pytest.mark.unit
def test_parser_direct_strategy() -> None:
    raw = '{"title": "hello", "score": 7}'
    out = parse_with_fallback(raw, _DemoSchema)
    assert out.title == "hello"
    assert out.score == 7


@pytest.mark.unit
def test_parser_code_fence_strategy() -> None:
    raw = 'Here is the answer:\n```json\n{"title": "hi", "score": 3}\n```\nDone.'
    out = parse_with_fallback(raw, _DemoSchema)
    assert out.title == "hi"


@pytest.mark.unit
def test_parser_brace_match_strategy() -> None:
    raw = 'Sure! {"title": "x", "score": 1} that\'s it.'
    out = parse_with_fallback(raw, _DemoSchema)
    assert out.score == 1


@pytest.mark.unit
def test_parser_raises_on_garbage() -> None:
    with pytest.raises(LLMParseError) as exc:
        parse_with_fallback("totally unparseable nonsense", _DemoSchema)
    assert len(exc.value.attempts) == 3


@pytest.mark.unit
def test_real_maestro_provider_blocked_without_opt_in_env_var(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Critical guard: prevents tests from accidentally calling real LLM.

    Even if a test bypasses the mock_llm fixture (stale import, missing
    monkeypatch), MaestroProvider raises RuntimeError unless the opt-in
    env var PLUS_ONE_ALLOW_REAL_LLM=1 is set. Production entry points
    (main.py lifespan) set it once at startup; tests never do.
    """
    from plus_one.core.llm.maestro_provider import MaestroProvider

    monkeypatch.delenv("PLUS_ONE_ALLOW_REAL_LLM", raising=False)
    with pytest.raises(RuntimeError, match="PLUS_ONE_ALLOW_REAL_LLM"):
        MaestroProvider(role="conversational")


@pytest.mark.unit
def test_real_maestro_provider_constructs_when_opt_in_env_var_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Inverse of the guard test: opt-in actually unblocks construction.

    Without this we couldn't tell whether the guard's negative-case test
    is tautological (always raising for some other reason). This proves
    PLUS_ONE_ALLOW_REAL_LLM=1 is a real toggle, not a placebo.
    """
    real_import = builtins.__import__

    def fail_on_vendor_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "langchain_anthropic" or name.startswith("langchain_anthropic."):
            raise AssertionError("ChatAnthropic must be created lazily on real LLM calls")
        if name == "langchain_core.messages" or name.startswith("langchain_core.messages."):
            raise AssertionError("LangChain messages must be created lazily on real LLM calls")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fail_on_vendor_import)
    monkeypatch.setenv("PLUS_ONE_ALLOW_REAL_LLM", "1")

    from plus_one.core.llm.maestro_provider import MaestroProvider

    # Construction must succeed without importing or building the vendor client;
    # that work is deferred until .complete / .astream.
    provider = MaestroProvider(role="conversational")
    assert provider.role == "conversational"
    assert provider.name == "maestro"


@pytest.mark.unit
def test_stale_import_pattern_still_blocked() -> None:
    """Regression test for the bug PR #1 was originally fixing.

    A test that imports MaestroProvider directly and tries to construct it
    must still hit the guard, even though tests/conftest.py only patches
    the get_llm_provider factory. This is the structural guarantee that
    the mock_llm fixture cannot be silently bypassed.
    """
    # No env var set in test process.
    from plus_one.core.llm.maestro_provider import MaestroProvider

    with pytest.raises(RuntimeError, match="PLUS_ONE_ALLOW_REAL_LLM"):
        MaestroProvider(role="producer_agent")


@pytest.mark.unit
async def test_mock_role_binding_is_race_safe_under_gather(
    mock_llm: MockLLMProvider,
) -> None:
    """Concurrent calls to different roles must NOT bleed into each other.

    Reviewer F2: the prior implementation stored the active role on a
    shared instance attribute, which races under asyncio.gather. The
    ContextVar-based binding fixes this; this test pins the contract.
    """

    async def call_role(role: str) -> str:
        llm = llm_pkg.get_llm_provider(role)
        # Yield to event loop in the middle to maximize interleaving
        response: Response[BaseModel] = await llm.complete(
            system="s",
            messages=[Message(role="user", content=role)],
        )
        return response.text

    # Fan out 10 concurrent calls across 3 roles, repeated.
    roles = ["producer_agent", "joiner_agent", "controller_agent"] * 4
    await asyncio.gather(*(call_role(r) for r in roles))

    # Each role should be recorded the exact number of times we called it,
    # not double-counted under one role due to a race.
    for r in ("producer_agent", "joiner_agent", "controller_agent"):
        assert len(mock_llm.calls_for_role(r)) == roles.count(r), (
            f"role {r}: expected {roles.count(r)} calls, "
            f"got {len(mock_llm.calls_for_role(r))} — race in role binding"
        )


@pytest.mark.unit
async def test_mock_llm_default_response_when_nothing_queued(
    mock_llm: MockLLMProvider,
) -> None:
    llm = llm_pkg.get_llm_provider("producer_agent")
    response: Response[BaseModel] = await llm.complete(
        system="hi",
        messages=[Message(role="user", content="hello")],
    )
    assert "mock response" in response.text
    assert mock_llm.call_count == 1


@pytest.mark.unit
async def test_mock_llm_returns_queued_response_per_role(
    mock_llm: MockLLMProvider,
) -> None:
    mock_llm.queue_response(
        role="producer_agent",
        text='{"title": "ramen", "score": 9}',
        parsed_data={"title": "ramen", "score": 9},
    )

    llm = llm_pkg.get_llm_provider("producer_agent")
    response: Response[_DemoSchema] = await llm.complete(
        system="prod",
        messages=[Message(role="user", content="...")],
        response_model=_DemoSchema,
    )
    assert response.parsed is not None
    assert response.parsed.title == "ramen"
    assert response.parsed.score == 9

    # A call to a different role gets default, not the queued one
    llm2 = llm_pkg.get_llm_provider("controller_agent")
    response2: Response[BaseModel] = await llm2.complete(
        system="ctl",
        messages=[Message(role="user", content="...")],
    )
    assert "mock response" in response2.text

    assert len(mock_llm.calls_for_role("producer_agent")) == 1
    assert len(mock_llm.calls_for_role("controller_agent")) == 1
