"""Add strategic session tracking and snapshot history tables.

Revision ID: 0008_strategic_sessions_history
Revises: 0007_backfill_raw_knowledge_status
Create Date: 2026-03-29
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0008_strategic_sessions_history"
down_revision = "0007_backfill_raw_knowledge_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "strategic_sessions",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("topic", sa.Text(), nullable=False),
        sa.Column("domain_id", sa.String(length=32), nullable=False),
        sa.Column("subject_id", sa.String(length=120), nullable=True),
        sa.Column("subject_name", sa.String(length=255), nullable=True),
        sa.Column("market", sa.String(length=120), nullable=True),
        sa.Column("theater", sa.String(length=120), nullable=True),
        sa.Column("actor_template", sa.String(length=120), nullable=True),
        sa.Column("tick_count", sa.Integer(), nullable=True),
        sa.Column("tenant_id", sa.String(length=120), nullable=True),
        sa.Column("preset_id", sa.String(length=120), nullable=True),
        sa.Column("source_preferences", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("latest_brief_summary", sa.Text(), nullable=True),
        sa.Column("latest_run_summary", sa.Text(), nullable=True),
        sa.Column("latest_debate_verdict", sa.String(length=32), nullable=True),
        sa.Column("latest_briefed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latest_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_strategic_sessions_subject_id", "strategic_sessions", ["subject_id"])
    op.create_index("ix_strategic_sessions_tenant_id", "strategic_sessions", ["tenant_id"])
    op.create_index("ix_strategic_sessions_preset_id", "strategic_sessions", ["preset_id"])
    op.create_index("ix_strategic_sessions_latest_briefed_at", "strategic_sessions", ["latest_briefed_at"])
    op.create_index("ix_strategic_sessions_latest_run_at", "strategic_sessions", ["latest_run_at"])

    op.create_table(
        "strategic_briefs",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("session_id", sa.String(length=36), sa.ForeignKey("strategic_sessions.id"), nullable=False),
        sa.Column("tenant_id", sa.String(length=120), nullable=True),
        sa.Column("preset_id", sa.String(length=120), nullable=True),
        sa.Column("domain_id", sa.String(length=32), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("source_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("analysis_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_strategic_briefs_session_id", "strategic_briefs", ["session_id"])
    op.create_index("ix_strategic_briefs_tenant_id", "strategic_briefs", ["tenant_id"])
    op.create_index("ix_strategic_briefs_preset_id", "strategic_briefs", ["preset_id"])

    op.create_table(
        "strategic_run_snapshots",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("session_id", sa.String(length=36), sa.ForeignKey("strategic_sessions.id"), nullable=False),
        sa.Column("tenant_id", sa.String(length=120), nullable=True),
        sa.Column("preset_id", sa.String(length=120), nullable=True),
        sa.Column("ingest_run_id", sa.String(length=36), nullable=True),
        sa.Column("simulation_run_id", sa.String(length=36), nullable=True),
        sa.Column("debate_id", sa.String(length=36), nullable=True),
        sa.Column("generated_report_id", sa.String(length=36), nullable=True),
        sa.Column("result_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_strategic_run_snapshots_session_id", "strategic_run_snapshots", ["session_id"])
    op.create_index("ix_strategic_run_snapshots_tenant_id", "strategic_run_snapshots", ["tenant_id"])
    op.create_index("ix_strategic_run_snapshots_preset_id", "strategic_run_snapshots", ["preset_id"])
    op.create_index("ix_strategic_run_snapshots_ingest_run_id", "strategic_run_snapshots", ["ingest_run_id"])
    op.create_index(
        "ix_strategic_run_snapshots_simulation_run_id",
        "strategic_run_snapshots",
        ["simulation_run_id"],
    )
    op.create_index("ix_strategic_run_snapshots_debate_id", "strategic_run_snapshots", ["debate_id"])
    op.create_index(
        "ix_strategic_run_snapshots_generated_report_id",
        "strategic_run_snapshots",
        ["generated_report_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_strategic_run_snapshots_generated_report_id", table_name="strategic_run_snapshots")
    op.drop_index("ix_strategic_run_snapshots_debate_id", table_name="strategic_run_snapshots")
    op.drop_index("ix_strategic_run_snapshots_simulation_run_id", table_name="strategic_run_snapshots")
    op.drop_index("ix_strategic_run_snapshots_ingest_run_id", table_name="strategic_run_snapshots")
    op.drop_index("ix_strategic_run_snapshots_preset_id", table_name="strategic_run_snapshots")
    op.drop_index("ix_strategic_run_snapshots_tenant_id", table_name="strategic_run_snapshots")
    op.drop_index("ix_strategic_run_snapshots_session_id", table_name="strategic_run_snapshots")
    op.drop_table("strategic_run_snapshots")

    op.drop_index("ix_strategic_briefs_preset_id", table_name="strategic_briefs")
    op.drop_index("ix_strategic_briefs_tenant_id", table_name="strategic_briefs")
    op.drop_index("ix_strategic_briefs_session_id", table_name="strategic_briefs")
    op.drop_table("strategic_briefs")

    op.drop_index("ix_strategic_sessions_latest_run_at", table_name="strategic_sessions")
    op.drop_index("ix_strategic_sessions_latest_briefed_at", table_name="strategic_sessions")
    op.drop_index("ix_strategic_sessions_preset_id", table_name="strategic_sessions")
    op.drop_index("ix_strategic_sessions_tenant_id", table_name="strategic_sessions")
    op.drop_index("ix_strategic_sessions_subject_id", table_name="strategic_sessions")
    op.drop_table("strategic_sessions")
