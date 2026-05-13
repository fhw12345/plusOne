"""Shared pytest fixtures.

Every test gets a :class:`MockLLMProvider` automatically wired in via
monkeypatching ``plus_one.core.llm.factory.get_llm_provider``. This ensures
no test ever accidentally calls a real LLM endpoint.

If a test needs to script LLM behavior, depend on the ``mock_llm`` fixture::

    async def test_my_agent(mock_llm: MockLLMProvider) -> None:
        mock_llm.queue_response(
            role="producer_agent",
            text='{"items": []}',
            parsed_data={"items": []},
        )
        ...
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from plus_one.core.llm import factory
from plus_one.core.llm.testing import MockLLMProvider, make_mock_factory


@pytest.fixture(autouse=True)
def mock_llm(monkeypatch: pytest.MonkeyPatch) -> Iterator[MockLLMProvider]:
    """Replace the LLM provider factory with a scriptable mock.

    Auto-applied to every test (``autouse=True``). Tests can still depend on
    the fixture explicitly to call ``queue_response()`` or inspect calls.
    """
    parent = MockLLMProvider()
    fake_factory = make_mock_factory(parent)

    factory.get_llm_provider.cache_clear()
    monkeypatch.setattr(factory, "get_llm_provider", fake_factory)
    # Also patch the re-exported name in the package's __init__ surface.
    from plus_one.core import llm as llm_pkg

    monkeypatch.setattr(llm_pkg, "get_llm_provider", fake_factory)

    yield parent

    factory.get_llm_provider.cache_clear()
