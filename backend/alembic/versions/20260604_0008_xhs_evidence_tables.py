"""xhs evidence tables: posts, images, and candidate/query matches

Revision ID: 20260604_0008
Revises: 20260522_0007
Create Date: 2026-06-04

Stores only factual XHS crawl output. Coverage summaries, crawl queues, and
aggregate reports remain derived artifacts and are intentionally not stored
here.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260604_0008"
down_revision: str | Sequence[str] | None = "20260522_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "xhs_posts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("note_id", sa.String(length=80), nullable=False),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("author", sa.Text(), nullable=False),
        sa.Column("likes", sa.Integer(), nullable=False),
        sa.Column("comments", sa.Integer(), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_xhs_posts")),
        sa.UniqueConstraint("note_id", name=op.f("uq_xhs_posts_note_id")),
    )
    op.create_index("ix_xhs_posts_note_id", "xhs_posts", ["note_id"], unique=False)
    op.create_index("ix_xhs_posts_canonical_url", "xhs_posts", ["canonical_url"], unique=False)

    op.create_table(
        "xhs_post_images",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("post_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("local_url", sa.Text(), nullable=False),
        sa.Column("local_path", sa.Text(), nullable=False),
        sa.Column("byte_count", sa.Integer(), nullable=True),
        sa.Column("content_type", sa.String(length=120), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["post_id"], ["xhs_posts.id"], name=op.f("fk_xhs_post_images_post_id_xhs_posts"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_xhs_post_images")),
        sa.UniqueConstraint("post_id", "local_url", name="uq_xhs_post_images_post_local_url"),
    )
    op.create_index("ix_xhs_post_images_post_id", "xhs_post_images", ["post_id"], unique=False)

    op.create_table(
        "xhs_post_matches",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("post_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate", sa.Text(), nullable=False),
        sa.Column("destination", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=60), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("relevance_score", sa.Float(), nullable=True),
        sa.Column("matched_terms", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("quality_version", sa.Integer(), nullable=True),
        sa.Column("authenticity_score", sa.Float(), nullable=True),
        sa.Column("authenticity_reasons", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["post_id"], ["xhs_posts.id"], name=op.f("fk_xhs_post_matches_post_id_xhs_posts"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_xhs_post_matches")),
        sa.UniqueConstraint("post_id", "candidate", "query", name="uq_xhs_post_matches_post_candidate_query"),
    )
    op.create_index("ix_xhs_post_matches_candidate", "xhs_post_matches", ["candidate"], unique=False)
    op.create_index("ix_xhs_post_matches_query", "xhs_post_matches", ["query"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_xhs_post_matches_query", table_name="xhs_post_matches")
    op.drop_index("ix_xhs_post_matches_candidate", table_name="xhs_post_matches")
    op.drop_table("xhs_post_matches")
    op.drop_index("ix_xhs_post_images_post_id", table_name="xhs_post_images")
    op.drop_table("xhs_post_images")
    op.drop_index("ix_xhs_posts_canonical_url", table_name="xhs_posts")
    op.drop_index("ix_xhs_posts_note_id", table_name="xhs_posts")
    op.drop_table("xhs_posts")
