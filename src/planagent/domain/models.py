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
    execution_mode: Mapped[str] = mapped_column(
        String(16), default=ExecutionMode.INLINE.value, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(24), default=IngestRunStatus.PENDING.value, nullable=False
    )
    source_types: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    request_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    summary: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    raw_items: Mapped[list["RawSourceItem"]] = relationship(back_populates="ingest_run")


class RawSourceItem(Base):
    __tablename__ = "raw_source_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_id)
    ingest_run_id: Mapped[str] = mapped_column(ForeignKey("ingest_runs.id"), nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    ingest_run: Mapped[IngestRun] = relationship(back_populates="raw_items")
    normalized_item: Mapped["NormalizedItem"] = relationship(back_populates="raw_item", uselist=False)


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
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    predicate: Mapped[str] = mapped_column(String(120), nullable=False)
    object_text: Mapped[str] = mapped_column(Text, nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
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


class ReviewItem(Base):
    __tablename__ = "review_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_id)
    claim_id: Mapped[str] = mapped_column(ForeignKey("claims.id"), nullable=False, unique=True)
    queue_reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default=ReviewItemStatus.PENDING.value, nullable=False
    )
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
    trend_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
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
    domain_id: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_template: Mapped[str] = mapped_column(String(120), nullable=False)
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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    simulation_run: Mapped[SimulationRun] = relationship(back_populates="decision_records")


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
