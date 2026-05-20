"""Unit tests for ``plus_one.core.tools._mode``."""

from __future__ import annotations

import pytest

from plus_one.core.tools._mode import get_tools_mode, require_env


@pytest.mark.unit
def test_default_is_fixture(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PLUS_ONE_TOOLS_MODE", raising=False)
    monkeypatch.delenv("DEMO_MODE", raising=False)
    assert get_tools_mode() == "fixture"


@pytest.mark.unit
def test_explicit_real(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLUS_ONE_TOOLS_MODE", "real")
    assert get_tools_mode() == "real"


@pytest.mark.unit
def test_explicit_fixture(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLUS_ONE_TOOLS_MODE", "fixture")
    assert get_tools_mode() == "fixture"


@pytest.mark.unit
def test_case_insensitive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLUS_ONE_TOOLS_MODE", "REAL")
    assert get_tools_mode() == "real"


@pytest.mark.unit
def test_invalid_value_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLUS_ONE_TOOLS_MODE", "bogus")
    with pytest.raises(ValueError, match="PLUS_ONE_TOOLS_MODE"):
        get_tools_mode()


@pytest.mark.unit
def test_demo_mode_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PLUS_ONE_TOOLS_MODE", raising=False)
    monkeypatch.setenv("DEMO_MODE", "true")
    assert get_tools_mode() == "fixture"


@pytest.mark.unit
def test_demo_mode_alias_does_not_override_explicit_real(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PLUS_ONE_TOOLS_MODE", "real")
    monkeypatch.setenv("DEMO_MODE", "true")
    assert get_tools_mode() == "real"


@pytest.mark.unit
def test_require_env_noop_in_fixture(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PLUS_ONE_TOOLS_MODE", raising=False)
    monkeypatch.delenv("REDDIT_CLIENT_ID", raising=False)
    # Must not raise even though REDDIT_CLIENT_ID is absent.
    require_env("REDDIT_CLIENT_ID", tool="reddit_search")


@pytest.mark.unit
def test_require_env_raises_in_real_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PLUS_ONE_TOOLS_MODE", "real")
    monkeypatch.delenv("REDDIT_CLIENT_ID", raising=False)
    monkeypatch.delenv("REDDIT_CLIENT_SECRET", raising=False)
    with pytest.raises(RuntimeError) as exc_info:
        require_env("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", tool="reddit_search")
    msg = str(exc_info.value)
    assert "reddit_search" in msg
    assert "REDDIT_CLIENT_ID" in msg
    assert "REDDIT_CLIENT_SECRET" in msg


@pytest.mark.unit
def test_require_env_passes_in_real_when_all_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PLUS_ONE_TOOLS_MODE", "real")
    monkeypatch.setenv("REDDIT_CLIENT_ID", "cid")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "csecret")
    require_env("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", tool="reddit_search")
