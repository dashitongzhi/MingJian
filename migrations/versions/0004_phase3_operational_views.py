"""Phase 3 operational view schema.

Revision ID: 0004_phase3_operational_views
Revises: 0003_phase3_military_scenarios
Create Date: 2026-03-17
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0004_phase3_operational_views"
down_revision = "0003_phase3_military_scenarios"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "geo_assets",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("run_id", sa.String(length=36), sa.ForeignKey("simulation_runs.id"), nullable=False),
        sa.Column("force_id", sa.String(length=120), sa.ForeignKey("force_profiles.id"), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("asset_type", sa.String(length=64), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("properties", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "external_shocks",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("run_id", sa.String(length=36), sa.ForeignKey("simulation_runs.id"), nullable=False),
        sa.Column("tick", sa.Integer(), nullable=False),
        sa.Column("domain", sa.String(length=64), nullable=False),
        sa.Column("shock_type", sa.String(length=64), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("external_shocks")
    op.drop_table("geo_assets")
