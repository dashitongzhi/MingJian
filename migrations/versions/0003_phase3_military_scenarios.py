"""Phase 3 military scenario schema.

Revision ID: 0003_phase3_military_scenarios
Revises: 0002_phase2_corporate_simulation
Create Date: 2026-03-17
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0003_phase3_military_scenarios"
down_revision = "0002_phase2_corporate_simulation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "force_profiles",
        sa.Column("id", sa.String(length=120), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("theater", sa.String(length=120), nullable=False),
        sa.Column("attributes", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    with op.batch_alter_table("simulation_runs", recreate="auto") as batch_op:
        batch_op.alter_column("company_id", existing_type=sa.String(length=120), nullable=True)
        batch_op.add_column(sa.Column("force_id", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("parent_run_id", sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            "fk_simulation_runs_force_id",
            "force_profiles",
            ["force_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            "fk_simulation_runs_parent_run_id",
            "simulation_runs",
            ["parent_run_id"],
            ["id"],
        )

    op.create_table(
        "scenario_branches",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("run_id", sa.String(length=36), sa.ForeignKey("simulation_runs.id"), nullable=False),
        sa.Column("parent_run_id", sa.String(length=36), sa.ForeignKey("simulation_runs.id"), nullable=False),
        sa.Column("fork_step", sa.Integer(), nullable=False),
        sa.Column("assumptions", sa.JSON(), nullable=False),
        sa.Column("decision_deltas", sa.JSON(), nullable=False),
        sa.Column("kpi_trajectory", sa.JSON(), nullable=False),
        sa.Column("probability_band", sa.String(length=32), nullable=False),
        sa.Column("notable_events", sa.JSON(), nullable=False),
        sa.Column("evidence_summary", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id"),
    )

    with op.batch_alter_table("generated_reports", recreate="auto") as batch_op:
        batch_op.add_column(sa.Column("force_id", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("scenario_id", sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            "fk_generated_reports_force_id",
            "force_profiles",
            ["force_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            "fk_generated_reports_scenario_id",
            "scenario_branches",
            ["scenario_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("generated_reports", recreate="always") as batch_op:
        batch_op.drop_constraint("fk_generated_reports_scenario_id", type_="foreignkey")
        batch_op.drop_constraint("fk_generated_reports_force_id", type_="foreignkey")
        batch_op.drop_column("scenario_id")
        batch_op.drop_column("force_id")

    op.drop_table("scenario_branches")

    with op.batch_alter_table("simulation_runs", recreate="always") as batch_op:
        batch_op.drop_constraint("fk_simulation_runs_parent_run_id", type_="foreignkey")
        batch_op.drop_constraint("fk_simulation_runs_force_id", type_="foreignkey")
        batch_op.drop_column("parent_run_id")
        batch_op.drop_column("force_id")
        batch_op.alter_column("company_id", existing_type=sa.String(length=120), nullable=False)

    op.drop_table("force_profiles")
