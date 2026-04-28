"""Add calibration_records table.

Revision ID: 0013_calibration_records
Revises: 0012_decision_options_hypotheses
Create Date: 2026-04-24
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0013_calibration_records"
down_revision = "0012_decision_options_hypotheses"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "calibration_records",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("domain_id", sa.String(length=32), nullable=False, index=True),
        sa.Column("tenant_id", sa.String(length=120), nullable=True, index=True),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_hypotheses", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("confirmed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("refuted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("partial", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pending", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("calibration_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("rule_accuracy", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("calibration_records")
