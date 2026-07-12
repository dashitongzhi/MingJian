"""Add Community recommendation versions.

Revision ID: 0025_recommendation_versions
Revises: 0024_debate_operational_completion
Create Date: 2026-05-21
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0025_recommendation_versions"
down_revision = "0024_debate_operational_completion"
branch_labels = None
depends_on = None


def _column_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(table_name):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def _index_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(table_name):
        return set()
    return {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    watch_columns = _column_names("watch_rules")
    if "session_id" not in watch_columns:
        op.add_column(
            "watch_rules",
            sa.Column("session_id", sa.String(length=36), nullable=True),
        )
    watch_indexes = _index_names("watch_rules")
    if "ix_watch_rules_session_id" not in watch_indexes:
        op.create_index("ix_watch_rules_session_id", "watch_rules", ["session_id"])

    source_columns = _column_names("source_cursor_states")
    source_indexes = _index_names("source_cursor_states")
    if "health_status" not in source_columns:
        op.add_column(
            "source_cursor_states",
            sa.Column(
                "health_status",
                sa.String(length=24),
                nullable=False,
                server_default="pending",
            ),
        )
    if "last_checked_at" not in source_columns:
        op.add_column(
            "source_cursor_states",
            sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        )
    if "last_change_at" not in source_columns:
        op.add_column(
            "source_cursor_states",
            sa.Column("last_change_at", sa.DateTime(timezone=True), nullable=True),
        )
    if "ix_source_cursor_states_last_checked_at" not in source_indexes:
        op.create_index(
            "ix_source_cursor_states_last_checked_at",
            "source_cursor_states",
            ["last_checked_at"],
        )
    if "ix_source_cursor_states_last_change_at" not in source_indexes:
        op.create_index(
            "ix_source_cursor_states_last_change_at",
            "source_cursor_states",
            ["last_change_at"],
        )

    if inspector.has_table("recommendation_versions"):
        return

    op.create_table(
        "recommendation_versions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(length=36),
            sa.ForeignKey("strategic_sessions.id"),
            nullable=False,
        ),
        sa.Column(
            "watch_rule_id",
            sa.String(length=36),
            sa.ForeignKey("watch_rules.id"),
            nullable=True,
        ),
        sa.Column("tenant_id", sa.String(length=120), nullable=True),
        sa.Column("preset_id", sa.String(length=120), nullable=True),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("trigger_type", sa.String(length=64), nullable=False),
        sa.Column(
            "trigger_source_change_id",
            sa.String(length=36),
            sa.ForeignKey("source_change_records.id"),
            nullable=True,
        ),
        sa.Column("source_change_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("significance", sa.String(length=16), nullable=False, server_default="none"),
        sa.Column("change_summary", sa.Text(), nullable=True),
        sa.Column("recommendation_summary", sa.Text(), nullable=False),
        sa.Column("result_payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("source_snapshot", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("ingest_run_id", sa.String(length=36), nullable=True),
        sa.Column("simulation_run_id", sa.String(length=36), nullable=True),
        sa.Column("debate_id", sa.String(length=36), nullable=True),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_recommendation_versions_session_id", "recommendation_versions", ["session_id"])
    op.create_index(
        "ix_recommendation_versions_watch_rule_id",
        "recommendation_versions",
        ["watch_rule_id"],
    )
    op.create_index("ix_recommendation_versions_tenant_id", "recommendation_versions", ["tenant_id"])
    op.create_index("ix_recommendation_versions_preset_id", "recommendation_versions", ["preset_id"])
    op.create_index(
        "ix_recommendation_versions_trigger_type",
        "recommendation_versions",
        ["trigger_type"],
    )
    op.create_index(
        "ix_recommendation_versions_trigger_source_change_id",
        "recommendation_versions",
        ["trigger_source_change_id"],
    )
    op.create_index(
        "ix_recommendation_versions_ingest_run_id",
        "recommendation_versions",
        ["ingest_run_id"],
    )
    op.create_index(
        "ix_recommendation_versions_simulation_run_id",
        "recommendation_versions",
        ["simulation_run_id"],
    )
    op.create_index(
        "ix_recommendation_versions_debate_id",
        "recommendation_versions",
        ["debate_id"],
    )
    op.create_index(
        "ix_recommendation_versions_generated_at",
        "recommendation_versions",
        ["generated_at"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("recommendation_versions"):
        indexes = _index_names("recommendation_versions")
        for index_name in (
            "ix_recommendation_versions_generated_at",
            "ix_recommendation_versions_debate_id",
            "ix_recommendation_versions_simulation_run_id",
            "ix_recommendation_versions_ingest_run_id",
            "ix_recommendation_versions_trigger_source_change_id",
            "ix_recommendation_versions_trigger_type",
            "ix_recommendation_versions_preset_id",
            "ix_recommendation_versions_tenant_id",
            "ix_recommendation_versions_watch_rule_id",
            "ix_recommendation_versions_session_id",
        ):
            if index_name in indexes:
                op.drop_index(index_name, table_name="recommendation_versions")
        op.drop_table("recommendation_versions")

    source_columns = _column_names("source_cursor_states")
    source_indexes = _index_names("source_cursor_states")
    if "ix_source_cursor_states_last_change_at" in source_indexes:
        op.drop_index("ix_source_cursor_states_last_change_at", table_name="source_cursor_states")
    if "ix_source_cursor_states_last_checked_at" in source_indexes:
        op.drop_index("ix_source_cursor_states_last_checked_at", table_name="source_cursor_states")
    with op.batch_alter_table("source_cursor_states") as batch_op:
        for column_name in ("last_change_at", "last_checked_at", "health_status"):
            if column_name in source_columns:
                batch_op.drop_column(column_name)

    watch_columns = _column_names("watch_rules")
    watch_indexes = _index_names("watch_rules")
    if "ix_watch_rules_session_id" in watch_indexes:
        op.drop_index("ix_watch_rules_session_id", table_name="watch_rules")
    if "session_id" in watch_columns:
        with op.batch_alter_table("watch_rules") as batch_op:
            batch_op.drop_column("session_id")
