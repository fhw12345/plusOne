"""Pure divergence-score helper for the Joiner agent.

Computes a deterministic ``divergence_score`` in [0, 1] from a pair of
per-language classifications (``classification_en`` and
``classification_zh``). Keeping this out of the LLM output removes a
class of hallucinations and lets us unit-test the threshold exhaustively.

See ``docs/prds/batch2i-disagreement-perspective.md`` §4.3 for the
truth-table and rationale.

Caveat: v1 uses *source* as a language proxy (Reddit → English,
Xiaohongshu → Chinese, Google Places → neutral). A Reddit thread written
in Chinese — or a Xiaohongshu post written in English — will be
mis-attributed. v2 will replace this with per-evidence language
detection; see PRD §9.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from plus_one.agents.types import Classification

#: Items at or above this score with both per-language classifications
#: present and differing are flagged as disagreements in the UI.
DISAGREEMENT_THRESHOLD: Final[float] = 0.5

_STRONG: Final[frozenset[Classification]] = frozenset({"local_gem", "tourist_trap"})


def divergence_score(en: Classification | None, zh: Classification | None) -> float:
    """Score the divergence between two per-language classifications.

    Returns ``0.0`` when either side is ``None`` (the disagreement gate
    fails closed — see PRD §4.3) or when both sides agree.
    """
    if en is None or zh is None:
        return 0.0
    if en == zh:
        return 0.0
    pair = frozenset({en, zh})
    # Direct contradiction: gem vs trap.
    if pair == _STRONG:
        return 1.0
    # One side is strong, other side admits no evidence: asymmetric coverage
    # ("Reddit has never heard of this but xhs raves" — exactly the
    # cross-cultural finds the product wants to spotlight).
    if "insufficient" in pair and (pair - {"insufficient"}) & _STRONG:
        return 0.6
    # Strong vs neutral: meaningful disagreement.
    if "neutral" in pair and pair & _STRONG:
        return 0.5
    # Insufficient vs neutral: weakest signal that still differs.
    return 0.3
