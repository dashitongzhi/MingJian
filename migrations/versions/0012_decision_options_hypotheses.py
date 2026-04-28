"""Add decision_options and hypotheses tables.

Revision ID: 0012_decision_options_hypotheses
Revises: 0011_decision_method
Create Date: 2026-04-24
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0012_decision_options_hypotheses"
down_revision = "0011_decision_method"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "decision_options",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("run_id", sa.String(length=36), sa.ForeignKey("simulation_runs.id"), nullable=False, index=True),
        sa.Column("tenant_id", sa.String(length=120), nullable=True, index=True),
        sa.Column("preset_id", sa.String(length=120), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("expected_effects", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("risks", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("evidence_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("conditions", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("ranking", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_table(
        "hypotheses",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("run_id", sa.String(length=36), sa.ForeignKey("simulation_runs.id"), nullable=False, index=True),
        sa.Column("decision_option_id", sa.String(length=36), sa.ForeignKey("decision_options.id"), nullable=True, index=True),
        sa.Column("tenant_id", sa.String(length=120), nullable=True, index=True),
        sa.Column("preset_id", sa.String(length=120), nullable=True),
        sa.Column("prediction", sa.Text(), nullable=False),
        sa.Column("time_horizon", sa.String(length=64), nullable=False, server_default="3_months"),
        sa.Column("verification_status", sa.String(length=32), nullable=False, server_default="PENDING"),
        sa.Column("actual_outcome", sa.Text(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("hypotheses")
    op.drop_table("decision_options")
