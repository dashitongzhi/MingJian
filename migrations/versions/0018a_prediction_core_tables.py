"""Add prediction core tables and source cursor states.

Revision ID: 0018a_prediction_core_tables
Revises: 0018_incremental_source_changes
Create Date: 2026-05-03
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0018a_prediction_core_tables"
down_revision = "0018_incremental_source_changes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- prediction_series ---
    op.create_table(
        "prediction_series",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(120), index=True),
        sa.Column("preset_id", sa.String(120), index=True),
        sa.Column("subject_type", sa.String(64), nullable=False, index=True),
        sa.Column("subject_id", sa.String(120), index=True),
        sa.Column("domain_id", sa.String(64), nullable=False, index=True),
        sa.Column("source_type", sa.String(64), nullable=False, index=True),
        sa.Column("source_id", sa.String(36), nullable=False, index=True),
        sa.Column("source_run_id", sa.String(36), sa.ForeignKey("simulation_runs.id"), index=True),
        sa.Column("decision_option_id", sa.String(36), sa.ForeignKey("decision_options.id"), index=True),
        sa.Column("hypothesis_id", sa.String(36), sa.ForeignKey("hypotheses.id"), index=True),
        sa.Column("status", sa.String(32), default="ACTIVE", nullable=False, index=True),
        sa.Column("current_version_id", sa.String(36), index=True),
        sa.Column("series_metadata", sa.JSON, default=dict, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("source_type", "source_id"),
    )

    # --- prediction_versions ---
    op.create_table(
        "prediction_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("series_id", sa.String(36), sa.ForeignKey("prediction_series.id"), nullable=False, index=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("simulation_runs.id"), index=True),
        sa.Column("base_version_id", sa.String(36), sa.ForeignKey("prediction_versions.id"), index=True),
        sa.Column("parent_version_id", sa.String(36), sa.ForeignKey("prediction_versions.id"), index=True),
        sa.Column("hypothesis_id", sa.String(36), sa.ForeignKey("hypotheses.id"), index=True),
        sa.Column("decision_option_id", sa.String(36), sa.ForeignKey("decision_options.id"), index=True),
        sa.Column("version_number", sa.Integer, nullable=False),
        sa.Column("trigger_type", sa.String(64), nullable=False, index=True),
        sa.Column("trigger_ref_id", sa.String(120), index=True),
        sa.Column("trigger_event_id", sa.String(120), index=True),
        sa.Column("prediction_text", sa.Text, nullable=False),
        sa.Column("time_horizon", sa.String(64), default="3_months", nullable=False),
        sa.Column("probability", sa.Float, default=0.5, nullable=False),
        sa.Column("confidence", sa.Float, default=0.5, nullable=False),
        sa.Column("status", sa.String(32), default="ACTIVE", nullable=False, index=True),
        sa.Column("summary_delta", sa.Text),
        sa.Column("version_metadata", sa.JSON, default=dict, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("superseded_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("series_id", "version_number"),
        sa.CheckConstraint("probability >= 0 AND probability <= 1", name="ck_pv_probability"),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_pv_confidence"),
        sa.CheckConstraint("version_number >= 1", name="ck_pv_version_number"),
    )

    # --- prediction_evidence_links ---
    op.create_table(
        "prediction_evidence_links",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("series_id", sa.String(36), sa.ForeignKey("prediction_series.id"), nullable=False, index=True),
        sa.Column("version_id", sa.String(36), sa.ForeignKey("prediction_versions.id"), nullable=False, index=True),
        sa.Column("prediction_version_id", sa.String(36), sa.ForeignKey("prediction_versions.id"), nullable=False, index=True),
        sa.Column("evidence_item_id", sa.String(36), sa.ForeignKey("evidence_items.id"), index=True),
        sa.Column("claim_id", sa.String(36), sa.ForeignKey("claims.id"), index=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("simulation_runs.id"), index=True),
        sa.Column("decision_record_id", sa.String(36), sa.ForeignKey("decision_records.id"), index=True),
        sa.Column("link_type", sa.String(32), default="supporting", nullable=False),
        sa.Column("impact_score", sa.Float, default=0.0, nullable=False),
        sa.Column("impact_direction", sa.String(32), default="unknown", nullable=False),
        sa.Column("impact_reason", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("version_id", "evidence_item_id", "claim_id"),
        sa.CheckConstraint("impact_score >= 0 AND impact_score <= 1", name="ck_pel_impact_score"),
    )

    # --- prediction_revision_jobs ---
    op.create_table(
        "prediction_revision_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("series_id", sa.String(36), sa.ForeignKey("prediction_series.id"), nullable=False, index=True),
        sa.Column("base_version_id", sa.String(36), sa.ForeignKey("prediction_versions.id"), index=True),
        sa.Column("claim_id", sa.String(36), sa.ForeignKey("claims.id"), index=True),
        sa.Column("trigger_claim_id", sa.String(36), sa.ForeignKey("claims.id"), index=True),
        sa.Column("evidence_item_id", sa.String(36), sa.ForeignKey("evidence_items.id"), index=True),
        sa.Column("trigger_evidence_item_id", sa.String(36), sa.ForeignKey("evidence_items.id"), index=True),
        sa.Column("trigger_topic", sa.String(128), index=True),
        sa.Column("reason", sa.Text),
        sa.Column("status", sa.String(32), default="PENDING", nullable=False, index=True),
        sa.Column("revision_run_id", sa.String(36), sa.ForeignKey("simulation_runs.id"), index=True),
        sa.Column("new_run_id", sa.String(36), sa.ForeignKey("simulation_runs.id"), index=True),
        sa.Column("new_version_id", sa.String(36), sa.ForeignKey("prediction_versions.id"), index=True),
        sa.Column("lease_owner", sa.String(120), index=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), index=True),
        sa.Column("processing_attempts", sa.Integer, default=0, nullable=False),
        sa.Column("attempts", sa.Integer, default=0, nullable=False),
        sa.Column("last_error", sa.Text),
        sa.Column("job_metadata", sa.JSON, default=dict, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("attempts >= 0", name="ck_prj_attempts"),
    )

def downgrade() -> None:
    op.drop_table("prediction_revision_jobs")
    op.drop_table("prediction_evidence_links")
    op.drop_table("prediction_versions")
    op.drop_table("prediction_series")
