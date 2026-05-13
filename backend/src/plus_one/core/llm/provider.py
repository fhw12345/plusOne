"""LLM provider Protocol — the only LLM interface agent code should depend on."""

from __future__ import annotations

from typing import Generic, Literal, Protocol, TypeVar

from pydantic import BaseModel

TOutput = TypeVar("TOutput", bound=BaseModel)


class Message(BaseModel):
    """One message in a chat exchange."""

    role: Literal["user", "assistant"]
    content: str


class Usage(BaseModel):
    """Token + cost accounting for one LLM call."""

    input_tokens: int
    output_tokens: int
    cost_usd: float | None = None


class Response(BaseModel, Generic[TOutput]):
    """Wrapper around a single LLM completion."""

    text: str
    parsed: TOutput | None = None
    usage: Usage
    model: str
    provider: str


class LLMProvider(Protocol):
    """Abstract LLM provider — every implementation supports these calls.

    Implementations in this module:
      - :class:`AnthropicProvider`
      - :class:`OpenAIProvider`
      - :class:`CachedLLMProvider`  (demo mode)
    """

    name: str

    async def complete(
        self,
        *,
        system: str,
        messages: list[Message],
        response_model: type[TOutput] | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.7,
    ) -> Response[TOutput]:
        """Run one completion.

        If ``response_model`` is provided, the response text is parsed into it
        (with three-tier fallback parsing on failure — see core/llm/parsers.py).
        """
        ...
