from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from planagent.domain.enums import ClaimStatus, ReviewItemStatus


class PlatformModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class RawSourceItemModel(PlatformModel):
    id: str
    ingest_run_id: str
    source_type: str
    source_url: str
    title: str
    content_text: str
    published_at: datetime | None = None
    dedupe_key: str
    created_at: datetime


class NormalizedItemModel(PlatformModel):
    id: str
    raw_source_item_id: str
    canonical_url: str
    title: str
    body_text: str
    confidence: float
    normalized_at: datetime


class EvidenceItemModel(PlatformModel):
    id: str
    normalized_item_id: str
    tenant_id: str | None = None
    preset_id: str | None = None
    evidence_type: str
    title: str
    summary: str
    body_text: str
    source_url: str
    confidence: float
    status: str
    created_at: datetime
    updated_at: datetime


class ClaimModel(PlatformModel):
    id: str
    evidence_item_id: str
    tenant_id: str | None = None
    preset_id: str | None = None
    subject: str
    predicate: str
    object_text: str
    statement: str
    kind: str = "unclassified"
    confidence: float
    status: ClaimStatus
    requires_review: bool
    reasoning: str | None = None
    created_at: datetime
    updated_at: datetime


class EntityModel(PlatformModel):
    id: str
    name: str
    entity_type: str
    attributes: dict[str, Any] = Field(default_factory=dict)


class RelationshipModel(PlatformModel):
    id: str
    source_entity_id: str
    target_entity_id: str
    relation_type: str
    confidence: float


class SignalModel(PlatformModel):
    id: str
    claim_id: str | None = None
    tenant_id: str | None = None
    preset_id: str | None = None
    signal_type: str
    title: str
    confidence: float
    created_at: datetime


class EventModel(PlatformModel):
    id: str
    claim_id: str | None = None
    tenant_id: str | None = None
    preset_id: str | None = None
    event_type: str
    title: str
    confidence: float
    created_at: datetime


class TrendModel(PlatformModel):
    id: str
    claim_id: str | None = None
    tenant_id: str | None = None
    preset_id: str | None = None
    trend_type: str
    title: str
    confidence: float
    created_at: datetime


class GeoAssetModel(PlatformModel):
    id: str
    run_id: str
    force_id: str | None = None
    name: str
    asset_type: str
    latitude: float
    longitude: float
    properties: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class CompanyProfileModel(PlatformModel):
    id: str
    name: str
    market: str
    attributes: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ForceProfileModel(PlatformModel):
    id: str
    name: str
    theater: str
    attributes: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class StateSnapshotModel(PlatformModel):
    id: str
    run_id: str
    tick: int
    actor_id: str
    state: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class ExternalShockModel(PlatformModel):
    id: str
    run_id: str
    tick: int
    domain: str
    shock_type: str
    summary: str
    evidence_ids: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class DecisionRecordModel(PlatformModel):
    id: str
    run_id: str
    tick: int
    sequence: int
    actor_id: str
    action_id: str
    why_selected: str
    evidence_ids: list[str] = Field(default_factory=list)
    policy_rule_ids: list[str] = Field(default_factory=list)
    expected_effect: dict[str, Any] = Field(default_factory=dict)
    actual_effect: dict[str, Any] = Field(default_factory=dict)
    debate_verdict_id: str | None = None
    decision_method: str = "rule_engine"
    created_at: datetime | None = None


class ScenarioBranchModel(PlatformModel):
    branch_id: str
    run_id: str
    parent_id: str | None = None
    fork_step: int
    assumptions: list[str] = Field(default_factory=list)
    decision_deltas: list[str] = Field(default_factory=list)
    kpi_trajectory: list[dict[str, Any]] = Field(default_factory=list)
    probability_band: str
    notable_events: list[str] = Field(default_factory=list)
    evidence_summary: str


class AnalystReviewModel(PlatformModel):
    id: str
    claim_id: str
    queue_reason: str
    status: ReviewItemStatus
    reviewer_id: str | None = None
    review_note: str | None = None


class GeneratedReportModel(PlatformModel):
    id: str
    run_id: str
    company_id: str | None = None
    force_id: str | None = None
    scenario_id: str | None = None
    tenant_id: str | None = None
    preset_id: str | None = None
    title: str
    summary: str
    report_format: str
    sections: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class SimulationRunModel(PlatformModel):
    id: str
    company_id: str | None = None
    force_id: str | None = None
    domain_id: str
    actor_template: str
    status: str
    execution_mode: str
    tick_count: int
    seed: int
    parent_run_id: str | None = None
    summary: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


class DebateArgumentModel(PlatformModel):
    claim: str
    evidence_ids: list[str] = Field(default_factory=list)
    reasoning: str
    strength: str


class DebateRoundModel(PlatformModel):
    id: str | None = None
    debate_id: str | None = None
    round_number: int
    role: str
    position: str
    confidence: float
    arguments: list[DebateArgumentModel] = Field(default_factory=list)
    rebuttals: list[dict[str, Any]] = Field(default_factory=list)
    concessions: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime | None = None


class DebateSessionModel(PlatformModel):
    id: str
    run_id: str | None = None
    claim_id: str | None = None
    topic: str
    trigger_type: str
    status: str | None = None
    target_type: str | None = None
    target_id: str | None = None
    context_payload: dict[str, Any] = Field(default_factory=dict)
    rounds: list[DebateRoundModel] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DebateVerdictModel(PlatformModel):
    debate_id: str
    topic: str
    trigger_type: str
    rounds_completed: int
    verdict: str
    confidence: float
    winning_arguments: list[str] = Field(default_factory=list)
    decisive_evidence: list[str] = Field(default_factory=list)
    conditions: list[str] | None = None
    minority_opinion: str | None = None
    audit_trail: list[DebateRoundModel] = Field(default_factory=list)


class DecisionOptionModel(PlatformModel):
    id: str
    run_id: str
    tenant_id: str | None = None
    preset_id: str | None = None
    title: str
    description: str
    expected_effects: dict[str, Any] = Field(default_factory=dict)
    risks: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float
    conditions: list[str] = Field(default_factory=list)
    ranking: int
    created_at: datetime | None = None


class HypothesisModel(PlatformModel):
    id: str
    run_id: str
    decision_option_id: str | None = None
    tenant_id: str | None = None
    preset_id: str | None = None
    prediction: str
    time_horizon: str
    verification_status: str
    actual_outcome: str | None = None
    verified_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CalibrationRecordModel(PlatformModel):
    id: str
    domain_id: str
    tenant_id: str | None = None
    period_start: datetime
    period_end: datetime
    total_hypotheses: int
    confirmed: int
    refuted: int
    partial: int
    pending: int
    calibration_score: float
    rule_accuracy: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class WatchRuleModel(PlatformModel):
    id: str
    name: str
    domain_id: str
    query: str
    source_types: list[str] = Field(default_factory=list)
    poll_interval_minutes: int
    enabled: bool
    next_poll_at: datetime | None = None
    lease_owner: str | None = None
    lease_expires_at: datetime | None = None
    poll_attempts: int
    last_poll_at: datetime | None = None
    last_poll_error: str | None = None
    auto_trigger_simulation: bool
    auto_trigger_debate: bool
    tick_count: int
    tenant_id: str | None = None
    preset_id: str | None = None
    created_at: datetime
    updated_at: datetime
