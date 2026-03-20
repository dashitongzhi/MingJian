"""Phase 2 corporate simulation schema.

Revision ID: 0002_phase2_corporate_simulation
Revises: 0001_phase1_bootstrap
Create Date: 2026-03-17
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0002_phase2_corporate_simulation"
down_revision = "0001_phase1_bootstrap"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "company_profiles",
        sa.Column("id", sa.String(length=120), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("market", sa.String(length=120), nullable=False),
        sa.Column("attributes", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "simulation_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("company_id", sa.String(length=120), sa.ForeignKey("company_profiles.id"), nullable=False),
        sa.Column("domain_id", sa.String(length=64), nullable=False),
        sa.Column("actor_template", sa.String(length=120), nullable=False),
        sa.Column("execution_mode", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("tick_count", sa.Integer(), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "state_snapshots",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("run_id", sa.String(length=36), sa.ForeignKey("simulation_runs.id"), nullable=False),
        sa.Column("tick", sa.Integer(), nullable=False),
        sa.Column("actor_id", sa.String(length=120), nullable=False),
        sa.Column("state", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "tick", "actor_id"),
    )

    op.create_table(
        "decision_records",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("run_id", sa.String(length=36), sa.ForeignKey("simulation_runs.id"), nullable=False),
        sa.Column("tick", sa.Integer(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("actor_id", sa.String(length=120), nullable=False),
        sa.Column("action_id", sa.String(length=120), nullable=False),
        sa.Column("why_selected", sa.Text(), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("policy_rule_ids", sa.JSON(), nullable=False),
        sa.Column("expected_effect", sa.JSON(), nullable=False),
        sa.Column("actual_effect", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "tick", "sequence"),
    )

    op.create_table(
        "generated_reports",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("run_id", sa.String(length=36), sa.ForeignKey("simulation_runs.id"), nullable=False),
        sa.Column("company_id", sa.String(length=120), sa.ForeignKey("company_profiles.id")),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("report_format", sa.String(length=32), nullable=False),
        sa.Column("sections", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("generated_reports")
    op.drop_table("decision_records")
    op.drop_table("state_snapshots")
    op.drop_table("simulation_runs")
    op.drop_table("company_profiles")
