"""Add debate votes.

Revision ID: 0022_debate_votes
Revises: 0021_pgvector_embedding
Create Date: 2026-05-04
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0022_debate_votes"
down_revision = "0021_pgvector_embedding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "debate_votes",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "debate_session_id",
            sa.String(length=36),
            sa.ForeignKey("debate_sessions.id"),
            nullable=False,
        ),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("vote", sa.String(length=16), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "role IN ('advocate', 'challenger', 'arbitrator')",
            name="ck_debate_votes_role",
        ),
        sa.CheckConstraint(
            "vote IN ('agree', 'disagree', 'neutral')",
            name="ck_debate_votes_vote",
        ),
    )
    op.create_index("ix_debate_votes_debate_session_id", "debate_votes", ["debate_session_id"])
    op.create_index("ix_debate_votes_round_number", "debate_votes", ["round_number"])
    op.create_index("ix_debate_votes_role", "debate_votes", ["role"])
    op.create_index("ix_debate_votes_vote", "debate_votes", ["vote"])


def downgrade() -> None:
    op.drop_index("ix_debate_votes_vote", table_name="debate_votes")
    op.drop_index("ix_debate_votes_role", table_name="debate_votes")
    op.drop_index("ix_debate_votes_round_number", table_name="debate_votes")
    op.drop_index("ix_debate_votes_debate_session_id", table_name="debate_votes")
    op.drop_table("debate_votes")
