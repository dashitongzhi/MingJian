"""Backfill raw knowledge status for already materialized inline ingest rows.

Revision ID: 0007_backfill_raw_knowledge_status
Revises: 0006_phase6_runtime_hardening
Create Date: 2026-03-29
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0007_backfill_raw_knowledge_status"
down_revision = "0006_phase6_runtime_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("raw_source_items") or not inspector.has_table("normalized_items"):
        return

    op.execute(
        sa.text(
            """
            UPDATE raw_source_items
            SET
                knowledge_status = 'COMPLETED',
                processed_at = COALESCE(raw_source_items.processed_at, normalized_items.normalized_at),
                last_error = NULL
            FROM normalized_items
            WHERE normalized_items.raw_source_item_id = raw_source_items.id
              AND raw_source_items.knowledge_status IN ('PENDING', 'PROCESSING')
            """
        )
    )


def downgrade() -> None:
    return None
