"""Tests for the skill registry + frontmatter parser."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from plus_one.core.agents.framework.errors import SkillNotFoundError
from plus_one.core.agents.framework.skills import (
    Skill,
    SkillRegistry,
    parse_skill_file,
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.unit
def test_parse_skill_file_happy_path(tmp_path: Path) -> None:
    p = tmp_path / "ramen.md"
    p.write_text(
        "---\n"
        "name: ramen_basics\n"
        "description: Tokyo ramen styles\n"
        "when_to_use: User asks about noodles\n"
        'allowed_tools: ["reddit_search"]\n'
        "---\n"
        "# Ramen body\n\nlots of text\n",
        encoding="utf-8",
    )
    skill = parse_skill_file(p)
    assert skill.name == "ramen_basics"
    assert skill.description == "Tokyo ramen styles"
    assert skill.when_to_use == "User asks about noodles"
    assert skill.allowed_tools == ("reddit_search",)
    assert skill.body.startswith("# Ramen body")
    assert skill.source_path == p


@pytest.mark.unit
def test_parse_skill_file_rejects_missing_frontmatter(tmp_path: Path) -> None:
    p = tmp_path / "broken.md"
    p.write_text("just markdown, no frontmatter", encoding="utf-8")
    with pytest.raises(ValueError, match="no YAML frontmatter"):
        parse_skill_file(p)


@pytest.mark.unit
def test_parse_skill_file_rejects_missing_required_field(tmp_path: Path) -> None:
    p = tmp_path / "no_desc.md"
    p.write_text(
        "---\nname: x\n---\nbody\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="schema mismatch"):
        parse_skill_file(p)


@pytest.mark.unit
def test_parse_skill_file_rejects_bad_yaml(tmp_path: Path) -> None:
    p = tmp_path / "bad_yaml.md"
    # Unclosed bracket — PyYAML's permissive scanner does fail on this.
    p.write_text(
        "---\nname: [unclosed\n---\nbody\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="not valid YAML"):
        parse_skill_file(p)


@pytest.mark.unit
def test_registry_register_and_get() -> None:
    reg = SkillRegistry()
    s = Skill(name="x", description="d", body="b")
    reg.register(s)
    assert "x" in reg
    assert reg.get("x") is s
    assert len(reg) == 1


@pytest.mark.unit
def test_registry_rejects_duplicate_without_override() -> None:
    reg = SkillRegistry()
    reg.register(Skill(name="x", description="d", body="b"))
    with pytest.raises(ValueError, match="already registered"):
        reg.register(Skill(name="x", description="d2", body="b2"))


@pytest.mark.unit
def test_registry_override_replaces() -> None:
    reg = SkillRegistry()
    reg.register(Skill(name="x", description="orig", body="b"))
    reg.register(Skill(name="x", description="new", body="b2"), override=True)
    assert reg.get("x").description == "new"


@pytest.mark.unit
def test_registry_get_missing_raises() -> None:
    reg = SkillRegistry()
    with pytest.raises(SkillNotFoundError):
        reg.get("nope")


@pytest.mark.unit
def test_registry_load_directory(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text(
        "---\nname: a\ndescription: alpha skill\n---\nbody a\n",
        encoding="utf-8",
    )
    (tmp_path / "b.md").write_text(
        "---\nname: b\ndescription: beta skill\n---\nbody b\n",
        encoding="utf-8",
    )
    (tmp_path / "ignored.txt").write_text("not markdown", encoding="utf-8")

    reg = SkillRegistry()
    n = reg.load_directory(tmp_path)
    assert n == 2
    assert "a" in reg
    assert "b" in reg


@pytest.mark.unit
def test_registry_load_missing_directory_returns_zero(tmp_path: Path) -> None:
    reg = SkillRegistry()
    assert reg.load_directory(tmp_path / "does_not_exist") == 0


@pytest.mark.unit
def test_keyword_route_returns_relevant_first() -> None:
    reg = SkillRegistry()
    reg.register(
        Skill(
            name="ramen",
            description="Tokyo ramen styles tonkotsu shoyu",
            when_to_use="User asks about noodles",
            body="b",
        )
    )
    reg.register(
        Skill(
            name="sushi",
            description="Tokyo sushi omakase",
            when_to_use="User asks about raw fish",
            body="b",
        )
    )

    matches = reg.route("I want tonkotsu noodles in Shibuya")
    assert matches[0].name == "ramen"


@pytest.mark.unit
def test_keyword_route_excludes_zero_score() -> None:
    reg = SkillRegistry()
    reg.register(Skill(name="ramen", description="ramen tonkotsu shoyu", body="b"))
    matches = reg.route("show me hotels in Paris")
    assert matches == []


@pytest.mark.unit
def test_keyword_route_top_k() -> None:
    reg = SkillRegistry()
    for i in range(5):
        reg.register(
            Skill(
                name=f"s{i}",
                description="hotel paris france europe travel destination",
                body="b",
            )
        )
    matches = reg.route("hotel travel paris", top_k=2)
    assert len(matches) == 2


@pytest.mark.unit
def test_skill_is_frozen() -> None:
    s = Skill(name="x", description="d", body="b")
    with pytest.raises(ValueError, match="frozen"):
        s.name = "y"  # type: ignore[misc]
