"""Verify the bundled skills directory loads cleanly."""

from __future__ import annotations

from pathlib import Path

import pytest

from plus_one.core.agents.framework.skills import SkillRegistry

# Skills live alongside the package source so they ship with the wheel.
# This file is at tests/unit/agents/framework/test_bundled_skills.py
# (4 levels deep below backend/), so parents[4] gets us to backend/.
_BUNDLED_SKILLS_DIR = (
    Path(__file__).resolve().parents[4] / "src" / "plus_one" / "skills"
)


@pytest.mark.unit
def test_bundled_skills_directory_loads() -> None:
    registry = SkillRegistry()
    n = registry.load_directory(_BUNDLED_SKILLS_DIR)
    assert n >= 1, "expected at least one bundled skill"
    assert "ramen_basics" in registry


@pytest.mark.unit
def test_bundled_ramen_skill_routes_on_query() -> None:
    registry = SkillRegistry()
    registry.load_directory(_BUNDLED_SKILLS_DIR)
    matches = registry.route("Where can I find good tonkotsu ramen in Tokyo?")
    names = [s.name for s in matches]
    assert "ramen_basics" in names


@pytest.mark.unit
def test_bundled_ramen_skill_lists_real_tools() -> None:
    registry = SkillRegistry()
    registry.load_directory(_BUNDLED_SKILLS_DIR)
    skill = registry.get("ramen_basics")
    assert "reddit_search" in skill.allowed_tools
    assert "xhs_search" in skill.allowed_tools
    assert "google_places_search" in skill.allowed_tools
