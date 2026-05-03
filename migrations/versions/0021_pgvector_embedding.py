"""Add pgvector native vector column to knowledge_graph_nodes.

Revision ID: 0021_pgvector_embedding
Revises: 0020_prediction_calibration_contexts
Create Date: 2026-05-03
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0021_pgvector_embedding"
down_revision = "0020_prediction_calibration_contexts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Enable pgvector extension (requires superuser or CREATE privilege)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # 2. Add the native vector column (default 64 dimensions)
    op.add_column(
        "knowledge_graph_nodes",
        sa.Column("embedding_vector", sa.Text(), nullable=True),
    )
    # Use raw SQL to set the proper vector(64) type — SQLAlchemy doesn't know
    # about pgvector types natively, so we cast via DDL.
    op.execute(
        "ALTER TABLE knowledge_graph_nodes "
        "ALTER COLUMN embedding_vector TYPE vector(64) "
        "USING embedding_vector::vector(64)"
    )

    # 3. Backfill: convert existing JSON embeddings to native vector type
    op.execute(
        """
        UPDATE knowledge_graph_nodes
        SET embedding_vector = (
            '[' || array_to_string(
                ARRAY(SELECT jsonb_array_elements_text(embedding::jsonb)), ','
            ) || ']'
        )::vector(64)
        WHERE embedding IS NOT NULL
          AND embedding != '[]'::jsonb
          AND embedding_vector IS NULL
        """
    )

    # 4. Create an HNSW index for fast approximate nearest-neighbor search
    #    Requires pgvector >= 0.5.0 for HNSW; falls back to IVFFlat comment if needed.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_knowledge_graph_nodes_embedding_vector "
        "ON knowledge_graph_nodes USING hnsw (embedding_vector vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_knowledge_graph_nodes_embedding_vector")
    op.drop_column("knowledge_graph_nodes", "embedding_vector")
    # Note: we intentionally do NOT drop the vector extension in downgrade
    # as other tables/future migrations may depend on it.
