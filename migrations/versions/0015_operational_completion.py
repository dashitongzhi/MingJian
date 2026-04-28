"""Add source snapshots, operations records, replay packages, and Jarvis runs.

Revision ID: 0015_operational_completion
Revises: 0014_knowledge_graph
Create Date: 2026-04-25
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0015_operational_completion"
down_revision = "0014_knowledge_graph"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "source_snapshots",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("raw_source_item_id", sa.String(length=36), sa.ForeignKey("raw_source_items.id"), nullable=False),
        sa.Column("tenant_id", sa.String(length=120), nullable=True),
        sa.Column("preset_id", sa.String(length=120), nullable=True),
        sa.Column("storage_backend", sa.String(length=32), nullable=False, server_default="filesystem"),
        sa.Column("storage_uri", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_source_snapshots_raw_source_item_id", "source_snapshots", ["raw_source_item_id"])
    op.create_index("ix_source_snapshots_tenant_id", "source_snapshots", ["tenant_id"])
    op.create_index("ix_source_snapshots_preset_id", "source_snapshots", ["preset_id"])
    op.create_index("ix_source_snapshots_content_sha256", "source_snapshots", ["content_sha256"])

    op.create_table(
        "source_health",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="OK"),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("source_type"),
    )
    op.create_index("ix_source_health_source_type", "source_health", ["source_type"])

    op.create_table(
        "analysis_cache_records",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("cache_key", sa.String(length=64), nullable=False),
        sa.Column("domain_id", sa.String(length=32), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("request_payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("response_payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("cache_key"),
    )
    op.create_index("ix_analysis_cache_records_cache_key", "analysis_cache_records", ["cache_key"])
    op.create_index("ix_analysis_cache_records_domain_id", "analysis_cache_records", ["domain_id"])
    op.create_index("ix_analysis_cache_records_expires_at", "analysis_cache_records", ["expires_at"])

    op.create_table(
        "dead_letter_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("topic", sa.String(length=128), nullable=False),
        sa.Column("group_name", sa.String(length=120), nullable=True),
        sa.Column("consumer_name", sa.String(length=120), nullable=True),
        sa.Column("message_id", sa.String(length=120), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_dead_letter_events_topic", "dead_letter_events", ["topic"])
    op.create_index("ix_dead_letter_events_group_name", "dead_letter_events", ["group_name"])
    op.create_index("ix_dead_letter_events_consumer_name", "dead_letter_events", ["consumer_name"])
    op.create_index("ix_dead_letter_events_message_id", "dead_letter_events", ["message_id"])

    op.create_table(
        "scenario_replay_packages",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("run_id", sa.String(length=36), sa.ForeignKey("simulation_runs.id"), nullable=False),
        sa.Column("tenant_id", sa.String(length=120), nullable=True),
        sa.Column("preset_id", sa.String(length=120), nullable=True),
        sa.Column("package_payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_scenario_replay_packages_run_id", "scenario_replay_packages", ["run_id"])
    op.create_index("ix_scenario_replay_packages_tenant_id", "scenario_replay_packages", ["tenant_id"])
    op.create_index("ix_scenario_replay_packages_preset_id", "scenario_replay_packages", ["preset_id"])

    op.create_table(
        "jarvis_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="COMPLETED"),
        sa.Column("profile_id", sa.String(length=120), nullable=False, server_default="plan-agent"),
        sa.Column("result_payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_jarvis_runs_run_id", "jarvis_runs", ["run_id"])
    op.create_index("ix_jarvis_runs_target_id", "jarvis_runs", ["target_id"])

    op.add_column("knowledge_graph_nodes", sa.Column("embedding", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("knowledge_graph_nodes", sa.Column("embedding_model", sa.String(length=120), nullable=True))


def downgrade() -> None:
    op.drop_column("knowledge_graph_nodes", "embedding_model")
    op.drop_column("knowledge_graph_nodes", "embedding")
    op.drop_index("ix_jarvis_runs_target_id", table_name="jarvis_runs")
    op.drop_index("ix_jarvis_runs_run_id", table_name="jarvis_runs")
    op.drop_table("jarvis_runs")
    op.drop_index("ix_scenario_replay_packages_preset_id", table_name="scenario_replay_packages")
    op.drop_index("ix_scenario_replay_packages_tenant_id", table_name="scenario_replay_packages")
    op.drop_index("ix_scenario_replay_packages_run_id", table_name="scenario_replay_packages")
    op.drop_table("scenario_replay_packages")
    op.drop_index("ix_dead_letter_events_message_id", table_name="dead_letter_events")
    op.drop_index("ix_dead_letter_events_consumer_name", table_name="dead_letter_events")
    op.drop_index("ix_dead_letter_events_group_name", table_name="dead_letter_events")
    op.drop_index("ix_dead_letter_events_topic", table_name="dead_letter_events")
    op.drop_table("dead_letter_events")
    op.drop_index("ix_source_health_source_type", table_name="source_health")
    op.drop_table("source_health")
    op.drop_index("ix_analysis_cache_records_expires_at", table_name="analysis_cache_records")
    op.drop_index("ix_analysis_cache_records_domain_id", table_name="analysis_cache_records")
    op.drop_index("ix_analysis_cache_records_cache_key", table_name="analysis_cache_records")
    op.drop_table("analysis_cache_records")
    op.drop_index("ix_source_snapshots_content_sha256", table_name="source_snapshots")
    op.drop_index("ix_source_snapshots_preset_id", table_name="source_snapshots")
    op.drop_index("ix_source_snapshots_tenant_id", table_name="source_snapshots")
    op.drop_index("ix_source_snapshots_raw_source_item_id", table_name="source_snapshots")
    op.drop_table("source_snapshots")
