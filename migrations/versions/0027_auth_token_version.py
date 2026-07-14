"""invalidate all user sessions with a token generation

Revision ID: 0027_auth_token_version
Revises: 0026_auth_persistence
Create Date: 2026-07-14 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0027_auth_token_version"
down_revision = "0026_auth_persistence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "auth_users",
        sa.Column("token_version", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("auth_users", "token_version")
