"""Smoke tests for ORM model wiring.

Verifies relationships, defaults, and tablename conventions WITHOUT
hitting a real database. Live DB tests live in tests/integration/.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from plus_one.core.db.base import Base, new_uuid
from plus_one.core.db.models import (
    EmailCode,
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
        "email_codes",
    }
    assert expected.issubset(set(Base.metadata.tables.keys()))


@pytest.mark.unit
def test_magic_link_tokens_table_is_gone() -> None:
    """batch-2m dropped magic_link_tokens — it must not be registered."""
    assert "magic_link_tokens" not in Base.metadata.tables


@pytest.mark.unit
def test_user_relationships_lazy_construct() -> None:
    """Relationship attributes should be present and start empty for a new instance."""
    user = User(
        email="a@example.com",
        username="alice",
        password_hash="x",
        is_active=True,
    )
    assert user.email == "a@example.com"
    assert user.username == "alice"
    assert user.is_active is True
    assert user.profile is None
    assert list(user.companions) == []
    assert list(user.trips) == []


@pytest.mark.unit
def test_user_has_new_credential_columns() -> None:
    """batch-2m: username / password_hash / is_admin / email_verified_at /
    failed_login_attempts / locked_until exist on users."""
    cols = {c.name for c in Base.metadata.tables["users"].columns}
    for new in (
        "username",
        "password_hash",
        "is_admin",
        "email_verified_at",
        "failed_login_attempts",
        "locked_until",
    ):
        assert new in cols, f"missing user column {new}"


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
def test_email_code_pk_and_indexes_declared() -> None:
    """batch-2m: email_codes has uuid PK + email index + active partial unique."""
    table = Base.metadata.tables["email_codes"]
    pk_cols = [c.name for c in table.primary_key.columns]
    assert pk_cols == ["id"]
    indexes = {idx.name for idx in table.indexes}
    assert "ix_email_codes_email" in indexes
    assert "uq_email_codes_active" in indexes


@pytest.mark.unit
def test_email_code_construction() -> None:
    now = datetime.now(UTC)
    row = EmailCode(
        email="a@example.com",
        code_hash="$argon2id$...",
        purpose="verify_email",
        expires_at=now,
    )
    assert row.purpose == "verify_email"
    assert row.consumed_at is None


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
def test_email_code_purpose_check_constraint_declared() -> None:
    """purpose IN ('verify_email','login') CHECK exists."""
    table = Base.metadata.tables["email_codes"]
    check_names = {
        c.name for c in table.constraints if c.__class__.__name__ == "CheckConstraint" and c.name
    }
    assert "ck_email_codes_purpose" in check_names


@pytest.mark.unit
def test_magic_link_token_construction() -> None:
    # Placeholder kept so historical test names don't break in CI logs.
    # MagicLinkToken is gone; this just asserts that fact.
    from plus_one.core.db import models as m

    assert not hasattr(m, "MagicLinkToken")


@pytest.mark.unit
def test_trip_status_check_constraint_declared() -> None:
    """Trip.status must have a DB-level CHECK against the four allowed values."""
    table = Base.metadata.tables["trips"]
    check_names = {
        c.name for c in table.constraints if c.__class__.__name__ == "CheckConstraint" and c.name
    }
    assert "ck_trips_status" in check_names


@pytest.mark.unit
def test_trip_status_check_constraint_includes_clarifying() -> None:
    """batch-2t widened the CHECK to allow ``'clarifying'``."""
    table = Base.metadata.tables["trips"]
    check = next(
        c
        for c in table.constraints
        if c.__class__.__name__ == "CheckConstraint" and c.name == "ck_trips_status"
    )
    text = str(getattr(check, "sqltext", check))
    assert "clarifying" in text


@pytest.mark.unit
def test_trip_clarifier_columns_present() -> None:
    """batch-2t: ``clarifier_questions`` + ``clarifier_answers`` JSONB columns."""
    cols = {c.name for c in Base.metadata.tables["trips"].columns}
    assert "clarifier_questions" in cols
    assert "clarifier_answers" in cols


@pytest.mark.unit
def test_email_codes_table_present() -> None:
    """batch-2m sanity: email_codes table is registered."""
    assert "email_codes" in Base.metadata.tables


@pytest.mark.unit
def test_updated_at_has_no_server_default() -> None:
    """Reviewer F3: server_default on updated_at is misleading because raw SQL
    bulk updates would bypass it. The convention is ORM-only writes; updated_at
    is set client-side via the TimestampMixin onupdate hook."""
    col = Base.metadata.tables["users"].c.updated_at
    assert col.server_default is None
