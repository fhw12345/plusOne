"""batch-2t: clarifier loop columns + widen trips.status CHECK

Revision ID: 20260522_0007
Revises: 20260521_0005
Create Date: 2026-05-22

Adds two nullable JSONB columns to ``trips`` for the clarifier loop:

  * ``clarifier_questions`` — array of ``{id, text}`` produced by the
    LLM at trip-create time; populated only when the clarifier asked
    1–3 questions, NULL otherwise (skipped, 0 questions, legacy).
  * ``clarifier_answers``   — array of ``{id, text}`` from the user.
    NULL means "skipped" or "not yet collected"; empty list is
    reserved (we write NULL instead).

Also widens the ``ck_trips_status`` CHECK constraint to allow the new
``'clarifying'`` value (in addition to the existing
``pending / running / complete / aborted``). ``pending`` is kept for
backward compatibility with in-flight rows and the transient
pre-clarifier insert state.

Downgrade drops the two columns and reverts the CHECK to the narrower
set. Destructive for any rows currently in ``'clarifying'`` (the row
itself stays, the CHECK would reject the value) — acceptable, downgrade
is a manual rollback action.
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260522_0007"
down_revision: Union[str, Sequence[str], None] = "20260521_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # New nullable JSONB columns. Nullable because pre-deploy trips and
    # trips where the clarifier returned 0 questions don't need a value.
    op.add_column(
        "trips",
        sa.Column("clarifier_questions", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "trips",
        sa.Column("clarifier_answers", postgresql.JSONB(), nullable=True),
    )

    # Drop + recreate the status CHECK to widen the allowed set with
    # ``'clarifying'``. The original constraint was created with name
    # ``ck_trips_status`` in the initial migration.
    op.drop_constraint("ck_trips_status", "trips", type_="check")
    op.create_check_constraint(
        "ck_trips_status",
        "trips",
        "status IN ('pending', 'clarifying', 'running', 'complete', 'aborted')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_trips_status", "trips", type_="check")
    op.create_check_constraint(
        "ck_trips_status",
        "trips",
        "status IN ('pending', 'running', 'complete', 'aborted')",
    )
    op.drop_column("trips", "clarifier_answers")
    op.drop_column("trips", "clarifier_questions")
