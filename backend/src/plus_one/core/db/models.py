"""ORM models — User, Profile, Companion, Trip, Report, Feedback, MagicLinkToken.

Schema mirrors the PRD (docs/prd.md §8 Profile schema b). Notable choices:

- All primary keys are UUIDs (server-side via ``new_uuid``); avoids
  exposing sequence values in URLs and simplifies eventual sharding.
- All timestamps are ``timestamptz`` and TimestampMixin handles them.
- Companions belong to a User (1:N) and don't have their own accounts —
  per PRD §8 (rejected multi-account complexity).
- Trips reference a snapshot of which companions were involved (m:n via
  ``trip_companions`` association).
- Reports are versioned per trip — a trip can be regenerated; older
  reports are preserved for history / eval comparisons.
- Feedback is per-card-per-trip with optional ``for_companion_id`` for
  the "for whom?" follow-up question (PRD §8 dynamic learning).
- MagicLinkToken is the single-use email login token; consumed on first
  successful exchange for a JWT.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    Table,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from plus_one.core.db.base import Base, TimestampMixin, new_uuid

# === User ================================================================


class User(Base, TimestampMixin):
    """A registered Plus One user."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=new_uuid)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    profile: Mapped[Profile | None] = relationship(
        "Profile",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    companions: Mapped[list[Companion]] = relationship(
        "Companion",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    trips: Mapped[list[Trip]] = relationship(
        "Trip",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r}>"


# === Profile (the user's own preferences) ================================


class Profile(Base, TimestampMixin):
    """The user's own travel-preference profile (PRD schema b)."""

    __tablename__ = "profiles"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    # JSON blobs — schema is enforced at the Pydantic boundary in services/,
    # not at the DB layer. PRD §8 schema-b shape.
    demographics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    travel_style: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    explicit_preferences: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    visited_cities: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    # implicit_preferences exists for v2 (learning algorithm); MVP keeps it empty.
    implicit_preferences: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )

    user: Mapped[User] = relationship("User", back_populates="profile")


# === Companion ===========================================================


class Companion(Base, TimestampMixin):
    """A travel companion the user fills out for (PRD §8: companions don't have accounts)."""

    __tablename__ = "companions"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_companion_user_name"),)

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    explicit_preferences: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    constraints: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    user: Mapped[User] = relationship("User", back_populates="companions")


# === Trip ================================================================


