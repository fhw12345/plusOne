"""Skill system — file-based, hot-loadable methodology snippets.

A *skill* is a plain markdown file with YAML frontmatter that describes
when and how to apply some piece of domain methodology. Format follows the
Anthropic Skills convention:

::

    ---
    name: ramen_basics
    description: Tokyo ramen styles + landmark shops + how to read a menu
    when_to_use: User mentions ramen, noodles, or Tokyo food
    allowed_tools: ["reddit_search", "google_places"]
    ---

    # Body of the skill (markdown)

    ## Section 1
    ...

Skills are loaded once at startup from a directory tree. The registry
exposes them by name and supports keyword-based routing (heavy LLM-based
routing lives in a higher layer).

The framework does NOT prescribe how a skill is *applied* — agents decide
whether to inline a skill into a prompt, fork a subagent that owns it, or
just consult its frontmatter for routing. ADR-002 covers the rationale.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from plus_one.core.agents.framework.errors import SkillNotFoundError

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator


# Frontmatter delimited by --- on its own line at the start of the file.
# Body is everything after the closing delimiter.
_FRONTMATTER_RE = re.compile(
    r"\A---\s*\n(?P<frontmatter>.*?)\n---\s*\n(?P<body>.*)\Z",
    re.DOTALL,
)

# Minimum word length to count toward keyword routing — shorter than this
# matches too noisily ("a", "to", "the").
_MIN_KEYWORD_LEN = 4


class Skill(BaseModel):
    """A methodology snippet, loaded from a markdown-with-frontmatter file."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(description="Unique identifier, lowercase_underscore")
    description: str = Field(description="One-line summary used by the skill router for selection")
    when_to_use: str = Field(
        default="",
        description="Plain-language trigger description ('user asks about X')",
    )
    allowed_tools: tuple[str, ...] = Field(
        default=(),
        description="Tool names this skill is allowed to call",
    )
    body: str = Field(description="Markdown body of the skill")
    source_path: Path | None = Field(
        default=None,
        description="Where the skill was loaded from (None for in-memory skills)",
    )

    def keyword_score(self, text: str) -> int:
        """Trivial keyword-match score for cheap-and-fast routing.

        Counts how many words from ``description`` + ``when_to_use`` appear
        in ``text`` (case-insensitive, word-boundary). Suitable as a baseline
        before a real embedding-based router is added.
        """
        haystack = text.lower()
        score = 0
        for needle in (self.description + " " + self.when_to_use).lower().split():
            cleaned = re.sub(r"[^a-z0-9]+", "", needle)
            if len(cleaned) >= _MIN_KEYWORD_LEN and re.search(
                rf"\b{re.escape(cleaned)}\b", haystack
            ):
                score += 1
        return score


def parse_skill_file(path: Path) -> Skill:
    """Parse a single ``.md`` file into a :class:`Skill`.

    Raises:
        ValueError: file has no frontmatter, or frontmatter is malformed.
        ValidationError: frontmatter fields don't match the schema.
    """
    raw = path.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(raw)
    if not match:
        raise ValueError(f"Skill file {path} has no YAML frontmatter delimited by '---' lines")
    try:
        meta = yaml.safe_load(match.group("frontmatter")) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"Skill file {path}: frontmatter is not valid YAML: {exc}") from exc
    if not isinstance(meta, dict):
        raise ValueError(
            f"Skill file {path}: frontmatter must be a mapping, got {type(meta).__name__}"
        )

    # Normalize allowed_tools to a tuple
    if "allowed_tools" in meta and isinstance(meta["allowed_tools"], list):
        meta["allowed_tools"] = tuple(meta["allowed_tools"])

    try:
        return Skill(
            **meta,
            body=match.group("body").strip(),
            source_path=path,
        )
    except ValidationError as exc:
        raise ValueError(f"Skill file {path}: schema mismatch: {exc}") from exc


class SkillRegistry:
    """In-memory registry of all loaded skills.

    Three layers (per ADR-005-ish convention used by Claude Code skills):
    bundled (shipped in repo), user (~/.plus_one/skills/), project
    (.plus_one/skills/ in cwd). Later layers override earlier on name
    collision. For now only bundled is wired; the others are TODO.
    """

    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill, *, override: bool = False) -> None:
        """Register a skill in memory.

        If ``override`` is False (default) and the name is already taken,
        raise :class:`ValueError`. Use ``override=True`` to deliberately
        replace (e.g. user / project layer overriding bundled).
        """
        if skill.name in self._skills and not override:
            raise ValueError(
                f"Skill {skill.name!r} already registered; pass override=True to replace"
            )
        self._skills[skill.name] = skill

    def load_directory(self, directory: Path, *, override: bool = False) -> int:
        """Load every ``*.md`` file under ``directory`` (recursive).

        Returns the number of skills loaded. Skips files that fail to parse,
        emitting them as ValueError chained in a list — caller can decide
        whether to log or fail.
        """
        if not directory.exists():
            return 0
        loaded = 0
        for path in sorted(directory.rglob("*.md")):
            skill = parse_skill_file(path)
            self.register(skill, override=override)
            loaded += 1
        return loaded

    def get(self, name: str) -> Skill:
        """Return the skill with ``name`` or raise :class:`SkillNotFoundError`."""
        if name not in self._skills:
            raise SkillNotFoundError(name)
        return self._skills[name]

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name in self._skills

    def __iter__(self) -> Iterator[Skill]:
        return iter(self._skills.values())

    def __len__(self) -> int:
        return len(self._skills)

    def names(self) -> list[str]:
        return sorted(self._skills.keys())

    def route(self, query: str, *, top_k: int = 3) -> list[Skill]:
        """Cheap keyword-based routing — return up to ``top_k`` most relevant.

        Skills are sorted by descending :meth:`Skill.keyword_score`. Skills
        with score 0 are excluded. This is a deliberately simple baseline;
        an embedding-based router can replace it without changing the API.
        """
        scored: Iterable[tuple[int, Skill]] = (
            (s.keyword_score(query), s) for s in self._skills.values()
        )
        ranked = sorted(
            (item for item in scored if item[0] > 0),
            key=lambda item: item[0],
            reverse=True,
        )
        return [skill for _, skill in ranked[:top_k]]
