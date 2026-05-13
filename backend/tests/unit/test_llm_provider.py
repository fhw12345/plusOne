"""Tests for the LLM provider layer (Maestro + role mapping + parsers + mock)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from pydantic import BaseModel

from plus_one.core import llm as llm_pkg
from plus_one.core.llm.maestro_provider import MaestroProvider
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
async def test_real_maestro_provider_refuses_to_instantiate_under_pytest() -> None:
    """Critical guard: prevents tests from accidentally calling real LLM.

    Even if a test bypasses the mock_llm fixture (stale import, missing
    monkeypatch), MaestroProvider raises RuntimeError when sys.modules
    contains pytest. This protects CI from ever burning real tokens.
    """
    with pytest.raises(RuntimeError, match="must not be instantiated under pytest"):
        MaestroProvider(role="conversational")


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
