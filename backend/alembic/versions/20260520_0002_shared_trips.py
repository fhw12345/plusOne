"""shared_trips: revokable public share links for trips

Revision ID: 20260520_0002
Revises: 20260513_0001
Create Date: 2026-05-20
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260520_0002"
down_revision: Union[str, Sequence[str], None] = "20260513_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "shared_trips",
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("trip_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["trip_id"],
            ["trips.id"],
            name=op.f("fk_shared_trips_trip_id_trips"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_shared_trips_created_by_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("token", name=op.f("pk_shared_trips")),
    )
    op.create_index("ix_shared_trips_trip_id", "shared_trips", ["trip_id"], unique=False)
    op.create_index("ix_shared_trips_expires_at", "shared_trips", ["expires_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_shared_trips_expires_at", table_name="shared_trips")
    op.drop_index("ix_shared_trips_trip_id", table_name="shared_trips")
    op.drop_table("shared_trips")
