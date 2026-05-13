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

from typing import TYPE_CHECKING

import pytest

from plus_one.core import llm as llm_pkg
from plus_one.core.llm import factory
from plus_one.core.llm.testing import MockLLMProvider, make_mock_factory

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(autouse=True)
def mock_llm(monkeypatch: pytest.MonkeyPatch) -> Iterator[MockLLMProvider]:
    """Replace the LLM provider factory with a scriptable mock.

    Auto-applied to every test (``autouse=True``). Tests can still depend on
    the fixture explicitly to call ``queue_response()`` or inspect calls.
    """
    parent = MockLLMProvider()
    fake_factory = make_mock_factory(parent)

    # Capture the real (lru_cached) factory before monkeypatch swaps it out,
    # so we can clear its cache on teardown without losing the reference.
    real_factory = factory.get_llm_provider
    real_factory.cache_clear()
    monkeypatch.setattr(factory, "get_llm_provider", fake_factory)
    monkeypatch.setattr(llm_pkg, "get_llm_provider", fake_factory)

    yield parent

    real_factory.cache_clear()
