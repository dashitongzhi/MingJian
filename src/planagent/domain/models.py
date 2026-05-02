from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
import uuid

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from planagent.domain.enums import (
    ClaimStatus,
    ExecutionMode,
    IngestRunStatus,
    ReviewItemStatus,
    SimulationRunStatus,
)


def generate_id() -> str:
    if hasattr(uuid, "uuid7"):
        return str(uuid.uuid7())
    return str(uuid.uuid4())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class IngestRun(Base):
    __tablename__ = "ingest_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_id)
    requested_by: Mapped[str] = mapped_column(String(100), nullable=False)
    tenant_id: Mapped[str | None] = mapped_column(String(120), index=True)
    preset_id: Mapped[str | None] = mapped_column(String(120), index=True)
    execution_mode: Mapped[str] = mapped_column(
        String(16), default=ExecutionMode.INLINE.value, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(24), default=IngestRunStatus.PENDING.value, nullable=False
    )
    source_types: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    request_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    summary: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    lease_owner: Mapped[str | None] = mapped_column(String(120), index=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    processing_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    raw_items: Mapped[list["RawSourceItem"]] = relationship(back_populates="ingest_run")


class RawSourceItem(Base):
    __tablename__ = "raw_source_items"
    __table_args__ = (UniqueConstraint("dedupe_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_id)
    ingest_run_id: Mapped[str] = mapped_column(ForeignKey("ingest_runs.id"), nullable=False)
    tenant_id: Mapped[str | None] = mapped_column(String(120), index=True)
    preset_id: Mapped[str | None] = mapped_column(String(120), index=True)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    knowledge_status: Mapped[str] = mapped_column(String(24), default="PENDING", nullable=False, index=True)
    lease_owner: Mapped[str | None] = mapped_column(String(120), index=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    processing_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    ingest_run: Mapped[IngestRun] = relationship(back_populates="raw_items")
    normalized_item: Mapped["NormalizedItem"] = relationship(back_populates="raw_item", uselist=False)


class SourceSnapshot(Base):
    __tablename__ = "source_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_id)
    raw_source_item_id: Mapped[str] = mapped_column(ForeignKey("raw_source_items.id"), nullable=False, index=True)
    tenant_id: Mapped[str | None] = mapped_column(String(120), index=True)
    preset_id: Mapped[str | None] = mapped_column(String(120), index=True)
    storage_backend: Mapped[str] = mapped_column(String(32), default="filesystem", nullable=False)
    storage_uri: Mapped[str] = mapped_column(Text, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    byte_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class SourceHealth(Base):
    __tablename__ = "source_health"
    __table_args__ = (UniqueConstraint("source_type"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_id)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="OK", nullable=False)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class AnalysisCacheRecord(Base):
    __tablename__ = "analysis_cache_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_id)
    cache_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    domain_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    request_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    response_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class NormalizedItem(Base):
    __tablename__ = "normalized_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_id)
    raw_source_item_id: Mapped[str] = mapped_column(
        ForeignKey("raw_source_items.id"), nullable=False, unique=True
    )
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body_text: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    normalized_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    normalized_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    raw_item: Mapped[RawSourceItem] = relationship(back_populates="normalized_item")
    evidence_item: Mapped["EvidenceItem"] = relationship(
        back_populates="normalized_item", uselist=False
    )


class EvidenceItem(Base):
    __tablename__ = "evidence_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_id)
    normalized_item_id: Mapped[str] = mapped_column(
        ForeignKey("normalized_items.id"), nullable=False, unique=True
    )
    tenant_id: Mapped[str | None] = mapped_column(String(120), index=True)
    preset_id: Mapped[str | None] = mapped_column(String(120), index=True)
    evidence_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    body_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE", nullable=False)
    provenance: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    normalized_item: Mapped[NormalizedItem] = relationship(back_populates="evidence_item")
    claims: Mapped[list["Claim"]] = relationship(back_populates="evidence_item")


class Claim(Base):
    __tablename__ = "claims"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_id)
    evidence_item_id: Mapped[str] = mapped_column(ForeignKey("evidence_items.id"), nullable=False)
    tenant_id: Mapped[str | None] = mapped_column(String(120), index=True)
    preset_id: Mapped[str | None] = mapped_column(String(120), index=True)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    predicate: Mapped[str] = mapped_column(String(120), nullable=False)
    object_text: Mapped[str] = mapped_column(Text, nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), default="unclassified", nullable=False, index=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default=ClaimStatus.PENDING_REVIEW.value, nullable=False
    )
    requires_review: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    reasoning: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    evidence_item: Mapped[EvidenceItem] = relationship(back_populates="claims")
    review_item: Mapped["ReviewItem"] = relationship(back_populates="claim", uselist=False)
    debate_sessions: Mapped[list["DebateSessionRecord"]] = relationship(back_populates="claim")


class ReviewItem(Base):
    __tablename__ = "review_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_id)
    claim_id: Mapped[str] = mapped_column(ForeignKey("claims.id"), nullable=False, unique=True)
    tenant_id: Mapped[str | None] = mapped_column(String(120), index=True)
    preset_id: Mapped[str | None] = mapped_column(String(120), index=True)
    queue_reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default=ReviewItemStatus.PENDING.value, nullable=False
    )
    lease_owner: Mapped[str | None] = mapped_column(String(120), index=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    processing_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)
    reviewer_id: Mapped[str | None] = mapped_column(String(100))
    review_note: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    claim: Mapped[Claim] = relationship(back_populates="review_item")


class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_id)
    claim_id: Mapped[str | None] = mapped_column(ForeignKey("claims.id"))
    tenant_id: Mapped[str | None] = mapped_column(String(120), index=True)
    preset_id: Mapped[str | None] = mapped_column(String(120), index=True)
    signal_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class EventRecord(Base):
    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_id)
    claim_id: Mapped[str | None] = mapped_column(ForeignKey("claims.id"))
    tenant_id: Mapped[str | None] = mapped_column(String(120), index=True)
    preset_id: Mapped[str | None] = mapped_column(String(120), index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class Trend(Base):
    __tablename__ = "trends"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_id)
    claim_id: Mapped[str | None] = mapped_column(ForeignKey("claims.id"))
    tenant_id: Mapped[str | None] = mapped_column(String(120), index=True)
    preset_id: Mapped[str | None] = mapped_column(String(120), index=True)
    trend_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class KnowledgeGraphNode(Base):
    __tablename__ = "knowledge_graph_nodes"
    __table_args__ = (UniqueConstraint("node_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_id)
    node_key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    node_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    tenant_id: Mapped[str | None] = mapped_column(String(120), index=True)
    preset_id: Mapped[str | None] = mapped_column(String(120), index=True)
    source_table: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    embedding: Mapped[list[float]] = mapped_column(JSON, default=list, nullable=False)
    embedding_model: Mapped[str | None] = mapped_column(String(120))
    node_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class KnowledgeGraphEdge(Base):
    __tablename__ = "knowledge_graph_edges"
    __table_args__ = (UniqueConstraint("source_node_key", "target_node_key", "relation_type"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_id)
    source_node_key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    target_node_key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    relation_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    tenant_id: Mapped[str | None] = mapped_column(String(120), index=True)
    preset_id: Mapped[str | None] = mapped_column(String(120), index=True)
    edge_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class EventArchive(Base):
    __tablename__ = "event_archive"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_id)
    topic: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class DeadLetterEvent(Base):
    __tablename__ = "dead_letter_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_id)
    topic: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    group_name: Mapped[str | None] = mapped_column(String(120), index=True)
    consumer_name: Mapped[str | None] = mapped_column(String(120), index=True)
    message_id: Mapped[str | None] = mapped_column(String(120), index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    error: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class CompanyProfile(Base):
    __tablename__ = "company_profiles"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    market: Mapped[str] = mapped_column(String(120), nullable=False)
    attributes: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    simulation_runs: Mapped[list["SimulationRun"]] = relationship(back_populates="company")
    reports: Mapped[list["GeneratedReport"]] = relationship(back_populates="company")


class ForceProfile(Base):
    __tablename__ = "force_profiles"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    theater: Mapped[str] = mapped_column(String(120), nullable=False)
    attributes: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    simulation_runs: Mapped[list["SimulationRun"]] = relationship(back_populates="force")
    reports: Mapped[list["GeneratedReport"]] = relationship(back_populates="force")
    geo_assets: Mapped[list["GeoAssetRecord"]] = relationship(back_populates="force")


class SimulationRun(Base):
    __tablename__ = "simulation_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_id)
    company_id: Mapped[str | None] = mapped_column(ForeignKey("company_profiles.id"))
    force_id: Mapped[str | None] = mapped_column(ForeignKey("force_profiles.id"))
    tenant_id: Mapped[str | None] = mapped_column(String(120), index=True)
    preset_id: Mapped[str | None] = mapped_column(String(120), index=True)
    domain_id: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_template: Mapped[str] = mapped_column(String(120), nullable=False)
    military_use_mode: Mapped[str | None] = mapped_column(String(32))
    parent_run_id: Mapped[str | None] = mapped_column(ForeignKey("simulation_runs.id"))
    execution_mode: Mapped[str] = mapped_column(
        String(16), default=ExecutionMode.INLINE.value, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(24), default=SimulationRunStatus.PENDING.value, nullable=False
    )
    tick_count: Mapped[int] = mapped_column(Integer, nullable=False)
    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    configuration: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    summary: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    lease_owner: Mapped[str | None] = mapped_column(String(120), index=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    processing_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    company: Mapped[CompanyProfile | None] = relationship(back_populates="simulation_runs")
    force: Mapped[ForceProfile | None] = relationship(back_populates="simulation_runs")
    parent_run: Mapped[Optional["SimulationRun"]] = relationship(
        remote_side=lambda: [SimulationRun.id],
        back_populates="child_runs",
    )
    child_runs: Mapped[list["SimulationRun"]] = relationship(back_populates="parent_run")
    state_snapshots: Mapped[list["StateSnapshotRecord"]] = relationship(back_populates="simulation_run")
    decision_records: Mapped[list["DecisionRecordRecord"]] = relationship(back_populates="simulation_run")
    reports: Mapped[list["GeneratedReport"]] = relationship(back_populates="simulation_run")
    geo_assets: Mapped[list["GeoAssetRecord"]] = relationship(back_populates="simulation_run")
    external_shocks: Mapped[list["ExternalShockRecord"]] = relationship(back_populates="simulation_run")
    debate_sessions: Mapped[list["DebateSessionRecord"]] = relationship(back_populates="simulation_run")
    scenario_branch: Mapped[Optional["ScenarioBranchRecord"]] = relationship(
        back_populates="simulation_run",
        uselist=False,
        foreign_keys=lambda: [ScenarioBranchRecord.run_id],
    )


class StateSnapshotRecord(Base):
    __tablename__ = "state_snapshots"
    __table_args__ = (UniqueConstraint("run_id", "tick", "actor_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("simulation_runs.id"), nullable=False)
    tick: Mapped[int] = mapped_column(Integer, nullable=False)
    actor_id: Mapped[str] = mapped_column(String(120), nullable=False)
    state: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    simulation_run: Mapped[SimulationRun] = relationship(back_populates="state_snapshots")


class DecisionRecordRecord(Base):
    __tablename__ = "decision_records"
    __table_args__ = (UniqueConstraint("run_id", "tick", "sequence"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("simulation_runs.id"), nullable=False)
    tick: Mapped[int] = mapped_column(Integer, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    actor_id: Mapped[str] = mapped_column(String(120), nullable=False)
    action_id: Mapped[str] = mapped_column(String(120), nullable=False)
    why_selected: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    policy_rule_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    expected_effect: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    actual_effect: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    debate_verdict_id: Mapped[str | None] = mapped_column(ForeignKey("debate_sessions.id"))
    decision_method: Mapped[str] = mapped_column(String(32), default="rule_engine", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    simulation_run: Mapped[SimulationRun] = relationship(back_populates="decision_records")
    debate_session: Mapped[Optional["DebateSessionRecord"]] = relationship()


class GeoAssetRecord(Base):
    __tablename__ = "geo_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("simulation_runs.id"), nullable=False)
    force_id: Mapped[str | None] = mapped_column(ForeignKey("force_profiles.id"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(64), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    properties: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    simulation_run: Mapped[SimulationRun] = relationship(back_populates="geo_assets")
    force: Mapped[ForceProfile | None] = relationship(back_populates="geo_assets")


class ExternalShockRecord(Base):
    __tablename__ = "external_shocks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("simulation_runs.id"), nullable=False)
    tick: Mapped[int] = mapped_column(Integer, nullable=False)
    domain: Mapped[str] = mapped_column(String(64), nullable=False)
    shock_type: Mapped[str] = mapped_column(String(64), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    simulation_run: Mapped[SimulationRun] = relationship(back_populates="external_shocks")


class GeneratedReport(Base):
    __tablename__ = "generated_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("simulation_runs.id"), nullable=False)
    company_id: Mapped[str | None] = mapped_column(ForeignKey("company_profiles.id"))
    force_id: Mapped[str | None] = mapped_column(ForeignKey("force_profiles.id"))
    scenario_id: Mapped[str | None] = mapped_column(ForeignKey("scenario_branches.id"))
    tenant_id: Mapped[str | None] = mapped_column(String(120), index=True)
    preset_id: Mapped[str | None] = mapped_column(String(120), index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    report_format: Mapped[str] = mapped_column(String(32), nullable=False)
    sections: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    simulation_run: Mapped[SimulationRun] = relationship(back_populates="reports")
    company: Mapped[CompanyProfile | None] = relationship(back_populates="reports")
    force: Mapped[ForceProfile | None] = relationship(back_populates="reports")


class ScenarioBranchRecord(Base):
    __tablename__ = "scenario_branches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("simulation_runs.id"), nullable=False, unique=True)
    parent_run_id: Mapped[str] = mapped_column(ForeignKey("simulation_runs.id"), nullable=False)
    fork_step: Mapped[int] = mapped_column(Integer, nullable=False)
    assumptions: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    decision_deltas: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    kpi_trajectory: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    probability_band: Mapped[str] = mapped_column(String(32), nullable=False)
    notable_events: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    evidence_summary: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    simulation_run: Mapped[SimulationRun] = relationship(
        back_populates="scenario_branch",
        foreign_keys=[run_id],
    )
    parent_run: Mapped[SimulationRun] = relationship(foreign_keys=[parent_run_id])


class ScenarioReplayPackageRecord(Base):
    __tablename__ = "scenario_replay_packages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("simulation_runs.id"), nullable=False, index=True)
    tenant_id: Mapped[str | None] = mapped_column(String(120), index=True)
    preset_id: Mapped[str | None] = mapped_column(String(120), index=True)
    package_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class DebateSessionRecord(Base):
    __tablename__ = "debate_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_id)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("simulation_runs.id"))
    claim_id: Mapped[str | None] = mapped_column(ForeignKey("claims.id"))
    tenant_id: Mapped[str | None] = mapped_column(String(120), index=True)
    preset_id: Mapped[str | None] = mapped_column(String(120), index=True)
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="COMPLETED")
    target_type: Mapped[str] = mapped_column(String(64), nullable=False, default="run")
    target_id: Mapped[str | None] = mapped_column(String(120))
    context_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    simulation_run: Mapped[SimulationRun | None] = relationship(back_populates="debate_sessions")
    claim: Mapped[Claim | None] = relationship(back_populates="debate_sessions")
    rounds: Mapped[list["DebateRoundRecord"]] = relationship(back_populates="debate_session")
    verdict: Mapped[Optional["DebateVerdictRecord"]] = relationship(
        back_populates="debate_session",
        uselist=False,
    )


class DebateRoundRecord(Base):
    __tablename__ = "debate_rounds"
    __table_args__ = (UniqueConstraint("debate_id", "round_number", "role"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_id)
    debate_id: Mapped[str] = mapped_column(ForeignKey("debate_sessions.id"), nullable=False)
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    position: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    arguments: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    rebuttals: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    concessions: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    debate_session: Mapped[DebateSessionRecord] = relationship(back_populates="rounds")


class DebateVerdictRecord(Base):
    __tablename__ = "debate_verdicts"

    debate_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("debate_sessions.id"),
        primary_key=True,
    )
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(64), nullable=False)
    rounds_completed: Mapped[int] = mapped_column(Integer, nullable=False)
    verdict: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    winning_arguments: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    decisive_evidence: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    conditions: Mapped[list[str] | None] = mapped_column(JSON)
    minority_opinion: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    debate_session: Mapped[DebateSessionRecord] = relationship(back_populates="verdict")


class StrategicSession(Base):
    __tablename__ = "strategic_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_id)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    domain_id: Mapped[str] = mapped_column(String(32), nullable=False, default="auto")
    subject_id: Mapped[str | None] = mapped_column(String(120), index=True)
    subject_name: Mapped[str | None] = mapped_column(String(255))
    market: Mapped[str | None] = mapped_column(String(120))
    theater: Mapped[str | None] = mapped_column(String(120))
    actor_template: Mapped[str | None] = mapped_column(String(120))
    tick_count: Mapped[int | None] = mapped_column(Integer)
    tenant_id: Mapped[str | None] = mapped_column(String(120), index=True)
    preset_id: Mapped[str | None] = mapped_column(String(120), index=True)
    source_preferences: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    auto_refresh_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    refresh_timezone: Mapped[str] = mapped_column(String(64), default="UTC", nullable=False)
    refresh_hour_local: Mapped[int] = mapped_column(Integer, default=9, nullable=False)
    next_refresh_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    refresh_lease_owner: Mapped[str | None] = mapped_column(String(120), index=True)
    refresh_lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    refresh_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_refresh_error: Mapped[str | None] = mapped_column(Text)
    latest_brief_summary: Mapped[str | None] = mapped_column(Text)
    latest_run_summary: Mapped[str | None] = mapped_column(Text)
    latest_debate_verdict: Mapped[str | None] = mapped_column(String(32))
    latest_briefed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    latest_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    briefs: Mapped[list["StrategicBriefRecord"]] = relationship(back_populates="session")
    run_snapshots: Mapped[list["StrategicRunSnapshot"]] = relationship(back_populates="session")


class StrategicBriefRecord(Base):
    __tablename__ = "strategic_briefs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_id)
    session_id: Mapped[str] = mapped_column(ForeignKey("strategic_sessions.id"), nullable=False, index=True)
    tenant_id: Mapped[str | None] = mapped_column(String(120), index=True)
    preset_id: Mapped[str | None] = mapped_column(String(120), index=True)
    domain_id: Mapped[str] = mapped_column(String(32), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    source_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    analysis_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    session: Mapped[StrategicSession] = relationship(back_populates="briefs")


class StrategicRunSnapshot(Base):
    __tablename__ = "strategic_run_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_id)
    session_id: Mapped[str] = mapped_column(ForeignKey("strategic_sessions.id"), nullable=False, index=True)
    tenant_id: Mapped[str | None] = mapped_column(String(120), index=True)
    preset_id: Mapped[str | None] = mapped_column(String(120), index=True)
    ingest_run_id: Mapped[str | None] = mapped_column(String(36), index=True)
    simulation_run_id: Mapped[str | None] = mapped_column(String(36), index=True)
    debate_id: Mapped[str | None] = mapped_column(String(36), index=True)
    generated_report_id: Mapped[str | None] = mapped_column(String(36), index=True)
    result_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    session: Mapped[StrategicSession] = relationship(back_populates="run_snapshots")


class WatchRule(Base):
    __tablename__ = "watch_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_id)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    domain_id: Mapped[str] = mapped_column(String(32), nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    source_types: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    keywords: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    exclude_keywords: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    entity_tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    trigger_threshold: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    min_new_evidence_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    importance_threshold: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    poll_interval_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    next_poll_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    lease_owner: Mapped[str | None] = mapped_column(String(120), index=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    poll_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_poll_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_poll_error: Mapped[str | None] = mapped_column(Text)
    auto_trigger_simulation: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    auto_trigger_debate: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    tick_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tenant_id: Mapped[str | None] = mapped_column(String(120), index=True)
    preset_id: Mapped[str | None] = mapped_column(String(120), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
    incremental_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    force_full_refresh_every: Mapped[int] = mapped_column(Integer, default=24, nullable=False)
    last_cursor_reset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    change_significance_threshold: Mapped[str] = mapped_column(
        String(16), default="medium", nullable=False
    )


class CalibrationRecord(Base):
    __tablename__ = "calibration_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_id)
    domain_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    tenant_id: Mapped[str | None] = mapped_column(String(120), index=True)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    total_hypotheses: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    confirmed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    refuted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    partial: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pending: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    calibration_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    rule_accuracy: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class JarvisRunRecord(Base):
    __tablename__ = "jarvis_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_id)
    run_id: Mapped[str | None] = mapped_column(String(36), index=True)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[str | None] = mapped_column(String(120), index=True)
    status: Mapped[str] = mapped_column(String(32), default="COMPLETED", nullable=False)
    profile_id: Mapped[str] = mapped_column(String(120), default="plan-agent", nullable=False)
    result_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class DecisionOption(Base):
    __tablename__ = "decision_options"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_id)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("simulation_runs.id"), nullable=False, index=True)
    tenant_id: Mapped[str | None] = mapped_column(String(120), index=True)
    preset_id: Mapped[str | None] = mapped_column(String(120))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    expected_effects: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    risks: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    conditions: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    ranking: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class Hypothesis(Base):
    __tablename__ = "hypotheses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_id)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("simulation_runs.id"), nullable=False, index=True)
    decision_option_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("decision_options.id"), index=True
    )
    prediction_version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("prediction_versions.id"), index=True
    )
    tenant_id: Mapped[str | None] = mapped_column(String(120), index=True)
    preset_id: Mapped[str | None] = mapped_column(String(120))
    prediction: Mapped[str] = mapped_column(Text, nullable=False)
    time_horizon: Mapped[str] = mapped_column(String(64), default="3_months", nullable=False)
    verification_status: Mapped[str] = mapped_column(String(32), default="PENDING", nullable=False)
    actual_outcome: Mapped[str | None] = mapped_column(Text)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class PredictionSeries(Base):
    __tablename__ = "prediction_series"
    __table_args__ = (UniqueConstraint("source_type", "source_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_id)
    tenant_id: Mapped[str | None] = mapped_column(String(120), index=True)
    preset_id: Mapped[str | None] = mapped_column(String(120), index=True)
    subject_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    subject_id: Mapped[str | None] = mapped_column(String(120), index=True)
    domain_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    source_run_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("simulation_runs.id"), index=True)
    decision_option_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("decision_options.id"), index=True)
    hypothesis_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("hypotheses.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE", nullable=False, index=True)
    current_version_id: Mapped[str | None] = mapped_column(String(36), index=True)
    series_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class PredictionVersion(Base):
    __tablename__ = "prediction_versions"
    __table_args__ = (UniqueConstraint("series_id", "version_number"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_id)
    series_id: Mapped[str] = mapped_column(String(36), ForeignKey("prediction_series.id"), nullable=False, index=True)
    run_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("simulation_runs.id"), index=True)
    base_version_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("prediction_versions.id"), index=True)
    parent_version_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("prediction_versions.id"), index=True)
    hypothesis_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("hypotheses.id"), index=True)
    decision_option_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("decision_options.id"), index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    trigger_ref_id: Mapped[str | None] = mapped_column(String(120), index=True)
    trigger_event_id: Mapped[str | None] = mapped_column(String(120), index=True)
    prediction_text: Mapped[str] = mapped_column(Text, nullable=False)
    time_horizon: Mapped[str] = mapped_column(String(64), default="3_months", nullable=False)
    probability: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE", nullable=False, index=True)
    summary_delta: Mapped[str | None] = mapped_column(Text)
    version_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PredictionEvidenceLink(Base):
    __tablename__ = "prediction_evidence_links"
    __table_args__ = (UniqueConstraint("version_id", "evidence_item_id", "claim_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_id)
    series_id: Mapped[str] = mapped_column(String(36), ForeignKey("prediction_series.id"), nullable=False, index=True)
    version_id: Mapped[str] = mapped_column(String(36), ForeignKey("prediction_versions.id"), nullable=False, index=True)
    prediction_version_id: Mapped[str] = mapped_column(String(36), ForeignKey("prediction_versions.id"), nullable=False, index=True)
    evidence_item_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("evidence_items.id"), index=True)
    claim_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("claims.id"), index=True)
    run_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("simulation_runs.id"), index=True)
    decision_record_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("decision_records.id"), index=True)
    link_type: Mapped[str] = mapped_column(String(32), default="supporting", nullable=False)
    impact_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    impact_direction: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    impact_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class PredictionRevisionJob(Base):
    __tablename__ = "prediction_revision_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_id)
    series_id: Mapped[str] = mapped_column(String(36), ForeignKey("prediction_series.id"), nullable=False, index=True)
    base_version_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("prediction_versions.id"), index=True)
    claim_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("claims.id"), index=True)
    trigger_claim_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("claims.id"), index=True)
    evidence_item_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("evidence_items.id"), index=True)
    trigger_evidence_item_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("evidence_items.id"), index=True)
    trigger_topic: Mapped[str | None] = mapped_column(String(128), index=True)
    reason: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="PENDING", nullable=False, index=True)
    revision_run_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("simulation_runs.id"), index=True)
    new_run_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("simulation_runs.id"), index=True)
    new_version_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("prediction_versions.id"), index=True)
    lease_owner: Mapped[str | None] = mapped_column(String(120), index=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    processing_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)
    job_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SourceCursorState(Base):
    __tablename__ = "source_cursor_states"
    __table_args__ = (
        UniqueConstraint("watch_rule_id", "source_type", "source_url_or_query"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_id)
    watch_rule_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("watch_rules.id"), index=True
    )
    source_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_url_or_query: Mapped[str] = mapped_column(Text, nullable=False)
    tenant_id: Mapped[str | None] = mapped_column(String(120), index=True)
    preset_id: Mapped[str | None] = mapped_column(String(120), index=True)
    cursor: Mapped[str | None] = mapped_column(Text)
    etag: Mapped[str | None] = mapped_column(String(256))
    last_modified: Mapped[str | None] = mapped_column(String(256))
    last_seen_hash: Mapped[str | None] = mapped_column(String(64))
    last_seen_raw_source_item_id: Mapped[str | None] = mapped_column(String(36))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class SourceChangeRecord(Base):
    __tablename__ = "source_change_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_id)
    source_state_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("source_cursor_states.id"), nullable=False, index=True
    )
    watch_rule_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("watch_rules.id"), index=True
    )
    old_raw_source_item_id: Mapped[str | None] = mapped_column(String(36))
    new_raw_source_item_id: Mapped[str | None] = mapped_column(String(36))
    old_hash: Mapped[str | None] = mapped_column(String(64))
    new_hash: Mapped[str | None] = mapped_column(String(64))
    change_type: Mapped[str] = mapped_column(String(16), nullable=False)
    significance: Mapped[str] = mapped_column(String(16), default="none", nullable=False)
    diff_summary: Mapped[str | None] = mapped_column(Text)
    changed_fields: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    claim_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    prediction_revision_job_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
