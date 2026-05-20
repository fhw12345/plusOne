"""Integration test for trip_runner injecting Profile + Companions into AgentContext.

The PRD calls out this test as "light" — we monkeypatch ``run_cycle`` to
capture the ``ctx`` it was called with, then assert the profile/companion
fields wired through from the (stubbed) Profile + Companion rows.

This is a pure structural test: no real LLM, no real tools, no cycle
convergence — mirrors the stubbed pattern in test_trips_sse_auth.py.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import pytest

from plus_one.core.db.models import Companion, Profile
from plus_one.services import trip_runner

if TYPE_CHECKING:
    from plus_one.core.agents.framework.types import AgentContext


class _StubSession:
    """Provides Profile + Companions for _load_profile_context."""

    def __init__(self, profile: Profile | None, companions: list[Companion]) -> None:
        self._profile = profile
        self._companions = companions

    async def get(self, *_a: Any, **_kw: Any) -> Any:
        return None

    async def execute(self, stmt: object) -> Any:
        text = str(stmt).lower()
        if "companions" in text:
            return _ListResult(self._companions)
        return _ScalarResult(self._profile)

    def add(self, _obj: object) -> None:
        return None

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None

    async def close(self) -> None:
        return None


class _ScalarResult:
    def __init__(self, value: Any) -> None:
        self._value = value

    def scalar_one_or_none(self) -> Any:
        return self._value


class _ScalarsList:
    def __init__(self, items: list[Any]) -> None:
        self._items = items

    def all(self) -> list[Any]:
        return self._items


class _ListResult:
    def __init__(self, items: list[Any]) -> None:
        self._items = items

    def scalars(self) -> _ScalarsList:
        return _ScalarsList(self._items)


@pytest.mark.integration
async def test_load_profile_context_populates_loves_hates_and_companions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid.uuid4()
    profile = Profile(
        user_id=user_id,
        demographics={},
        travel_style={},
        explicit_preferences={"loves": ["ramen", "kissaten"], "hates": ["queues"]},
        visited_cities=[],
        implicit_preferences=[],
    )
    from datetime import UTC, datetime

    companion = Companion(
        user_id=user_id,
        name="Anna",
        explicit_preferences={"loves": ["matcha"], "hates": ["seafood"]},
        constraints={},
    )
    companion.id = uuid.uuid4()
    companion.created_at = datetime.now(UTC)
    companion.updated_at = datetime.now(UTC)

    stub = _StubSession(profile, [companion])

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def fake_session_scope():
        yield stub

    monkeypatch.setattr(trip_runner, "session_scope", fake_session_scope)

    user_profile, companions = await trip_runner._load_profile_context(user_id)
    assert user_profile.loves == ("ramen", "kissaten")
    assert user_profile.hates == ("queues",)
    assert len(companions) == 1
    assert companions[0].name == "Anna"
    assert companions[0].loves == ("matcha",)
    assert companions[0].hates == ("seafood",)


@pytest.mark.integration
async def test_load_profile_context_empty_user_returns_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """User with no profile row and no companions → all-default tuple."""
    user_id = uuid.uuid4()
    stub = _StubSession(None, [])

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def fake_session_scope():
        yield stub

    monkeypatch.setattr(trip_runner, "session_scope", fake_session_scope)

    user_profile, companions = await trip_runner._load_profile_context(user_id)
    assert user_profile.loves == ()
    assert user_profile.hates == ()
    assert companions == []


@pytest.mark.integration
async def test_run_trip_passes_loaded_profile_into_agent_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end: run_trip loads profile + companions and threads them into the
    AgentContext that run_cycle receives. Stubs everything else out so we
    only check the wiring."""
    trip_id = uuid.uuid4()
    user_id = uuid.uuid4()

    profile = Profile(
        user_id=user_id,
        demographics={},
        travel_style={},
        explicit_preferences={"loves": ["ramen"], "hates": []},
        visited_cities=[],
        implicit_preferences=[],
    )
    from datetime import UTC, datetime

    companion = Companion(
        user_id=user_id,
        name="Anna",
        explicit_preferences={"loves": ["matcha"], "hates": []},
        constraints={},
    )
    companion.id = uuid.uuid4()
    companion.created_at = datetime.now(UTC)
    companion.updated_at = datetime.now(UTC)

    profile_stub = _StubSession(profile, [companion])
    # Also stub session_scope so _set_status / _save_report don't blow up.
    from contextlib import asynccontextmanager

    class _NoopSession:
        async def get(self, *_a: Any, **_kw: Any) -> Any:
            return None

        def add(self, _obj: object) -> None:
            return None

        async def flush(self) -> None:
            return None

        async def commit(self) -> None:
            return None

        async def rollback(self) -> None:
            return None

        async def close(self) -> None:
            return None

        async def execute(self, _stmt: object) -> Any:
            return _ScalarResult(None)

    # Capture whether profile_stub was reached. We don't enumerate session
    # ordering inside run_trip (it retries _set_status up to 3x and we don't
    # want the test depending on that retry budget). Instead, route by what
    # the session does first: every other session sees only Trip.get / Report
    # add calls, while _load_profile_context is the only path that issues
    # SELECTs. So we yield a "smart" router session that defers to either
    # the profile stub or noop behavior per call.
    @asynccontextmanager
    async def fake_session_scope():
        # Each new session_scope re-uses the profile_stub; the stub's
        # behavior is correct for either SELECT and tolerates everything
        # else (`get`, `add`, etc.) thanks to the no-op stubs on the same
        # class.
        yield profile_stub

    monkeypatch.setattr(trip_runner, "session_scope", fake_session_scope)

    captured_ctx: dict[str, AgentContext] = {}

    async def fake_run_cycle(*, producer, joiner, controller, ctx, **_kw):  # type: ignore[no-untyped-def]
        captured_ctx["ctx"] = ctx
        # Return a result-shaped object that run_trip can use.
        from plus_one.core.agents.framework.cycle import CycleResult
        from plus_one.core.agents.framework.types import Decision

        return CycleResult(
            items=[],
            decision=Decision(should_continue=False, reasoning="stub"),
            ctx=ctx,
            trace=[],
        )

    monkeypatch.setattr(trip_runner, "run_cycle", fake_run_cycle)

    await trip_runner.run_trip(trip_id, "Tokyo", user_id)

    assert "ctx" in captured_ctx
    ctx = captured_ctx["ctx"]
    assert ctx.user_profile.loves == ("ramen",)
    assert len(ctx.selected_companions) == 1
    assert ctx.selected_companions[0].name == "Anna"
