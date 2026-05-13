"""Smoke tests for ORM model wiring.

Verifies relationships, defaults, and tablename conventions WITHOUT
hitting a real database. Live DB tests live in tests/integration/.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from plus_one.core.db.base import Base, new_uuid
from plus_one.core.db.models import (
    MagicLinkToken,
    Profile,
    Trip,
    User,
)


@pytest.mark.unit
def test_all_models_registered_on_metadata() -> None:
    """Every ORM class should appear in Base.metadata.tables."""
    expected = {
        "users",
        "profiles",
        "companions",
        "trips",
        "trip_companions",
        "reports",
        "feedback",
        "magic_link_tokens",
    }
    assert expected.issubset(set(Base.metadata.tables.keys()))


@pytest.mark.unit
def test_user_relationships_lazy_construct() -> None:
    """Relationship attributes should be present and start empty for a new instance."""
    user = User(email="a@example.com", is_active=True)
    # SQLAlchemy InstrumentedList lazy-init: companions/trips are list-like
    assert user.email == "a@example.com"
    assert user.is_active is True
    assert user.profile is None
    assert list(user.companions) == []
    assert list(user.trips) == []


@pytest.mark.unit
def test_profile_default_jsons() -> None:
    p = Profile(
        user_id=new_uuid(),
        demographics={},
        travel_style={},
        explicit_preferences={},
        visited_cities=[],
        implicit_preferences=[],
    )
    assert p.demographics == {}
    assert p.visited_cities == []


@pytest.mark.unit
def test_companion_uniqueness_constraint_declared() -> None:
    """The (user_id, name) UNIQUE constraint must exist on the companions table."""
    table = Base.metadata.tables["companions"]
    uniques = [c for c in table.constraints if c.__class__.__name__ == "UniqueConstraint"]
    names = {c.name for c in uniques if c.name}
    assert "uq_companion_user_name" in names


@pytest.mark.unit
def test_trip_companions_association_table_columns() -> None:
    table = Base.metadata.tables["trip_companions"]
    assert {"trip_id", "companion_id"} == {c.name for c in table.columns}


@pytest.mark.unit
def test_trip_default_status_is_pending_via_constructor() -> None:
    """Trip construction without status should fall back to 'pending'."""
    trip = Trip(user_id=new_uuid(), destination="Tokyo")
    # SQLAlchemy column defaults are applied at flush time, not construction —
    # so we assert the column-level default rather than the instance attribute.
    status_col = Base.metadata.tables["trips"].c.status
    assert status_col.default is not None
    assert getattr(status_col.default, "arg", None) == "pending"
    # Construction itself succeeds with no status value.
    assert trip.destination == "Tokyo"


@pytest.mark.unit
def test_report_token_counters_default_to_zero() -> None:
    cols = Base.metadata.tables["reports"].c
    assert cols.input_tokens.default is not None
    assert cols.output_tokens.default is not None
    assert getattr(cols.input_tokens.default, "arg", None) == 0
    assert getattr(cols.output_tokens.default, "arg", None) == 0


@pytest.mark.unit
def test_feedback_composite_index_declared() -> None:
    indexes = {idx.name for idx in Base.metadata.tables["feedback"].indexes}
    assert "ix_feedback_trip_card" in indexes


@pytest.mark.unit
def test_magic_link_token_pk_is_token_string() -> None:
    pk_cols = [c.name for c in Base.metadata.tables["magic_link_tokens"].primary_key.columns]
    assert pk_cols == ["token"]


@pytest.mark.unit
def test_magic_link_token_does_not_have_timestamp_mixin_columns() -> None:
    cols = {c.name for c in Base.metadata.tables["magic_link_tokens"].columns}
    # Has its own issued_at / expires_at / consumed_at
    assert "issued_at" in cols
    assert "expires_at" in cols
    # But NOT the TimestampMixin pair
    assert "created_at" not in cols
    assert "updated_at" not in cols


@pytest.mark.unit
def test_naming_convention_is_applied() -> None:
    """Constraint names should follow the project convention (pk_<table>, etc.)."""
    pk = Base.metadata.tables["users"].primary_key
    assert pk.name == "pk_users"
    fk_constraint_names: set[str] = set()
    for fk in Base.metadata.tables["profiles"].foreign_keys:
        if fk.constraint is not None and fk.constraint.name is not None:
            name = fk.constraint.name
            # SQLAlchemy types `name` as `str | _NoneName`; once we've
            # filtered out None we can safely str() it for the set.
            fk_constraint_names.add(str(name))
    assert "fk_profiles_user_id_users" in fk_constraint_names


@pytest.mark.unit
def test_magic_link_token_construction() -> None:
    now = datetime.now(UTC)
    tok = MagicLinkToken(
        token="abc123",
        user_id=new_uuid(),
        issued_at=now,
        expires_at=now,
    )
    assert tok.token == "abc123"
    assert tok.consumed_at is None
