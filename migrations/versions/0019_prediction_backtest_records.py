"""Add prediction backtest records.

Revision ID: 0019_prediction_backtest_records
Revises: 0018_incremental_source_changes
Create Date: 2026-05-02
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0019_prediction_backtest_records"
down_revision = "0018a_prediction_core_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prediction_backtest_records",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "prediction_version_id",
            sa.String(length=36),
            sa.ForeignKey("prediction_versions.id"),
            nullable=False,
        ),
        sa.Column(
            "series_id",
            sa.String(length=36),
            sa.ForeignKey("prediction_series.id"),
            nullable=False,
        ),
        sa.Column("run_id", sa.String(length=36), sa.ForeignKey("simulation_runs.id"), nullable=True),
        sa.Column("domain_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=120), nullable=True),
        sa.Column("preset_id", sa.String(length=120), nullable=True),
        sa.Column("verification_status", sa.String(length=32), nullable=False),
        sa.Column("actual_outcome", sa.Text(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column(
            "verified_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
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
        sa.UniqueConstraint("prediction_version_id"),
    )
    op.create_index(
        "ix_prediction_backtest_records_prediction_version_id",
        "prediction_backtest_records",
        ["prediction_version_id"],
    )
    op.create_index(
        "ix_prediction_backtest_records_series_id",
        "prediction_backtest_records",
        ["series_id"],
    )
    op.create_index("ix_prediction_backtest_records_run_id", "prediction_backtest_records", ["run_id"])
    op.create_index(
        "ix_prediction_backtest_records_domain_id",
        "prediction_backtest_records",
        ["domain_id"],
    )
    op.create_index(
        "ix_prediction_backtest_records_tenant_id",
        "prediction_backtest_records",
        ["tenant_id"],
    )
    op.create_index(
        "ix_prediction_backtest_records_preset_id",
        "prediction_backtest_records",
        ["preset_id"],
    )
    op.create_index(
        "ix_prediction_backtest_records_verification_status",
        "prediction_backtest_records",
        ["verification_status"],
    )


def downgrade() -> None:
    op.drop_index("ix_prediction_backtest_records_verification_status", table_name="prediction_backtest_records")
    op.drop_index("ix_prediction_backtest_records_preset_id", table_name="prediction_backtest_records")
    op.drop_index("ix_prediction_backtest_records_tenant_id", table_name="prediction_backtest_records")
    op.drop_index("ix_prediction_backtest_records_domain_id", table_name="prediction_backtest_records")
    op.drop_index("ix_prediction_backtest_records_run_id", table_name="prediction_backtest_records")
    op.drop_index("ix_prediction_backtest_records_series_id", table_name="prediction_backtest_records")
    op.drop_index(
        "ix_prediction_backtest_records_prediction_version_id",
        table_name="prediction_backtest_records",
    )
    op.drop_table("prediction_backtest_records")
