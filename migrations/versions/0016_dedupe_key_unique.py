"""Add unique constraint on raw_source_items.dedupe_key.

Revision ID: 0016_dedupe_key_unique
Revises: 0015_operational_completion
Create Date: 2026-04-27
"""

from __future__ import annotations

from alembic import op


revision = "0016_dedupe_key_unique"
down_revision = "0015_operational_completion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("raw_source_items") as batch_op:
        batch_op.create_unique_constraint("uq_raw_source_items_dedupe_key", ["dedupe_key"])


def downgrade() -> None:
    with op.batch_alter_table("raw_source_items") as batch_op:
        batch_op.drop_constraint("uq_raw_source_items_dedupe_key", type_="unique")
