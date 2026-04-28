"""Add persisted knowledge graph tables.

Revision ID: 0014_knowledge_graph
Revises: 0013_calibration_records
Create Date: 2026-04-25
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0014_knowledge_graph"
down_revision = "0013_calibration_records"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_graph_nodes",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("node_key", sa.String(length=160), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("node_type", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=120), nullable=True),
        sa.Column("preset_id", sa.String(length=120), nullable=True),
        sa.Column("source_table", sa.String(length=64), nullable=False),
        sa.Column("source_id", sa.String(length=120), nullable=False),
        sa.Column("node_metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("node_key"),
    )
    op.create_index("ix_knowledge_graph_nodes_node_key", "knowledge_graph_nodes", ["node_key"])
    op.create_index("ix_knowledge_graph_nodes_node_type", "knowledge_graph_nodes", ["node_type"])
    op.create_index("ix_knowledge_graph_nodes_tenant_id", "knowledge_graph_nodes", ["tenant_id"])
    op.create_index("ix_knowledge_graph_nodes_preset_id", "knowledge_graph_nodes", ["preset_id"])
    op.create_index("ix_knowledge_graph_nodes_source_id", "knowledge_graph_nodes", ["source_id"])

    op.create_table(
        "knowledge_graph_edges",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("source_node_key", sa.String(length=160), nullable=False),
        sa.Column("target_node_key", sa.String(length=160), nullable=False),
        sa.Column("relation_type", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=120), nullable=True),
        sa.Column("preset_id", sa.String(length=120), nullable=True),
        sa.Column("edge_metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("source_node_key", "target_node_key", "relation_type"),
    )
    op.create_index("ix_knowledge_graph_edges_source_node_key", "knowledge_graph_edges", ["source_node_key"])
    op.create_index("ix_knowledge_graph_edges_target_node_key", "knowledge_graph_edges", ["target_node_key"])
    op.create_index("ix_knowledge_graph_edges_relation_type", "knowledge_graph_edges", ["relation_type"])
    op.create_index("ix_knowledge_graph_edges_tenant_id", "knowledge_graph_edges", ["tenant_id"])
    op.create_index("ix_knowledge_graph_edges_preset_id", "knowledge_graph_edges", ["preset_id"])


def downgrade() -> None:
    op.drop_index("ix_knowledge_graph_edges_preset_id", table_name="knowledge_graph_edges")
    op.drop_index("ix_knowledge_graph_edges_tenant_id", table_name="knowledge_graph_edges")
    op.drop_index("ix_knowledge_graph_edges_relation_type", table_name="knowledge_graph_edges")
    op.drop_index("ix_knowledge_graph_edges_target_node_key", table_name="knowledge_graph_edges")
    op.drop_index("ix_knowledge_graph_edges_source_node_key", table_name="knowledge_graph_edges")
    op.drop_table("knowledge_graph_edges")
    op.drop_index("ix_knowledge_graph_nodes_source_id", table_name="knowledge_graph_nodes")
    op.drop_index("ix_knowledge_graph_nodes_preset_id", table_name="knowledge_graph_nodes")
    op.drop_index("ix_knowledge_graph_nodes_tenant_id", table_name="knowledge_graph_nodes")
    op.drop_index("ix_knowledge_graph_nodes_node_type", table_name="knowledge_graph_nodes")
    op.drop_index("ix_knowledge_graph_nodes_node_key", table_name="knowledge_graph_nodes")
    op.drop_table("knowledge_graph_nodes")
