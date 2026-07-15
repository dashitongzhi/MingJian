"""Add debate enhanced models.

Revision ID: 0023_debate_enhanced_models
Revises: 0022_debate_votes
Create Date: 2026-05-10
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0023_debate_enhanced_models"
down_revision = "0022_debate_votes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "debate_reliability_scores",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "debate_id",
            sa.String(length=36),
            sa.ForeignKey("debate_sessions.id"),
            nullable=False,
        ),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("argument_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("argument_summary", sa.Text(), nullable=False),
        sa.Column("reliability_score", sa.Integer(), nullable=False),
        sa.Column("bias_flags", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("blind_spots", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column(
            "evidence_strength", sa.String(length=32), nullable=False, server_default="moderate"
        ),
        sa.Column("auditor_role", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_debate_reliability_scores_debate_id", "debate_reliability_scores", ["debate_id"]
    )

    op.create_table(
        "debate_structured_dissents",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "debate_id",
            sa.String(length=36),
            sa.ForeignKey("debate_sessions.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("dissenter_role", sa.String(length=32), nullable=False),
        sa.Column("claims", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("evidence_gaps", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("confidence_trajectory", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("recommended_monitoring", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("overall_dissent_strength", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_debate_structured_dissents_debate_id",
        "debate_structured_dissents",
        ["debate_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_debate_structured_dissents_debate_id", table_name="debate_structured_dissents"
    )
    op.drop_table("debate_structured_dissents")
    op.drop_index("ix_debate_reliability_scores_debate_id", table_name="debate_reliability_scores")
    op.drop_table("debate_reliability_scores")
