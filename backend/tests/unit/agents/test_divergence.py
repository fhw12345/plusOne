"""Truth-table tests for the divergence-score helper.

Mirrors the table in ``docs/prds/batch2i-disagreement-perspective.md`` §4.3.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from plus_one.agents._divergence import DISAGREEMENT_THRESHOLD, divergence_score

if TYPE_CHECKING:
    from plus_one.agents.types import Classification


@pytest.mark.unit
@pytest.mark.parametrize(
    ("en", "zh", "expected"),
    [
        # Agreement → 0.0
        ("local_gem", "local_gem", 0.0),
        ("tourist_trap", "tourist_trap", 0.0),
        ("neutral", "neutral", 0.0),
        ("insufficient", "insufficient", 0.0),
        # Direct contradiction → 1.0
        ("local_gem", "tourist_trap", 1.0),
        ("tourist_trap", "local_gem", 1.0),
        # Strong vs insufficient (asymmetric coverage) → 0.6
        ("local_gem", "insufficient", 0.6),
        ("insufficient", "tourist_trap", 0.6),
        # Strong vs neutral → 0.5
        ("local_gem", "neutral", 0.5),
        ("tourist_trap", "neutral", 0.5),
        # Weak/weak (still differs) → 0.3
        ("neutral", "insufficient", 0.3),
        ("insufficient", "neutral", 0.3),
        # Either-None → 0.0 (gate fails closed)
        (None, "local_gem", 0.0),
        ("local_gem", None, 0.0),
        (None, None, 0.0),
    ],
)
def test_divergence_score_truth_table(
    en: Classification | None,
    zh: Classification | None,
    expected: float,
) -> None:
    assert divergence_score(en, zh) == expected


@pytest.mark.unit
def test_threshold_is_documented_constant() -> None:
    assert DISAGREEMENT_THRESHOLD == 0.5


@pytest.mark.unit
def test_score_is_bounded_in_unit_interval() -> None:
    """Defensive: every emitted score must lie in [0, 1] so the UI gate
    stays well-defined and the field's ``Field(ge=0, le=1)`` constraint
    on ``JoinedItem.divergence_score`` never trips."""
    values: list[Classification | None] = [
        "local_gem",
        "tourist_trap",
        "neutral",
        "insufficient",
        None,
    ]
    for en in values:
        for zh in values:
            score = divergence_score(en, zh)
            assert 0.0 <= score <= 1.0
