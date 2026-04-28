"""Add intelligence MVP source, watch, and military mode fields.

Revision ID: 0017_intelligence_mvp_fields
Revises: 0016_dedupe_key_unique
Create Date: 2026-04-28
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0017_intelligence_mvp_fields"
down_revision = "0016_dedupe_key_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("simulation_runs", sa.Column("military_use_mode", sa.String(length=32), nullable=True))
    op.add_column("watch_rules", sa.Column("keywords", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("watch_rules", sa.Column("exclude_keywords", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("watch_rules", sa.Column("entity_tags", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("watch_rules", sa.Column("trigger_threshold", sa.Float(), nullable=False, server_default="0.0"))
    op.add_column(
        "watch_rules",
        sa.Column("min_new_evidence_count", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column("watch_rules", sa.Column("importance_threshold", sa.Float(), nullable=False, server_default="0.0"))


def downgrade() -> None:
    op.drop_column("watch_rules", "importance_threshold")
    op.drop_column("watch_rules", "min_new_evidence_count")
    op.drop_column("watch_rules", "trigger_threshold")
    op.drop_column("watch_rules", "entity_tags")
    op.drop_column("watch_rules", "exclude_keywords")
    op.drop_column("watch_rules", "keywords")
    op.drop_column("simulation_runs", "military_use_mode")
