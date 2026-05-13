"""Factory — returns the LLM provider for a given role.

Single entry point for all agent code:

    >>> from plus_one.core.llm import get_llm_provider
    >>> llm = get_llm_provider("producer_agent")
    >>> result = await llm.complete(system="...", messages=[...])

Each role gets its own provider instance (with its own model + sampling
defaults). Instances are cached so repeated calls for the same role return
the same client.
"""

from __future__ import annotations

from functools import lru_cache

from plus_one.core.llm.maestro_provider import MaestroProvider
from plus_one.core.llm.provider import LLMProvider


@lru_cache(maxsize=32)
def get_llm_provider(
    role: str = "conversational",
    *,
    streaming: bool = False,
) -> LLMProvider:
    """Return a cached :class:`MaestroProvider` for ``role``.

    Args:
        role: Logical role name; mapped to a concrete model in
              :mod:`plus_one.core.llm.roles`.
        streaming: If True, returns a streaming-enabled client.

    Returns:
        An :class:`LLMProvider` instance (currently always :class:`MaestroProvider`).
    """
    return MaestroProvider(role=role, streaming=streaming)
