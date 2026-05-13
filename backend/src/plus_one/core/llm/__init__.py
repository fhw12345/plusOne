"""LLM access for Plus One.

All LLM traffic is routed through Agent Maestro (an Anthropic-API-compatible
gateway exposing Claude / GPT / Gemini behind one endpoint). Agent code
declares a *role* rather than a model; per-role model assignment lives in
:mod:`plus_one.core.llm.roles`.

Usage::

    from plus_one.core.llm import get_llm_provider, Message

    llm = get_llm_provider("producer_agent")
    response = await llm.complete(
        system="You are ...",
        messages=[Message(role="user", content="Suggest 5 ramen shops in Tokyo")],
        response_model=ProducerOutput,
    )
"""

from plus_one.core.llm.factory import get_llm_provider
from plus_one.core.llm.parsers import LLMParseError, parse_with_fallback
from plus_one.core.llm.provider import LLMProvider, Message, Response, Usage
from plus_one.core.llm.roles import list_roles, resolve_model

__all__ = [
    "LLMParseError",
    "LLMProvider",
    "Message",
    "Response",
    "Usage",
    "get_llm_provider",
    "list_roles",
    "parse_with_fallback",
    "resolve_model",
]
