"""Add strategic session auto-refresh scheduling fields.

Revision ID: 0009_strategic_session_auto_refresh
Revises: 0008_strategic_sessions_history
Create Date: 2026-03-29
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from alembic import op
import sqlalchemy as sa


revision = "0009_strategic_session_auto_refresh"
down_revision = "0008_strategic_sessions_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "strategic_sessions",
        sa.Column("auto_refresh_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "strategic_sessions",
        sa.Column("refresh_timezone", sa.String(length=64), nullable=False, server_default="UTC"),
    )
    op.add_column(
        "strategic_sessions",
        sa.Column("refresh_hour_local", sa.Integer(), nullable=False, server_default="9"),
    )
    op.add_column(
        "strategic_sessions",
        sa.Column("next_refresh_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "strategic_sessions",
        sa.Column("refresh_lease_owner", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "strategic_sessions",
        sa.Column("refresh_lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "strategic_sessions",
        sa.Column("refresh_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "strategic_sessions",
        sa.Column("last_refresh_error", sa.Text(), nullable=True),
    )

    op.create_index("ix_strategic_sessions_next_refresh_at", "strategic_sessions", ["next_refresh_at"])
    op.create_index(
        "ix_strategic_sessions_refresh_lease_owner",
        "strategic_sessions",
        ["refresh_lease_owner"],
    )
    op.create_index(
        "ix_strategic_sessions_refresh_lease_expires_at",
        "strategic_sessions",
        ["refresh_lease_expires_at"],
    )

    next_refresh = (datetime.now(timezone.utc) + timedelta(days=1)).replace(
        hour=9,
        minute=0,
        second=0,
        microsecond=0,
    )
    op.execute(
        sa.text(
            """
            UPDATE strategic_sessions
            SET next_refresh_at = :next_refresh
            WHERE auto_refresh_enabled = TRUE
              AND next_refresh_at IS NULL
            """
        ).bindparams(next_refresh=next_refresh)
    )


def downgrade() -> None:
    op.drop_index("ix_strategic_sessions_refresh_lease_expires_at", table_name="strategic_sessions")
    op.drop_index("ix_strategic_sessions_refresh_lease_owner", table_name="strategic_sessions")
    op.drop_index("ix_strategic_sessions_next_refresh_at", table_name="strategic_sessions")
    op.drop_column("strategic_sessions", "last_refresh_error")
    op.drop_column("strategic_sessions", "refresh_attempts")
    op.drop_column("strategic_sessions", "refresh_lease_expires_at")
    op.drop_column("strategic_sessions", "refresh_lease_owner")
    op.drop_column("strategic_sessions", "next_refresh_at")
    op.drop_column("strategic_sessions", "refresh_hour_local")
    op.drop_column("strategic_sessions", "refresh_timezone")
    op.drop_column("strategic_sessions", "auto_refresh_enabled")
