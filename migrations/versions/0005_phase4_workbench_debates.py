"""Phase 4 workbench and Phase 5 debate schema.

Revision ID: 0005_phase4_workbench_debates
Revises: 0004_phase3_operational_views
Create Date: 2026-03-20
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0005_phase4_workbench_debates"
down_revision = "0004_phase3_operational_views"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("debate_sessions"):
        op.create_table(
            "debate_sessions",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("run_id", sa.String(length=36), sa.ForeignKey("simulation_runs.id"), nullable=True),
            sa.Column("claim_id", sa.String(length=36), sa.ForeignKey("claims.id"), nullable=True),
            sa.Column("topic", sa.Text(), nullable=False),
            sa.Column("trigger_type", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("target_type", sa.String(length=64), nullable=False),
            sa.Column("target_id", sa.String(length=120), nullable=True),
            sa.Column("context_payload", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )

    if not inspector.has_table("debate_rounds"):
        op.create_table(
            "debate_rounds",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("debate_id", sa.String(length=36), sa.ForeignKey("debate_sessions.id"), nullable=False),
            sa.Column("round_number", sa.Integer(), nullable=False),
            sa.Column("role", sa.String(length=32), nullable=False),
            sa.Column("position", sa.String(length=32), nullable=False),
            sa.Column("confidence", sa.Float(), nullable=False),
            sa.Column("arguments", sa.JSON(), nullable=False),
            sa.Column("rebuttals", sa.JSON(), nullable=False),
            sa.Column("concessions", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("debate_id", "round_number", "role"),
        )

    if not inspector.has_table("debate_verdicts"):
        op.create_table(
            "debate_verdicts",
            sa.Column("debate_id", sa.String(length=36), sa.ForeignKey("debate_sessions.id"), primary_key=True),
            sa.Column("topic", sa.Text(), nullable=False),
            sa.Column("trigger_type", sa.String(length=64), nullable=False),
            sa.Column("rounds_completed", sa.Integer(), nullable=False),
            sa.Column("verdict", sa.String(length=32), nullable=False),
            sa.Column("confidence", sa.Float(), nullable=False),
            sa.Column("winning_arguments", sa.JSON(), nullable=False),
            sa.Column("decisive_evidence", sa.JSON(), nullable=False),
            sa.Column("conditions", sa.JSON(), nullable=True),
            sa.Column("minority_opinion", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )

    decision_record_columns = {column["name"] for column in inspector.get_columns("decision_records")}
    if "debate_verdict_id" not in decision_record_columns:
        with op.batch_alter_table("decision_records") as batch_op:
            batch_op.add_column(sa.Column("debate_verdict_id", sa.String(length=36), nullable=True))
            batch_op.create_foreign_key(
                "fk_decision_records_debate_verdict_id",
                "debate_sessions",
                ["debate_verdict_id"],
                ["id"],
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    decision_record_columns = {column["name"] for column in inspector.get_columns("decision_records")}
    if "debate_verdict_id" in decision_record_columns:
        with op.batch_alter_table("decision_records") as batch_op:
            batch_op.drop_constraint("fk_decision_records_debate_verdict_id", type_="foreignkey")
            batch_op.drop_column("debate_verdict_id")
    if inspector.has_table("debate_verdicts"):
        op.drop_table("debate_verdicts")
    if inspector.has_table("debate_rounds"):
        op.drop_table("debate_rounds")
    if inspector.has_table("debate_sessions"):
        op.drop_table("debate_sessions")
