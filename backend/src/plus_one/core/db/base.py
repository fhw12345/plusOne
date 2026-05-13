"""SQLAlchemy declarative base + common mixins.

We use the modern :class:`DeclarativeBase` API (SQLAlchemy 2.0+). Models
elsewhere in the codebase inherit from :class:`Base` and may opt into
:class:`TimestampMixin` for ``created_at`` / ``updated_at`` columns.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Naming convention required for Alembic to detect constraint changes
# correctly. Without this, autogenerate produces noisy migrations.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Project-wide declarative base.

    All ORM models in Plus One inherit from this class so they share the
    same MetaData (Alembic discovers them via ``Base.metadata``).
    """

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def _utcnow() -> datetime:
    """Return current UTC time with timezone — matches Postgres timestamptz."""
    return datetime.now(UTC)


class TimestampMixin:
    """Adds ``created_at`` and ``updated_at`` columns.

    Uses ``server_default=func.now()`` so inserts work even if the
    application forgets to set the column. ``updated_at`` is application-
    side only (no ``ON UPDATE``) — set it explicitly in ``UPDATE`` paths.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=_utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=_utcnow,
        onupdate=_utcnow,
    )


def new_uuid() -> uuid.UUID:
    """Default factory for UUID primary keys."""
    return uuid.uuid4()
