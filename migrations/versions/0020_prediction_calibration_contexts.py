"""Add prediction calibration context tables.

Revision ID: 0020_prediction_calibration_contexts
Revises: 0019_prediction_backtest_records
Create Date: 2026-05-03
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0020_prediction_calibration_contexts"
down_revision = "0019_prediction_backtest_records"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rule_accuracies",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("rule_id", sa.String(length=128), nullable=False),
        sa.Column("domain_id", sa.String(length=32), nullable=False),
        sa.Column("tenant_id", sa.String(length=120), nullable=True),
        sa.Column("total_predictions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("confirmed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("refuted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("partial", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("accuracy_score", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("weight_multiplier", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("last_calculated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_rule_accuracies_rule_id", "rule_accuracies", ["rule_id"])
    op.create_index("ix_rule_accuracies_domain_id", "rule_accuracies", ["domain_id"])
    op.create_index("ix_rule_accuracies_tenant_id", "rule_accuracies", ["tenant_id"])

    op.create_table(
        "source_trust_scores",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("source_url_pattern", sa.String(length=256), nullable=False),
        sa.Column("tenant_id", sa.String(length=120), nullable=True),
        sa.Column("total_evidence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("evidence_confirmed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("evidence_refuted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("trust_score", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("last_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_source_trust_scores_source_type", "source_trust_scores", ["source_type"])
    op.create_index("ix_source_trust_scores_tenant_id", "source_trust_scores", ["tenant_id"])

    op.create_table(
        "prediction_calibration_contexts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(length=36),
            sa.ForeignKey("simulation_runs.id"),
            nullable=False,
        ),
        sa.Column(
            "prediction_version_id",
            sa.String(length=36),
            sa.ForeignKey("prediction_versions.id"),
            nullable=True,
        ),
        sa.Column("historical_versions_injected", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rule_weights_applied", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("source_trust_applied", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("confidence_adjustment", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_prediction_calibration_contexts_run_id",
        "prediction_calibration_contexts",
        ["run_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_prediction_calibration_contexts_run_id", table_name="prediction_calibration_contexts")
    op.drop_table("prediction_calibration_contexts")
    op.drop_index("ix_source_trust_scores_tenant_id", table_name="source_trust_scores")
    op.drop_index("ix_source_trust_scores_source_type", table_name="source_trust_scores")
    op.drop_table("source_trust_scores")
    op.drop_index("ix_rule_accuracies_tenant_id", table_name="rule_accuracies")
    op.drop_index("ix_rule_accuracies_domain_id", table_name="rule_accuracies")
    op.drop_index("ix_rule_accuracies_rule_id", table_name="rule_accuracies")
    op.drop_table("rule_accuracies")
