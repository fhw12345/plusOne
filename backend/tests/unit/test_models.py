"""Profile + Companion ORM declarative assertions (PRD §9.a, batch 2h).

The PRD originally calls for real-DB IntegrityError + cascade checks but
the test suite has no live-DB fixture; instead we verify the equivalent
constraints at the SQLAlchemy metadata + relationship-config level. The
alembic upgrade/downgrade round-trip in CI is the live-PG guardrail.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import RelationshipProperty

from plus_one.core.db.base import Base
from plus_one.core.db.models import Companion, Profile, User


@pytest.mark.unit
def test_profile_jsonb_columns_nullable_false_with_orm_defaults() -> None:
    """Confirmation checklist from PRD §3 table."""
    cols = Base.metadata.tables["profiles"].c
    for name in ("demographics", "travel_style", "explicit_preferences"):
        assert cols[name].nullable is False
        # ColumnDefault wraps the python callable; check the callable name.
        assert cols[name].default is not None
        assert cols[name].default.arg.__name__ == "dict"
    for name in ("visited_cities", "implicit_preferences"):
        assert cols[name].nullable is False
        assert cols[name].default is not None
        assert cols[name].default.arg.__name__ == "list"


@pytest.mark.unit
def test_profile_user_id_is_unique() -> None:
    """One profile per user (1:1)."""
    user_id_col = Base.metadata.tables["profiles"].c.user_id
    assert user_id_col.unique is True


@pytest.mark.unit
def test_profile_user_fk_on_delete_cascade() -> None:
    """Deleting a User must cascade-delete its Profile row."""
    fk = next(iter(Base.metadata.tables["profiles"].c.user_id.foreign_keys))
    assert fk.ondelete == "CASCADE"


@pytest.mark.unit
def test_user_profile_relationship_uses_delete_orphan() -> None:
    """ORM-level cascade matches the FK-level CASCADE so unit-of-work
    deletion through User.profile = None also clears the row."""
    rel = User.__mapper__.relationships["profile"]
    assert isinstance(rel, RelationshipProperty)
    # cascade is a CascadeOptions instance with the configured flags as attrs.
    assert "delete-orphan" in rel.cascade


@pytest.mark.unit
def test_companion_composite_unique_constraint_present() -> None:
    """(user_id, name) UNIQUE — PRD §3 checklist + existing migration."""
    table = Base.metadata.tables["companions"]
    uniques = [
        c
        for c in table.constraints
        if c.__class__.__name__ == "UniqueConstraint" and c.name == "uq_companion_user_name"
    ]
    assert len(uniques) == 1
    cols = {col.name for col in uniques[0].columns}
    assert cols == {"user_id", "name"}


@pytest.mark.unit
def test_companion_name_length_capped_at_100() -> None:
    name_col = Base.metadata.tables["companions"].c.name
    # SQLAlchemy String(100) → length=100; mirrors API schema max_length=100.
    assert getattr(name_col.type, "length", None) == 100


@pytest.mark.unit
def test_companion_user_fk_on_delete_cascade() -> None:
    """Deleting a User must cascade-delete its Companion rows."""
    fk = next(iter(Base.metadata.tables["companions"].c.user_id.foreign_keys))
    assert fk.ondelete == "CASCADE"


@pytest.mark.unit
def test_user_companions_relationship_cascade_delete_orphan() -> None:
    rel = User.__mapper__.relationships["companions"]
    assert "delete-orphan" in rel.cascade


@pytest.mark.unit
def test_companion_jsonb_defaults_match_prd() -> None:
    cols = Base.metadata.tables["companions"].c
    for name in ("explicit_preferences", "constraints"):
        assert cols[name].nullable is False
        assert cols[name].default is not None
        assert cols[name].default.arg.__name__ == "dict"


@pytest.mark.unit
def test_profile_and_companion_classes_export_expected_attributes() -> None:
    """Quick smoke that the ORM classes still expose the columns the
    rest of the codebase imports (catches accidental rename in this PR)."""
    for attr in ("demographics", "travel_style", "explicit_preferences", "visited_cities"):
        assert hasattr(Profile, attr)
    for attr in ("name", "explicit_preferences", "constraints"):
        assert hasattr(Companion, attr)
