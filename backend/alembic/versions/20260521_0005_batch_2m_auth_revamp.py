"""batch-2m auth revamp: users credential columns + email_codes; drop magic_link_tokens

Revision ID: 20260521_0005
Revises: 20260520_0004
Create Date: 2026-05-21

Adds username / password_hash / is_admin / email_verified_at /
failed_login_attempts / locked_until columns to ``users``, creates the
new ``email_codes`` table (single-use verify/login codes), and drops
``magic_link_tokens`` outright.

No data seeding — admin row is created at app startup via
``ensure_admin_user()`` so migrations stay env-free and idempotent.

Downgrade re-creates ``magic_link_tokens`` schema (no data restore —
magic-link is dead) and drops the new columns / tables.
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260521_0005"
down_revision: Union[str, Sequence[str], None] = "20260520_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- users: add credential columns ----------------------------------
    # Add nullable first so any existing rows survive the migration.
    # Then backfill with placeholder values + lock the schema down with
    # NOT NULL. Backfill values are intentionally unusable
    # (random username, empty password hash) — pre-batch-2m DBs only
    # held demo magic-link users in dev.
    op.add_column("users", sa.Column("username", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("password_hash", sa.Text(), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "is_admin",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "users",
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "failed_login_attempts",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "users",
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
    )

    # Backfill any pre-existing rows with disposable values so we can
    # apply NOT NULL. Username is forced lowercase + a per-row suffix.
    op.execute(
        sa.text(
            "UPDATE users "
            "SET username = 'legacy_' || substr(replace(id::text, '-', ''), 1, 16), "
            "    password_hash = '' "
            "WHERE username IS NULL OR password_hash IS NULL"
        )
    )

    op.alter_column("users", "username", nullable=False)
    op.alter_column("users", "password_hash", nullable=False)

    # Drop the server_defaults so the ORM-side defaults are authoritative
    # going forward — server_default only exists to satisfy NOT NULL on
    # the migration's UPDATE.
    op.alter_column("users", "is_admin", server_default=None)
    op.alter_column("users", "failed_login_attempts", server_default=None)

    op.create_unique_constraint(
        op.f("uq_users_username"), "users", ["username"]
    )
    op.create_check_constraint(
        "ck_users_username_lowercase",
        "users",
        "username = lower(username)",
    )

    # --- email_codes (new) ----------------------------------------------
    op.create_table(
        "email_codes",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("code_hash", sa.Text(), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "purpose IN ('verify_email', 'login')",
            name="ck_email_codes_purpose",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_codes")),
    )
    op.create_index("ix_email_codes_email", "email_codes", ["email"], unique=False)
    # Partial unique: one active row per (email, purpose). Re-issuing a
    # code requires consuming the previous row first.
    op.create_index(
        "uq_email_codes_active",
        "email_codes",
        ["email", "purpose"],
        unique=True,
        postgresql_where=sa.text("consumed_at IS NULL"),
    )

    # --- drop magic_link_tokens -----------------------------------------
    op.drop_index(
        "uq_magic_link_tokens_user_id_unconsumed", table_name="magic_link_tokens"
    )
    op.drop_index("ix_magic_link_tokens_expires_at", table_name="magic_link_tokens")
    op.drop_index(op.f("ix_magic_link_tokens_user_id"), table_name="magic_link_tokens")
    op.drop_table("magic_link_tokens")


def downgrade() -> None:
    # Re-create magic_link_tokens shell (no data restore).
    op.create_table(
        "magic_link_tokens",
        sa.Column("token", sa.String(length=128), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_magic_link_tokens_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("token", name=op.f("pk_magic_link_tokens")),
    )
    op.create_index(
        op.f("ix_magic_link_tokens_user_id"),
        "magic_link_tokens",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_magic_link_tokens_expires_at",
        "magic_link_tokens",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        "uq_magic_link_tokens_user_id_unconsumed",
        "magic_link_tokens",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("consumed_at IS NULL"),
    )

    op.drop_index("uq_email_codes_active", table_name="email_codes")
    op.drop_index("ix_email_codes_email", table_name="email_codes")
    op.drop_table("email_codes")

    op.drop_constraint("ck_users_username_lowercase", "users", type_="check")
    op.drop_constraint(op.f("uq_users_username"), "users", type_="unique")
    op.drop_column("users", "locked_until")
    op.drop_column("users", "failed_login_attempts")
    op.drop_column("users", "email_verified_at")
    op.drop_column("users", "is_admin")
    op.drop_column("users", "password_hash")
    op.drop_column("users", "username")
