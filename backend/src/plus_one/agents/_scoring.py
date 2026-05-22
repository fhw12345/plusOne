"""Per-person scoring helpers for the joiner agent (batch-2p).

Two pure helpers:

* ``render_person_roster(profile, companions)`` — produces the
  ``{person_roster}`` block injected into the joiner v3 prompt. Lists
  every party member with their ``person_id`` UUID and explicit
  loves/hates. The joiner LLM keys its emitted ``match_scores`` map
  against those UUIDs.
* ``validate_match_scores(scores, allowed_ids)`` — defensive parser run
  after the LLM responds: drops keys for UUIDs we never sent (LLM
  hallucinated), fills missing party members with the neutral default
  ``0.5``, clamps every value into ``[0.0, 1.0]`` and coerces an empty
  result to ``None``.

No LLM, no DB, no IO — keeps the file trivially unit-testable.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from plus_one.core.agents.framework.types import (
        CompanionForContext,
        UserProfileForContext,
    )


_NEUTRAL_DEFAULT = 0.5
_USER_LABEL = "you"


def _format_list(values: tuple[str, ...]) -> str:
    """Render a tuple of preference strings as ``[a, b, c]``."""
    return "[" + ", ".join(values) + "]"


def render_person_roster(
    profile: UserProfileForContext,
    companions: list[CompanionForContext],
) -> str:
    """Render the ``{person_roster}`` block for the joiner v3 prompt.

    One line per party member, in the form::

        - person_id=<uuid> name=you loves=[ramen] hates=[seafood]

    The user is always emitted (labelled ``you``) even when their profile
    has no preferences and no ``id`` — the LLM should never see an empty
    roster, so the line is kept with empty bracket placeholders. If the
    user has no ``id`` (synthetic / test context), we emit the literal
    ``unknown`` token so the structure stays stable; the post-parse
    validator will drop scores keyed against it.

    Companions are listed in the order given.
    """
    lines: list[str] = []
    user_id = str(profile.id) if profile.id is not None else "unknown"
    lines.append(
        f"- person_id={user_id} name={_USER_LABEL} "
        f"loves={_format_list(profile.loves)} hates={_format_list(profile.hates)}"
    )
    for companion in companions:
        cid = str(companion.id) if companion.id is not None else "unknown"
        lines.append(
            f"- person_id={cid} name={companion.name} "
            f"loves={_format_list(companion.loves)} hates={_format_list(companion.hates)}"
        )
    return "\n".join(lines)


def validate_match_scores(
    scores: dict[UUID, float] | dict[str, float] | None,
    allowed_ids: set[UUID],
) -> dict[UUID, float] | None:
    """Sanitise LLM-emitted per-person scores.

    * Coerces string keys to ``UUID`` where possible.
    * Drops keys not in ``allowed_ids`` (LLM hallucinated a UUID).
    * Fills any ``allowed_ids`` not present with the neutral default
      ``0.5`` so downstream code can rely on completeness.
    * Clamps every value into ``[0.0, 1.0]``.
    * If after sanitisation the map is empty or there are no
      ``allowed_ids`` at all, returns ``None``.
    """
    if not allowed_ids:
        return None
    cleaned: dict[UUID, float] = {}
    if scores:
        for raw_key, raw_value in scores.items():
            key: UUID | None
            if isinstance(raw_key, UUID):
                key = raw_key
            else:
                try:
                    key = UUID(str(raw_key))
                except (ValueError, AttributeError, TypeError):
                    key = None
            if key is None or key not in allowed_ids:
                continue
            try:
                value = float(raw_value)
            except (TypeError, ValueError):
                continue
            if value < 0.0:
                value = 0.0
            elif value > 1.0:
                value = 1.0
            cleaned[key] = value
    # Fill missing required ids with the neutral default.
    for required in allowed_ids:
        cleaned.setdefault(required, _NEUTRAL_DEFAULT)
    return cleaned or None
