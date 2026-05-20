"""tool_cache: DB-backed cache for real-mode tool responses

Revision ID: 20260520_0003
Revises: 20260520_0002
Create Date: 2026-05-20
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260520_0003"
down_revision: Union[str, Sequence[str], None] = "20260520_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tool_cache",
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("source", "key_hash", name=op.f("pk_tool_cache")),
    )
    op.create_index(
        "ix_tool_cache_expires_at", "tool_cache", ["expires_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_tool_cache_expires_at", table_name="tool_cache")
    op.drop_table("tool_cache")