# Association table for trip <-> companion m:n
trip_companions = Table(
    "trip_companions",
    Base.metadata,
    Column(
        "trip_id",
        PGUUID(as_uuid=True),
        ForeignKey("trips.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "companion_id",
        PGUUID(as_uuid=True),
        ForeignKey("companions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


# Valid Trip.status values. Enforced at the DB layer via CHECK so a typo
# in worker code can't silently corrupt state.
_TRIP_STATUSES = ("pending", "running", "complete", "aborted")


class Trip(Base, TimestampMixin):
    """One planning request (input + reference to generated reports)."""

    __tablename__ = "trips"
    __table_args__ = (
        # Note: the naming convention prepends "ck_<table>_" to the
        # constraint name, so the resulting DB-level constraint name is
        # "ck_trips_status".
        CheckConstraint(
            f"status IN {_TRIP_STATUSES}",
            name="status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    destination: Mapped[str] = mapped_column(String(200), nullable=False)
    date_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    date_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    budget_amount: Mapped[int | None] = mapped_column(nullable=True)
    budget_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    free_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Status of the in-flight cycle. Stays "pending" -> "running" -> one of
    # "complete" | "aborted". Workers update; readers poll or subscribe via SSE.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")

    user: Mapped[User] = relationship("User", back_populates="trips")
    companions: Mapped[list[Companion]] = relationship(
        "Companion",
        secondary=trip_companions,
        lazy="selectin",
    )
    reports: Mapped[list[Report]] = relationship(
        "Report",
        back_populates="trip",
        cascade="all, delete-orphan",
        order_by="Report.created_at",
    )
    shared_trips: Mapped[list[SharedTrip]] = relationship(
        "SharedTrip",
        back_populates="trip",
        cascade="all, delete-orphan",
    )


# === Report ==============================================================


class Report(Base, TimestampMixin):
    """A generated report for a trip. One trip can have many (regenerations)."""

    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=new_uuid)
    trip_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("trips.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Full structured output: TL;DR + tabs + cards. Schema enforced by
    # services/, not the DB.
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    # Cycle trace (events, timing, token cost) for observability.
    trace: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    # Cumulative token usage across all LLM calls in this report.
    input_tokens: Mapped[int] = mapped_column(nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(nullable=False, default=0)

    trip: Mapped[Trip] = relationship("Trip", back_populates="reports")


# === SharedTrip ==========================================================


class SharedTrip(Base, TimestampMixin):
    """A revokable public share link for a Trip.

    The ``token`` is a 192-bit ``secrets.token_urlsafe(24)`` value used as
    the only secret in the unauthed GET path ``/api/shared/{token}``.
    ``ondelete='CASCADE'`` on both FKs means dropping the Trip or User
    automatically drops the share row (DB-level belt). The ORM-side
    ``Trip.shared_trips`` relationship adds ``cascade='all, delete-orphan'``
    so ``session.delete(trip)`` collects children inside the unit-of-work
    (ORM-level suspenders).
    """

    __tablename__ = "shared_trips"
    __table_args__ = (
        Index("ix_shared_trips_trip_id", "trip_id"),
        Index("ix_shared_trips_expires_at", "expires_at"),
    )

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    trip_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("trips.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    trip: Mapped[Trip] = relationship("Trip", back_populates="shared_trips")


# === Feedback ============================================================


class Feedback(Base, TimestampMixin):
    """Per-card thumbs/text feedback. Drives Profile learning (v2)."""

    __tablename__ = "feedback"
    __table_args__ = (Index("ix_feedback_trip_card", "trip_id", "card_id"),)

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=new_uuid)
    trip_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("trips.id", ondelete="CASCADE"),
        nullable=False,
    )
    card_id: Mapped[str] = mapped_column(String(100), nullable=False)
    for_companion_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companions.id", ondelete="SET NULL"),
        nullable=True,
    )
    # 'thumb_up' | 'thumb_down'
    signal: Mapped[str] = mapped_column(String(20), nullable=False)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)


# === MagicLinkToken ======================================================


class MagicLinkToken(Base):
    """Single-use token issued on /auth/magic-link request, exchanged for JWT.

    No TimestampMixin: ``issued_at`` is enough; ``updated_at`` semantics
    don't apply (we never update tokens — we either consume or expire them).
    """

    __tablename__ = "magic_link_tokens"
    __table_args__ = (
        # Cleanup query "DELETE WHERE expires_at < now()" should not full-scan.
        Index("ix_magic_link_tokens_expires_at", "expires_at"),
        # At most one live (unconsumed) token per user — replay/abuse guard.
        # Partial unique requires a Postgres-only WHERE clause; harmless on
        # other dialects, which simply ignore postgresql_where.
        Index(
            "uq_magic_link_tokens_user_id_unconsumed",
            "user_id",
            unique=True,
            postgresql_where=text("consumed_at IS NULL"),
        ),
    )

    token: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# === ToolCache ===========================================================


class ToolCache(Base, TimestampMixin):
    """DB-backed cache for real-mode tool responses.

    Composite PK ``(source, key_hash)`` — one row per source/query pair.
    ``payload`` holds the raw tool response list as JSONB; per-source
    TTLs live in ``core/tools/_cache_db.py::_TTL_BY_SOURCE``.

    Indexed on ``expires_at`` so a future cleanup job can sweep stale
    rows without a full table scan.
    """

    __tablename__ = "tool_cache"
    __table_args__ = (Index("ix_tool_cache_expires_at", "expires_at"),)

    source: Mapped[str] = mapped_column(String(50), primary_key=True)
    key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    payload: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
