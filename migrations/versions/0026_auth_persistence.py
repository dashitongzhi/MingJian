"""persist auth users and tokens

Revision ID: 0026_auth_persistence
Revises: 0025_recommendation_versions
Create Date: 2026-06-16 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0026_auth_persistence"
down_revision = "0025_recommendation_versions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auth_users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("auth_provider", sa.String(length=64), nullable=True),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_login", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("username"),
    )
    op.create_index("ix_auth_users_auth_provider", "auth_users", ["auth_provider"])
    op.create_index("ix_auth_users_email", "auth_users", ["email"], unique=True)
    op.create_index("ix_auth_users_external_id", "auth_users", ["external_id"])
    op.create_index("ix_auth_users_username", "auth_users", ["username"], unique=True)

    op.create_table(
        "auth_refresh_tokens",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["auth_users.id"]),
        sa.PrimaryKeyConstraint("token_hash"),
    )
    op.create_index("ix_auth_refresh_tokens_expires_at", "auth_refresh_tokens", ["expires_at"])
    op.create_index("ix_auth_refresh_tokens_revoked_at", "auth_refresh_tokens", ["revoked_at"])
    op.create_index("ix_auth_refresh_tokens_user_id", "auth_refresh_tokens", ["user_id"])

    op.create_table(
        "auth_revoked_tokens",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("token_hash"),
    )
    op.create_index("ix_auth_revoked_tokens_expires_at", "auth_revoked_tokens", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_auth_revoked_tokens_expires_at", table_name="auth_revoked_tokens")
    op.drop_table("auth_revoked_tokens")
    op.drop_index("ix_auth_refresh_tokens_user_id", table_name="auth_refresh_tokens")
    op.drop_index("ix_auth_refresh_tokens_revoked_at", table_name="auth_refresh_tokens")
    op.drop_index("ix_auth_refresh_tokens_expires_at", table_name="auth_refresh_tokens")
    op.drop_table("auth_refresh_tokens")
    op.drop_index("ix_auth_users_username", table_name="auth_users")
    op.drop_index("ix_auth_users_external_id", table_name="auth_users")
    op.drop_index("ix_auth_users_email", table_name="auth_users")
    op.drop_index("ix_auth_users_auth_provider", table_name="auth_users")
    op.drop_table("auth_users")
