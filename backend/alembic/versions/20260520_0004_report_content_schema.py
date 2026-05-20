"""report content schema: documentation marker for translations key

Revision ID: 20260520_0004
Revises: 20260520_0003
Create Date: 2026-05-20

No-op DDL migration. PRD batch 2k §6.3 chose Option B — keep one
``content`` JSONB column on ``reports`` and extend the in-document
shape from:

    {"items": [<JoinedItem>...]}

to:

    {
      "items": [<JoinedItem>...],
      "translations": {"en": [<JoinedItem>...], "zh": [<JoinedItem>...]}
    }

JSONB already accepts the new ``translations`` key without DDL; no
column add, no nullability flip, no index needed. The migration exists
so ``alembic history`` records the schema-shape change for future
auditability (e.g. when a v2 backfill script needs to identify reports
predating this revision, it can target ``WHERE alembic_version <
'20260520_0004'`` semantically).

Existing reports keep ``{"items": [...]}`` and the frontend's fallback
path (``content.translations[lang] ?? content.items``) renders them
correctly without a backfill.
"""

from collections.abc import Sequence
from typing import Union

# revision identifiers, used by Alembic.
revision: str = "20260520_0004"
down_revision: Union[str, Sequence[str], None] = "20260520_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Documentation-only marker. JSONB tolerates the new ``translations``
    # key without DDL — see module docstring.
    pass


def downgrade() -> None:
    # No-op upgrade has nothing to undo. We deliberately do NOT strip
    # the ``translations`` key from existing rows on downgrade; the
    # frontend's fallback path handles its presence harmlessly.
    pass
