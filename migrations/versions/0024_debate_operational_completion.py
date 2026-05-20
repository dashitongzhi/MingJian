"""Complete debate operational schema.

Revision ID: 0024_debate_operational_completion
Revises: 0023_debate_enhanced_models
Create Date: 2026-05-20
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0024_debate_operational_completion"
down_revision = "0023_debate_enhanced_models"
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

    if not inspector.has_table("debate_interrupts"):
        op.create_table(
            "debate_interrupts",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column(
                "debate_session_id",
                sa.String(length=36),
                sa.ForeignKey("debate_sessions.id"),
                nullable=False,
            ),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column(
                "interrupt_type",
                sa.String(length=32),
                nullable=False,
                server_default="general",
            ),
            sa.Column("injected_at_round", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="PENDING"),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.CheckConstraint(
                "interrupt_type IN ('supplementary_info', 'direction_correction', 'new_evidence', 'general')",
                name="ck_debate_interrupts_type",
            ),
            sa.CheckConstraint(
                "status IN ('PENDING', 'INJECTED', 'IGNORED')",
                name="ck_debate_interrupts_status",
            ),
        )

    interrupt_indexes = _index_names("debate_interrupts")
    if "ix_debate_interrupts_debate_session_id" not in interrupt_indexes:
        op.create_index(
            "ix_debate_interrupts_debate_session_id",
            "debate_interrupts",
            ["debate_session_id"],
        )
    if "ix_debate_interrupts_status" not in interrupt_indexes:
        op.create_index("ix_debate_interrupts_status", "debate_interrupts", ["status"])
    if "ix_debate_interrupts_injected_at_round" not in interrupt_indexes:
        op.create_index(
            "ix_debate_interrupts_injected_at_round",
            "debate_interrupts",
            ["injected_at_round"],
        )

    verdict_columns = _column_names("debate_verdicts")
    missing_verdict_columns: list[sa.Column] = []
    if "recommendations" not in verdict_columns:
        missing_verdict_columns.append(sa.Column("recommendations", sa.JSON(), nullable=True))
    if "risk_factors" not in verdict_columns:
        missing_verdict_columns.append(sa.Column("risk_factors", sa.JSON(), nullable=True))
    if "alternative_scenarios" not in verdict_columns:
        missing_verdict_columns.append(
            sa.Column("alternative_scenarios", sa.JSON(), nullable=True)
        )
    if "conclusion_summary" not in verdict_columns:
        missing_verdict_columns.append(sa.Column("conclusion_summary", sa.Text(), nullable=True))

    if missing_verdict_columns:
        with op.batch_alter_table("debate_verdicts") as batch_op:
            for column in missing_verdict_columns:
                batch_op.add_column(column)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    verdict_columns = _column_names("debate_verdicts")
    drop_columns = [
        column
        for column in (
            "conclusion_summary",
            "alternative_scenarios",
            "risk_factors",
            "recommendations",
        )
        if column in verdict_columns
    ]
    if drop_columns:
        with op.batch_alter_table("debate_verdicts") as batch_op:
            for column in drop_columns:
                batch_op.drop_column(column)

    if inspector.has_table("debate_interrupts"):
        interrupt_indexes = _index_names("debate_interrupts")
        for index_name in (
            "ix_debate_interrupts_injected_at_round",
            "ix_debate_interrupts_status",
            "ix_debate_interrupts_debate_session_id",
        ):
            if index_name in interrupt_indexes:
                op.drop_index(index_name, table_name="debate_interrupts")
        op.drop_table("debate_interrupts")
