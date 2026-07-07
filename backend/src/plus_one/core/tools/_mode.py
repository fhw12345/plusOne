"""Tools-mode switch shared by all live-data tools (Reddit / XHS / Places).

The mode toggles each tool between its existing ``fixture`` behavior
(fast, deterministic, used in CI / e2e / dev) and the new ``real``
behavior (live API client + DB-backed cache).

Convention is intentionally a single env var (``PLUS_ONE_TOOLS_MODE``)
read at call time — not baked into ``AgentContext`` — so the joiner
stays mode-unaware and tests can flip mode per-call via
``monkeypatch.setenv``. See PRD Batch 2k §3.1.

Back-compat alias: ADR-003 wording used ``DEMO_MODE=true`` to mean
fixture mode. We honor that as ``PLUS_ONE_TOOLS_MODE=fixture``.
"""

from __future__ import annotations

import os
from typing import Literal

ToolsMode = Literal["real", "fixture"]

_VALID_MODES: tuple[ToolsMode, ...] = ("real", "fixture")
_TRUTHY = {"1", "true", "yes", "on"}


def get_tools_mode() -> ToolsMode:
    """Resolve the current tools mode.

    Precedence:
      1. ``PLUS_ONE_TOOLS_MODE`` if set — must be ``"real"`` or
         ``"fixture"`` (raises ``ValueError`` otherwise; loud over silent).
      2. ``DEMO_MODE=true`` alias → ``"fixture"`` (ADR-003 back-compat).
      3. Default ``"fixture"``.
    """
    raw = os.getenv("PLUS_ONE_TOOLS_MODE")
    if raw is not None:
        value = raw.strip().lower()
        if value not in _VALID_MODES:
            raise ValueError(f"PLUS_ONE_TOOLS_MODE must be one of {_VALID_MODES!r}, got {raw!r}")
        return value

    demo = os.getenv("DEMO_MODE")
    if demo is not None and demo.strip().lower() == "true":
        return "fixture"

    return "fixture"


def require_env(*names: str, tool: str) -> None:
    """Fail loud at tool construction when mode=real and any env is missing.

    No-op when mode is fixture — fixture-mode tests should never need
    live credentials.

    Raises ``RuntimeError`` listing every missing var, so a misconfig
    surfaces once with the full picture rather than one var at a time.
    """
    if get_tools_mode() != "real":
        return
    missing = [name for name in names if not os.getenv(name)]
    if missing:
        raise RuntimeError(f"Tool {tool!r} requires env vars in real mode: {', '.join(missing)}")


def fixture_fallbacks_enabled() -> bool:
    """Return whether real-mode tools may degrade to local fixtures.

    Fixture mode always uses fixtures. In real mode, beta validation can set
    ``PLUS_ONE_DISABLE_FIXTURE_FALLBACK=1`` so fake evidence is excluded from
    end-to-end readiness checks.
    """
    if get_tools_mode() != "real":
        return True
    raw = os.getenv("PLUS_ONE_DISABLE_FIXTURE_FALLBACK", "")
    return raw.strip().lower() not in _TRUTHY
