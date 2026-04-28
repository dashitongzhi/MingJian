"""Phase 6 runtime hardening for worker leases, tenant isolation, and diagnostics.

Revision ID: 0006_phase6_runtime_hardening
Revises: 0005_phase4_workbench_debates
Create Date: 2026-03-28
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0006_phase6_runtime_hardening"
down_revision = "0005_phase4_workbench_debates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    _ensure_column(inspector, "ingest_runs", sa.Column("tenant_id", sa.String(length=120), nullable=True))
    _ensure_column(inspector, "ingest_runs", sa.Column("preset_id", sa.String(length=120), nullable=True))
    _ensure_column(inspector, "ingest_runs", sa.Column("lease_owner", sa.String(length=120), nullable=True))
    _ensure_column(
        inspector,
        "ingest_runs",
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    _ensure_column(
        inspector,
        "ingest_runs",
        sa.Column("processing_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    _ensure_column(inspector, "ingest_runs", sa.Column("last_error", sa.Text(), nullable=True))

    _ensure_column(inspector, "raw_source_items", sa.Column("tenant_id", sa.String(length=120), nullable=True))
    _ensure_column(inspector, "raw_source_items", sa.Column("preset_id", sa.String(length=120), nullable=True))
    _ensure_column(
        inspector,
        "raw_source_items",
        sa.Column("knowledge_status", sa.String(length=24), nullable=False, server_default="PENDING"),
    )
    _ensure_column(inspector, "raw_source_items", sa.Column("lease_owner", sa.String(length=120), nullable=True))
    _ensure_column(
        inspector,
        "raw_source_items",
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    _ensure_column(
        inspector,
        "raw_source_items",
        sa.Column("processing_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    _ensure_column(inspector, "raw_source_items", sa.Column("last_error", sa.Text(), nullable=True))
    _ensure_column(
        inspector,
        "raw_source_items",
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )

    _ensure_column(inspector, "evidence_items", sa.Column("tenant_id", sa.String(length=120), nullable=True))
    _ensure_column(inspector, "evidence_items", sa.Column("preset_id", sa.String(length=120), nullable=True))

    _ensure_column(inspector, "claims", sa.Column("tenant_id", sa.String(length=120), nullable=True))
    _ensure_column(inspector, "claims", sa.Column("preset_id", sa.String(length=120), nullable=True))
    _ensure_column(
        inspector,
        "claims",
        sa.Column("kind", sa.String(length=32), nullable=False, server_default="unclassified"),
    )

    _ensure_column(inspector, "review_items", sa.Column("tenant_id", sa.String(length=120), nullable=True))
    _ensure_column(inspector, "review_items", sa.Column("preset_id", sa.String(length=120), nullable=True))
    _ensure_column(inspector, "review_items", sa.Column("lease_owner", sa.String(length=120), nullable=True))
    _ensure_column(
        inspector,
        "review_items",
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    _ensure_column(
        inspector,
        "review_items",
        sa.Column("processing_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    _ensure_column(inspector, "review_items", sa.Column("last_error", sa.Text(), nullable=True))

    _ensure_column(inspector, "signals", sa.Column("tenant_id", sa.String(length=120), nullable=True))
    _ensure_column(inspector, "signals", sa.Column("preset_id", sa.String(length=120), nullable=True))
    _ensure_column(inspector, "events", sa.Column("tenant_id", sa.String(length=120), nullable=True))
    _ensure_column(inspector, "events", sa.Column("preset_id", sa.String(length=120), nullable=True))
    _ensure_column(inspector, "trends", sa.Column("tenant_id", sa.String(length=120), nullable=True))
    _ensure_column(inspector, "trends", sa.Column("preset_id", sa.String(length=120), nullable=True))

    _ensure_column(inspector, "simulation_runs", sa.Column("tenant_id", sa.String(length=120), nullable=True))
    _ensure_column(inspector, "simulation_runs", sa.Column("preset_id", sa.String(length=120), nullable=True))
    _ensure_column(inspector, "simulation_runs", sa.Column("lease_owner", sa.String(length=120), nullable=True))
    _ensure_column(
        inspector,
        "simulation_runs",
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    _ensure_column(
        inspector,
        "simulation_runs",
        sa.Column("processing_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    _ensure_column(inspector, "simulation_runs", sa.Column("last_error", sa.Text(), nullable=True))

    _ensure_column(inspector, "generated_reports", sa.Column("tenant_id", sa.String(length=120), nullable=True))
    _ensure_column(inspector, "generated_reports", sa.Column("preset_id", sa.String(length=120), nullable=True))

    _ensure_column(inspector, "debate_sessions", sa.Column("tenant_id", sa.String(length=120), nullable=True))
    _ensure_column(inspector, "debate_sessions", sa.Column("preset_id", sa.String(length=120), nullable=True))

    _ensure_index(inspector, "ingest_runs", "ix_ingest_runs_tenant_id", ["tenant_id"])
    _ensure_index(inspector, "ingest_runs", "ix_ingest_runs_preset_id", ["preset_id"])
    _ensure_index(inspector, "ingest_runs", "ix_ingest_runs_lease_owner", ["lease_owner"])
    _ensure_index(inspector, "ingest_runs", "ix_ingest_runs_lease_expires_at", ["lease_expires_at"])

    _ensure_index(inspector, "raw_source_items", "ix_raw_source_items_tenant_id", ["tenant_id"])
    _ensure_index(inspector, "raw_source_items", "ix_raw_source_items_preset_id", ["preset_id"])
    _ensure_index(inspector, "raw_source_items", "ix_raw_source_items_knowledge_status", ["knowledge_status"])
    _ensure_index(inspector, "raw_source_items", "ix_raw_source_items_lease_owner", ["lease_owner"])
    _ensure_index(
        inspector,
        "raw_source_items",
        "ix_raw_source_items_lease_expires_at",
        ["lease_expires_at"],
    )

    _ensure_index(inspector, "evidence_items", "ix_evidence_items_tenant_id", ["tenant_id"])
    _ensure_index(inspector, "evidence_items", "ix_evidence_items_preset_id", ["preset_id"])

    _ensure_index(inspector, "claims", "ix_claims_tenant_id", ["tenant_id"])
    _ensure_index(inspector, "claims", "ix_claims_preset_id", ["preset_id"])
    _ensure_index(inspector, "claims", "ix_claims_kind", ["kind"])

    _ensure_index(inspector, "review_items", "ix_review_items_tenant_id", ["tenant_id"])
    _ensure_index(inspector, "review_items", "ix_review_items_preset_id", ["preset_id"])
    _ensure_index(inspector, "review_items", "ix_review_items_lease_owner", ["lease_owner"])
    _ensure_index(inspector, "review_items", "ix_review_items_lease_expires_at", ["lease_expires_at"])

    _ensure_index(inspector, "signals", "ix_signals_tenant_id", ["tenant_id"])
    _ensure_index(inspector, "signals", "ix_signals_preset_id", ["preset_id"])
    _ensure_index(inspector, "events", "ix_events_tenant_id", ["tenant_id"])
    _ensure_index(inspector, "events", "ix_events_preset_id", ["preset_id"])
    _ensure_index(inspector, "trends", "ix_trends_tenant_id", ["tenant_id"])
    _ensure_index(inspector, "trends", "ix_trends_preset_id", ["preset_id"])

    _ensure_index(inspector, "simulation_runs", "ix_simulation_runs_tenant_id", ["tenant_id"])
    _ensure_index(inspector, "simulation_runs", "ix_simulation_runs_preset_id", ["preset_id"])
    _ensure_index(inspector, "simulation_runs", "ix_simulation_runs_lease_owner", ["lease_owner"])
    _ensure_index(
        inspector,
        "simulation_runs",
        "ix_simulation_runs_lease_expires_at",
        ["lease_expires_at"],
    )

    _ensure_index(inspector, "generated_reports", "ix_generated_reports_tenant_id", ["tenant_id"])
    _ensure_index(inspector, "generated_reports", "ix_generated_reports_preset_id", ["preset_id"])

    _ensure_index(inspector, "debate_sessions", "ix_debate_sessions_tenant_id", ["tenant_id"])
    _ensure_index(inspector, "debate_sessions", "ix_debate_sessions_preset_id", ["preset_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for table_name, index_name in [
        ("debate_sessions", "ix_debate_sessions_preset_id"),
        ("debate_sessions", "ix_debate_sessions_tenant_id"),
        ("generated_reports", "ix_generated_reports_preset_id"),
        ("generated_reports", "ix_generated_reports_tenant_id"),
        ("simulation_runs", "ix_simulation_runs_lease_expires_at"),
        ("simulation_runs", "ix_simulation_runs_lease_owner"),
        ("simulation_runs", "ix_simulation_runs_preset_id"),
        ("simulation_runs", "ix_simulation_runs_tenant_id"),
        ("trends", "ix_trends_preset_id"),
        ("trends", "ix_trends_tenant_id"),
        ("events", "ix_events_preset_id"),
        ("events", "ix_events_tenant_id"),
        ("signals", "ix_signals_preset_id"),
        ("signals", "ix_signals_tenant_id"),
        ("review_items", "ix_review_items_lease_expires_at"),
        ("review_items", "ix_review_items_lease_owner"),
        ("review_items", "ix_review_items_preset_id"),
        ("review_items", "ix_review_items_tenant_id"),
        ("claims", "ix_claims_kind"),
        ("claims", "ix_claims_preset_id"),
        ("claims", "ix_claims_tenant_id"),
        ("evidence_items", "ix_evidence_items_preset_id"),
        ("evidence_items", "ix_evidence_items_tenant_id"),
        ("raw_source_items", "ix_raw_source_items_lease_expires_at"),
        ("raw_source_items", "ix_raw_source_items_lease_owner"),
        ("raw_source_items", "ix_raw_source_items_knowledge_status"),
        ("raw_source_items", "ix_raw_source_items_preset_id"),
        ("raw_source_items", "ix_raw_source_items_tenant_id"),
        ("ingest_runs", "ix_ingest_runs_lease_expires_at"),
        ("ingest_runs", "ix_ingest_runs_lease_owner"),
        ("ingest_runs", "ix_ingest_runs_preset_id"),
        ("ingest_runs", "ix_ingest_runs_tenant_id"),
    ]:
        _drop_index_if_exists(inspector, table_name, index_name)

    for table_name, column_name in [
        ("debate_sessions", "preset_id"),
        ("debate_sessions", "tenant_id"),
        ("generated_reports", "preset_id"),
        ("generated_reports", "tenant_id"),
        ("simulation_runs", "last_error"),
        ("simulation_runs", "processing_attempts"),
        ("simulation_runs", "lease_expires_at"),
        ("simulation_runs", "lease_owner"),
        ("simulation_runs", "preset_id"),
        ("simulation_runs", "tenant_id"),
        ("trends", "preset_id"),
        ("trends", "tenant_id"),
        ("events", "preset_id"),
        ("events", "tenant_id"),
        ("signals", "preset_id"),
        ("signals", "tenant_id"),
        ("review_items", "last_error"),
        ("review_items", "processing_attempts"),
        ("review_items", "lease_expires_at"),
        ("review_items", "lease_owner"),
        ("review_items", "preset_id"),
        ("review_items", "tenant_id"),
        ("claims", "kind"),
        ("claims", "preset_id"),
        ("claims", "tenant_id"),
        ("evidence_items", "preset_id"),
        ("evidence_items", "tenant_id"),
        ("raw_source_items", "processed_at"),
        ("raw_source_items", "last_error"),
        ("raw_source_items", "processing_attempts"),
        ("raw_source_items", "lease_expires_at"),
        ("raw_source_items", "lease_owner"),
        ("raw_source_items", "knowledge_status"),
        ("raw_source_items", "preset_id"),
        ("raw_source_items", "tenant_id"),
        ("ingest_runs", "last_error"),
        ("ingest_runs", "processing_attempts"),
        ("ingest_runs", "lease_expires_at"),
        ("ingest_runs", "lease_owner"),
        ("ingest_runs", "preset_id"),
        ("ingest_runs", "tenant_id"),
    ]:
        _drop_column_if_exists(inspector, table_name, column_name)


def _ensure_column(inspector: sa.Inspector, table_name: str, column: sa.Column) -> None:
    if not inspector.has_table(table_name):
        return
    existing = {item["name"] for item in inspector.get_columns(table_name)}
    if column.name in existing:
        return
    with op.batch_alter_table(table_name) as batch_op:
        batch_op.add_column(column)


def _drop_column_if_exists(inspector: sa.Inspector, table_name: str, column_name: str) -> None:
    if not inspector.has_table(table_name):
        return
    existing = {item["name"] for item in inspector.get_columns(table_name)}
    if column_name not in existing:
        return
    with op.batch_alter_table(table_name) as batch_op:
        batch_op.drop_column(column_name)


def _ensure_index(
    inspector: sa.Inspector,
    table_name: str,
    index_name: str,
    columns: list[str],
) -> None:
    if not inspector.has_table(table_name):
        return
    existing = {item["name"] for item in inspector.get_indexes(table_name)}
    if index_name in existing:
        return
    op.create_index(index_name, table_name, columns)


def _drop_index_if_exists(inspector: sa.Inspector, table_name: str, index_name: str) -> None:
    if not inspector.has_table(table_name):
        return
    existing = {item["name"] for item in inspector.get_indexes(table_name)}
    if index_name not in existing:
        return
    op.drop_index(index_name, table_name=table_name)
