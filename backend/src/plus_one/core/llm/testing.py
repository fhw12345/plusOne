"""Mock LLM provider for tests.

Tests should never call a real LLM. Use :class:`MockLLMProvider` to script
deterministic responses by role.

Usage in a test::

    async def test_something(mock_llm: MockLLMProvider) -> None:
        mock_llm.queue_response(
            role="producer_agent",
            text='{"items": [{"name": "X"}]}',
            parsed_data={"items": [{"name": "X"}]},
        )
        # ... code that calls get_llm_provider("producer_agent") ...
        assert mock_llm.call_count == 1
"""

from __future__ import annotations

from collections import defaultdict, deque
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from plus_one.core.llm.provider import LLMProvider, Message, Response, Usage

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


# Per-async-task role binding. Using a ContextVar instead of an instance
# attribute makes role tracking race-safe under asyncio.gather over multiple
# roles — two concurrent tasks see independent role values, not the last
# writer's. Reviewer F2.
_current_role: ContextVar[str] = ContextVar("plus_one_mock_role", default="mock")


class _ScriptedResponse:
    def __init__(
        self,
        text: str,
        parsed_data: dict[str, Any] | None = None,
        input_tokens: int = 100,
        output_tokens: int = 50,
    ) -> None:
        self.text = text
        self.parsed_data = parsed_data
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class MockLLMProvider(LLMProvider):
    """In-memory LLM provider that returns scripted responses per role.

    The same instance is returned by :func:`get_llm_provider` for every role
    during tests (via monkeypatch). Internally it routes by role so tests can
    pre-load multiple roles' expected outputs.
    """

    name = "mock"

    def __init__(self) -> None:
        self._queues: dict[str, deque[_ScriptedResponse]] = defaultdict(deque)
        self._default_response = _ScriptedResponse(
            text="(mock response — queue empty)",
        )
        self.calls: list[dict[str, Any]] = []

    # === Test-side API ===

    def queue_response(
        self,
        role: str,
        text: str,
        parsed_data: dict[str, Any] | None = None,
        *,
        input_tokens: int = 100,
        output_tokens: int = 50,
    ) -> None:
        """Push a scripted response for the next call with ``role``."""
        self._queues[role].append(_ScriptedResponse(text, parsed_data, input_tokens, output_tokens))

    def reset(self) -> None:
        """Clear all queued responses + call history."""
        self._queues.clear()
        self.calls.clear()

    @property
    def call_count(self) -> int:
        return len(self.calls)

    def calls_for_role(self, role: str) -> list[dict[str, Any]]:
        return [c for c in self.calls if c["role"] == role]

    # === LLMProvider interface (matches MaestroProvider signature) ===

    role = "mock"

    async def complete[TOutput: BaseModel](
        self,
        *,
        system: str,
        messages: list[Message],
        response_model: type[TOutput] | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.7,
    ) -> Response[TOutput]:
        # Caller's role is identified by the ContextVar set by _RoleBoundMock,
        # which is per-async-task (race-safe under asyncio.gather).
        role = _current_role.get()
        self.calls.append(
            {
                "role": role,
                "system": system,
                "messages": [m.model_dump() for m in messages],
                "max_tokens": max_tokens,
                "temperature": temperature,
                "response_model": response_model.__name__ if response_model else None,
            }
        )

        queue = self._queues.get(role, deque())
        scripted = queue.popleft() if queue else self._default_response

        parsed: TOutput | None = None
        if response_model is not None and scripted.parsed_data is not None:
            parsed = response_model.model_validate(scripted.parsed_data)

        return Response[TOutput](
            text=scripted.text,
            parsed=parsed,
            usage=Usage(
                input_tokens=scripted.input_tokens,
                output_tokens=scripted.output_tokens,
            ),
            model=f"mock-{role}",
            provider="mock",
        )

    async def astream(
        self,
        *,
        system: str,
        messages: list[Message],
        max_tokens: int | None = None,
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:
        response: Response[BaseModel] = await self.complete(
            system=system,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        # Stream the scripted text as one chunk by default; tests that need
        # multi-chunk streaming can subclass.
        yield response.text


class _RoleBoundMock:
    """Adapter so each get_llm_provider(role) call returns a per-role view.

    Sets the ``_current_role`` ContextVar before delegating to the shared
    :class:`MockLLMProvider`. Because ContextVar values are per-async-task,
    two calls running concurrently under :func:`asyncio.gather` see
    independent role bindings — there is no race.
    """

    name = "mock"

    def __init__(self, parent: MockLLMProvider, role: str) -> None:
        self._parent = parent
        self.role = role

    async def complete(self, **kwargs: Any) -> Any:
        token = _current_role.set(self.role)
        try:
            return await self._parent.complete(**kwargs)
        finally:
            _current_role.reset(token)

    async def astream(self, **kwargs: Any) -> AsyncIterator[str]:
        token = _current_role.set(self.role)
        try:
            async for chunk in self._parent.astream(**kwargs):
                yield chunk
        finally:
            _current_role.reset(token)


def make_mock_factory(parent: MockLLMProvider) -> Any:
    """Return a drop-in replacement for ``get_llm_provider`` that yields role-bound mocks."""

    def _factory(role: str = "conversational", *, streaming: bool = False) -> Any:
        del streaming  # unused, present for API compatibility with real factory
        return _RoleBoundMock(parent, role)

    return _factory
