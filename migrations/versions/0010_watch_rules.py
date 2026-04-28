"""Add watch_rules table for continuous intelligence collection.

Revision ID: 0010_watch_rules
Revises: 0009_strategic_session_auto_refresh
Create Date: 2026-04-23
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0010_watch_rules"
down_revision = "0009_strategic_session_auto_refresh"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "watch_rules",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("domain_id", sa.String(length=32), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("source_types", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("poll_interval_minutes", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("next_poll_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_owner", sa.String(length=120), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("poll_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_poll_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_poll_error", sa.Text(), nullable=True),
        sa.Column("auto_trigger_simulation", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("auto_trigger_debate", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("tick_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tenant_id", sa.String(length=120), nullable=True),
        sa.Column("preset_id", sa.String(length=120), nullable=True),
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
    op.create_index("ix_watch_rules_next_poll_at", "watch_rules", ["next_poll_at"])
    op.create_index("ix_watch_rules_lease_owner", "watch_rules", ["lease_owner"])
    op.create_index("ix_watch_rules_tenant_id", "watch_rules", ["tenant_id"])
    op.create_index("ix_watch_rules_domain_id", "watch_rules", ["domain_id"])


def downgrade() -> None:
    op.drop_index("ix_watch_rules_domain_id", table_name="watch_rules")
    op.drop_index("ix_watch_rules_tenant_id", table_name="watch_rules")
    op.drop_index("ix_watch_rules_lease_owner", table_name="watch_rules")
    op.drop_index("ix_watch_rules_next_poll_at", table_name="watch_rules")
    op.drop_table("watch_rules")
