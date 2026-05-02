"""Add incremental source cursor and change records.

Revision ID: 0018_incremental_source_changes
Revises: 0017_intelligence_mvp_fields
Create Date: 2026-05-02
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0018_incremental_source_changes"
down_revision = "0017_intelligence_mvp_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "watch_rules",
        sa.Column("incremental_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "watch_rules",
        sa.Column("force_full_refresh_every", sa.Integer(), nullable=False, server_default="24"),
    )
    op.add_column(
        "watch_rules",
        sa.Column("last_cursor_reset_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "watch_rules",
        sa.Column(
            "change_significance_threshold",
            sa.String(length=32),
            nullable=False,
            server_default="medium",
        ),
    )

    op.create_table(
        "source_cursor_states",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "watch_rule_id",
            sa.String(length=36),
            sa.ForeignKey("watch_rules.id"),
            nullable=True,
        ),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("source_url_or_query", sa.Text(), nullable=False),
        sa.Column("tenant_id", sa.String(length=120), nullable=True),
        sa.Column("preset_id", sa.String(length=120), nullable=True),
        sa.Column("cursor", sa.Text(), nullable=True),
        sa.Column("etag", sa.Text(), nullable=True),
        sa.Column("last_modified", sa.Text(), nullable=True),
        sa.Column("last_seen_hash", sa.String(length=64), nullable=True),
        sa.Column(
            "last_seen_raw_source_item_id",
            sa.String(length=36),
            sa.ForeignKey("raw_source_items.id"),
            nullable=True,
        ),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
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
        sa.UniqueConstraint("watch_rule_id", "source_type", "source_url_or_query"),
    )
    op.create_index(
        "ix_source_cursor_states_watch_rule_id",
        "source_cursor_states",
        ["watch_rule_id"],
    )
    op.create_index("ix_source_cursor_states_source_type", "source_cursor_states", ["source_type"])
    op.create_index("ix_source_cursor_states_tenant_id", "source_cursor_states", ["tenant_id"])
    op.create_index("ix_source_cursor_states_preset_id", "source_cursor_states", ["preset_id"])
    op.create_index(
        "ix_source_cursor_states_last_seen_hash",
        "source_cursor_states",
        ["last_seen_hash"],
    )
    op.create_index(
        "ix_source_cursor_states_last_seen_raw_source_item_id",
        "source_cursor_states",
        ["last_seen_raw_source_item_id"],
    )
    op.create_index(
        "ix_source_cursor_states_last_success_at",
        "source_cursor_states",
        ["last_success_at"],
    )
    op.create_index(
        "ix_source_cursor_states_last_failure_at",
        "source_cursor_states",
        ["last_failure_at"],
    )

    op.create_table(
        "source_change_records",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "source_state_id",
            sa.String(length=36),
            sa.ForeignKey("source_cursor_states.id"),
            nullable=False,
        ),
        sa.Column(
            "watch_rule_id",
            sa.String(length=36),
            sa.ForeignKey("watch_rules.id"),
            nullable=True,
        ),
        sa.Column(
            "old_raw_source_item_id",
            sa.String(length=36),
            sa.ForeignKey("raw_source_items.id"),
            nullable=True,
        ),
        sa.Column(
            "new_raw_source_item_id",
            sa.String(length=36),
            sa.ForeignKey("raw_source_items.id"),
            nullable=True,
        ),
        sa.Column("old_hash", sa.String(length=64), nullable=True),
        sa.Column("new_hash", sa.String(length=64), nullable=True),
        sa.Column("change_type", sa.String(length=32), nullable=False),
        sa.Column("significance", sa.String(length=32), nullable=False, server_default="none"),
        sa.Column("diff_summary", sa.Text(), nullable=True),
        sa.Column("changed_fields", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("claim_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("prediction_revision_job_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_source_change_records_source_state_id",
        "source_change_records",
        ["source_state_id"],
    )
    op.create_index(
        "ix_source_change_records_watch_rule_id",
        "source_change_records",
        ["watch_rule_id"],
    )
    op.create_index(
        "ix_source_change_records_old_raw_source_item_id",
        "source_change_records",
        ["old_raw_source_item_id"],
    )
    op.create_index(
        "ix_source_change_records_new_raw_source_item_id",
        "source_change_records",
        ["new_raw_source_item_id"],
    )
    op.create_index("ix_source_change_records_old_hash", "source_change_records", ["old_hash"])
    op.create_index("ix_source_change_records_new_hash", "source_change_records", ["new_hash"])
    op.create_index(
        "ix_source_change_records_change_type",
        "source_change_records",
        ["change_type"],
    )
    op.create_index(
        "ix_source_change_records_significance",
        "source_change_records",
        ["significance"],
    )
    op.create_index("ix_source_change_records_created_at", "source_change_records", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_source_change_records_created_at", table_name="source_change_records")
    op.drop_index("ix_source_change_records_significance", table_name="source_change_records")
    op.drop_index("ix_source_change_records_change_type", table_name="source_change_records")
    op.drop_index("ix_source_change_records_new_hash", table_name="source_change_records")
    op.drop_index("ix_source_change_records_old_hash", table_name="source_change_records")
    op.drop_index(
        "ix_source_change_records_new_raw_source_item_id",
        table_name="source_change_records",
    )
    op.drop_index(
        "ix_source_change_records_old_raw_source_item_id",
        table_name="source_change_records",
    )
    op.drop_index("ix_source_change_records_watch_rule_id", table_name="source_change_records")
    op.drop_index("ix_source_change_records_source_state_id", table_name="source_change_records")
    op.drop_table("source_change_records")

    op.drop_index("ix_source_cursor_states_last_failure_at", table_name="source_cursor_states")
    op.drop_index("ix_source_cursor_states_last_success_at", table_name="source_cursor_states")
    op.drop_index(
        "ix_source_cursor_states_last_seen_raw_source_item_id",
        table_name="source_cursor_states",
    )
    op.drop_index("ix_source_cursor_states_last_seen_hash", table_name="source_cursor_states")
    op.drop_index("ix_source_cursor_states_preset_id", table_name="source_cursor_states")
    op.drop_index("ix_source_cursor_states_tenant_id", table_name="source_cursor_states")
    op.drop_index("ix_source_cursor_states_source_type", table_name="source_cursor_states")
    op.drop_index("ix_source_cursor_states_watch_rule_id", table_name="source_cursor_states")
    op.drop_table("source_cursor_states")

    op.drop_column("watch_rules", "change_significance_threshold")
    op.drop_column("watch_rules", "last_cursor_reset_at")
    op.drop_column("watch_rules", "force_full_refresh_every")
    op.drop_column("watch_rules", "incremental_enabled")
