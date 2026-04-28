"""Add decision_method column to decision_records.

Revision ID: 0011_decision_method
Revises: 0010_watch_rules
Create Date: 2026-04-24
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0011_decision_method"
down_revision = "0010_watch_rules"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "decision_records",
        sa.Column(
            "decision_method",
            sa.String(length=32),
            nullable=False,
            server_default="rule_engine",
        ),
    )


def downgrade() -> None:
    op.drop_column("decision_records", "decision_method")
