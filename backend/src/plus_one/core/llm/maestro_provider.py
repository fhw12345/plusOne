"""Maestro LLM provider — every LLM call in Plus One goes through here.

Agent Maestro is an Anthropic-API-compatible gateway that proxies to multiple
underlying vendors (Anthropic / OpenAI / Google). By speaking the Anthropic
wire protocol regardless of upstream vendor, we get:

  - One SDK (``langchain-anthropic``) for everything
  - Cross-vendor failover via configuration only
  - Per-role model selection (see ``roles.py``)
  - Internal: token-unlimited, so we don't gate by cost
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any

import structlog
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel

from plus_one.config import settings
from plus_one.core.llm.parsers import parse_with_fallback
from plus_one.core.llm.provider import LLMProvider, Message, Response, Usage
from plus_one.core.llm.roles import resolve_model

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from langchain_core.runnables import Runnable

logger = structlog.get_logger()


def _to_langchain_messages(system: str, messages: list[Message]) -> list[BaseMessage]:
    """Convert Plus One ``Message`` list (+ system) to LangChain message objects."""
    lc: list[BaseMessage] = [SystemMessage(content=system)] if system else []
    for m in messages:
        if m.role == "user":
            lc.append(HumanMessage(content=m.content))
        elif m.role == "assistant":
            lc.append(AIMessage(content=m.content))
    return lc


class MaestroProvider(LLMProvider):
    """LLM provider routed through Agent Maestro.

    Created per-role. Construct via :func:`get_llm_provider` instead of
    instantiating directly — the factory caches one instance per role.
    """

    name = "maestro"

    def __init__(
        self,
        *,
        role: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        streaming: bool = False,
    ) -> None:
        # Hard guard: if pytest is the running interpreter, refuse to construct
        # a real Maestro client. The intended path under tests is the mock
        # provider injected via tests/conftest.py — if this guard fires it means
        # a test is bypassing the mock (e.g. via stale module-level imports).
        if "pytest" in sys.modules:
            raise RuntimeError(
                "MaestroProvider must not be instantiated under pytest. "
                "Tests should depend on the `mock_llm` fixture and call "
                "get_llm_provider through the patched namespace. See "
                "tests/conftest.py."
            )
        self.role = role
        self.model = resolve_model(role)
        self._chat = ChatAnthropic(
            model=self.model,
            temperature=temperature
            if temperature is not None
            else settings.llm_default_temperature,
            max_tokens_to_sample=max_tokens or settings.llm_default_max_tokens,
            streaming=streaming,
            anthropic_api_url=settings.maestro_base_url,
            anthropic_api_key=settings.maestro_auth_token,
        )

    async def complete[TOutput: BaseModel](
        self,
        *,
        system: str,
        messages: list[Message],
        response_model: type[TOutput] | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.7,
    ) -> Response[TOutput]:
        """One-shot completion. For streaming use :meth:`astream`."""
        lc_messages = _to_langchain_messages(system, messages)

        # bind() returns a new Runnable with overridden params; type annotation
        # avoids mypy treating the rebind as an incompatible assignment.
        chat: Runnable[Any, AIMessage] = self._chat.bind(temperature=temperature)
        if max_tokens is not None:
            chat = chat.bind(max_tokens=max_tokens)

        logger.info(
            "maestro_complete",
            role=self.role,
            model=self.model,
            n_messages=len(messages),
            temperature=temperature,
        )

        ai_msg = await chat.ainvoke(lc_messages)
        text = ai_msg.content if isinstance(ai_msg.content, str) else str(ai_msg.content)

        usage_meta = getattr(ai_msg, "usage_metadata", None) or {}
        usage = Usage(
            input_tokens=int(usage_meta.get("input_tokens", 0)),
            output_tokens=int(usage_meta.get("output_tokens", 0)),
        )

        parsed: TOutput | None = None
        if response_model is not None:
            parsed = parse_with_fallback(text, response_model)

        return Response[TOutput](
            text=text,
            parsed=parsed,
            usage=usage,
            model=self.model,
            provider="maestro",
        )

    async def astream(
        self,
        *,
        system: str,
        messages: list[Message],
        max_tokens: int | None = None,
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:
        """Yield response text chunks as they arrive."""
        lc_messages = _to_langchain_messages(system, messages)
        chat: Runnable[Any, AIMessage] = self._chat.bind(temperature=temperature)
        if max_tokens is not None:
            chat = chat.bind(max_tokens=max_tokens)

        async for chunk in chat.astream(lc_messages):
            if chunk.content:
                text = chunk.content if isinstance(chunk.content, str) else str(chunk.content)
                yield text
