from __future__ import annotations

from datetime import datetime
from typing import Any
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from planagent.domain.enums import ExecutionMode, IngestRunStatus, ReviewItemStatus, SimulationRunStatus
from planagent.domain.types import GeneratedReportModel


class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class SourceSeedInput(APIModel):
    source_type: str
    source_url: str
    title: str
    content_text: str
    published_at: datetime | None = None
    source_metadata: dict[str, Any] = Field(default_factory=dict)


class IngestRunCreate(APIModel):
    requested_by: str = "system"
    tenant_id: str | None = None
    preset_id: str | None = None
    execution_mode: ExecutionMode | None = None
    items: list[SourceSeedInput] = Field(default_factory=list)


class IngestRunRead(APIModel):
    id: str
    requested_by: str
    execution_mode: ExecutionMode
    status: IngestRunStatus
    source_types: list[str] = Field(default_factory=list)
    request_payload: dict[str, Any] = Field(default_factory=dict)
    summary: dict[str, int] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    tenant_id: str | None = None
    preset_id: str | None = None

    @model_validator(mode="before")
    @classmethod
    def populate_metadata(cls, value: object) -> object:
        if isinstance(value, dict) or not hasattr(value, "request_payload"):
            return value
        request_payload = getattr(value, "request_payload", {}) or {}
        return {
            "id": value.id,
            "requested_by": value.requested_by,
            "execution_mode": value.execution_mode,
            "status": value.status,
            "source_types": value.source_types,
            "request_payload": value.request_payload,
            "summary": value.summary,
            "created_at": value.created_at,
            "updated_at": value.updated_at,
            "tenant_id": getattr(value, "tenant_id", None) or request_payload.get("tenant_id"),
            "preset_id": getattr(value, "preset_id", None) or request_payload.get("preset_id"),
        }


class ReviewDecisionRequest(APIModel):
    reviewer_id: str
    note: str | None = None


class ReviewItemRead(APIModel):
    id: str
    claim_id: str
    tenant_id: str | None = None
    preset_id: str | None = None
    queue_reason: str
    status: ReviewItemStatus
    reviewer_id: str | None = None
    review_note: str | None = None
    resolved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class SimulationRunCreate(APIModel):
    company_id: str | None = None
    company_name: str | None = None
    force_id: str | None = None
    force_name: str | None = None
    theater: str | None = None
    market: str = "ai"
    domain_id: str = "corporate"
    actor_template: str = "ai_model_provider"
    execution_mode: ExecutionMode | None = None
    tick_count: int | None = None
    seed: int = 7
    tenant_id: str | None = None
    preset_id: str | None = None
    initial_state: dict[str, float] = Field(default_factory=dict)
    military_use_mode: Literal["osint", "training", "full_domain"] = "full_domain"

    @model_validator(mode="after")
    def validate_domain_subject(self) -> "SimulationRunCreate":
        if self.domain_id == "corporate":
            if not self.company_id or not self.company_name:
                raise ValueError("Corporate simulation requires company_id and company_name.")
            return self
        if self.domain_id == "military":
            if not self.force_id or not self.force_name:
                raise ValueError("Military simulation requires force_id and force_name.")
            return self
        raise ValueError(f"Unsupported domain_id: {self.domain_id}.")


class SimulationRunRead(APIModel):
    id: str
    company_id: str | None = None
    force_id: str | None = None
    domain_id: str
    actor_template: str
    status: SimulationRunStatus
    execution_mode: ExecutionMode
    tick_count: int
    seed: int
    parent_run_id: str | None = None
    summary: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    tenant_id: str | None = None
    preset_id: str | None = None
    military_use_mode: str | None = None

    @model_validator(mode="before")
    @classmethod
    def populate_metadata(cls, value: object) -> object:
        if isinstance(value, dict) or not hasattr(value, "configuration"):
            return value
        configuration = getattr(value, "configuration", {}) or {}
        return {
            "id": value.id,
            "company_id": value.company_id,
            "force_id": value.force_id,
            "domain_id": value.domain_id,
            "actor_template": value.actor_template,
            "status": value.status,
            "execution_mode": value.execution_mode,
            "tick_count": value.tick_count,
            "seed": value.seed,
            "parent_run_id": value.parent_run_id,
            "summary": value.summary,
            "created_at": value.created_at,
            "updated_at": value.updated_at,
            "completed_at": value.completed_at,
            "tenant_id": getattr(value, "tenant_id", None) or configuration.get("tenant_id"),
            "preset_id": getattr(value, "preset_id", None) or configuration.get("preset_id"),
            "military_use_mode": getattr(value, "military_use_mode", None)
            or configuration.get("military_use_mode"),
        }


class ScenarioRunCreate(APIModel):
    fork_step: int | None = Field(default=None, ge=1)
    tick_count: int | None = Field(default=None, ge=1)
    assumptions: list[str] = Field(default_factory=list)
    decision_deltas: list[str] = Field(default_factory=list)
    state_overrides: dict[str, float] = Field(default_factory=dict)
    probability_band: str = "medium"


class ScenarioSearchRequest(APIModel):
    depth: int = Field(default=2, ge=1, le=3)
    beam_width: int = Field(default=3, ge=1, le=5)
    tick_count: int | None = Field(default=None, ge=1, le=12)
    assumptions: list[str] = Field(default_factory=list)


class ScenarioRunRead(APIModel):
    branch_id: str
    run_id: str
    parent_run_id: str
    fork_step: int
    assumptions: list[str] = Field(default_factory=list)
    decision_deltas: list[str] = Field(default_factory=list)
    kpi_trajectory: list[dict[str, Any]] = Field(default_factory=list)
    probability_band: str
    notable_events: list[str] = Field(default_factory=list)
    evidence_summary: str
    report_id: str | None = None
    created_at: datetime


class ScenarioCompareRead(APIModel):
    baseline_run_id: str
    domain_id: str
    branch_count: int
    metric_names: list[str] = Field(default_factory=list)
    baseline_final_state: dict[str, float] = Field(default_factory=dict)
    baseline_report_id: str | None = None
    baseline_recommendations: list[str] = Field(default_factory=list)
    recommended_branch_id: str | None = None
    summary: list[str] = Field(default_factory=list)
    branches: list[dict[str, Any]] = Field(default_factory=list)


class TimelineEventRead(APIModel):
    event_id: str
    event_type: str
    tick: int | None = None
    title: str
    detail: str | None = None
    related_ids: list[str] = Field(default_factory=list)
    created_at: datetime


class EvidenceGraphNodeRead(APIModel):
    node_id: str
    label: str
    node_type: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceGraphEdgeRead(APIModel):
    source_id: str
    target_id: str
    relation_type: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceGraphRead(APIModel):
    nodes: list[EvidenceGraphNodeRead] = Field(default_factory=list)
    edges: list[EvidenceGraphEdgeRead] = Field(default_factory=list)


class KnowledgeSearchResultRead(APIModel):
    node_id: str
    label: str
    node_type: str
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class GeoMapRead(APIModel):
    mode: str
    theater: str | None = None
    note: str | None = None
    assets: list[dict[str, Any]] = Field(default_factory=list)
    network: dict[str, Any] = Field(default_factory=dict)
    overlays: dict[str, Any] = Field(default_factory=dict)


class ScenarioTreeRead(APIModel):
    baseline_run_id: str
    active_run_id: str
    active_branch_id: str | None = None
    nodes: list[dict[str, Any]] = Field(default_factory=list)


class KPIMetricRead(APIModel):
    metric: str
    start: float | None = None
    end: float | None = None
    baseline_end: float | None = None
    delta: float | None = None


class KPIComparatorRead(APIModel):
    baseline_run_id: str
    current_run_id: str
    metrics: list[KPIMetricRead] = Field(default_factory=list)


class StartupKPICardRead(APIModel):
    metric_id: str
    label: str
    value: float | int | str
    unit: str | None = None
    target: str | None = None
    status: Literal["good", "watch", "risk"]
    insight: str


class StartupKPIPackRead(APIModel):
    preset_id: str
    tenant_id: str | None = None
    cards: list[StartupKPICardRead] = Field(default_factory=list)


class DebateSummaryRead(APIModel):
    debate_id: str
    topic: str
    trigger_type: str
    verdict: str | None = None
    confidence: float | None = None
    created_at: datetime


class RunWorkbenchRead(APIModel):
    run_id: str
    domain_id: str
    tenant_id: str | None = None
    preset_id: str | None = None
    latest_report_id: str | None = None
    review_queue: list[ReviewItemRead] = Field(default_factory=list)
    evidence_graph: EvidenceGraphRead
    timeline: list[TimelineEventRead] = Field(default_factory=list)
    geo_map: GeoMapRead
    scenario_tree: ScenarioTreeRead
    scenario_compare: ScenarioCompareRead | None = None
    decision_trace: list[dict[str, Any]] = Field(default_factory=list)
    kpi_comparator: KPIComparatorRead
    startup_kpi_pack: StartupKPIPackRead | None = None
    debate_records: list[DebateSummaryRead] = Field(default_factory=list)


class AgentStartupPresetRunCreate(APIModel):
    requested_by: str = "agent-startup-preset"
    tenant_id: str | None = None
    scenarios: list[Literal["baseline", "upside", "downside"]] = Field(
        default_factory=lambda: ["baseline", "upside", "downside"]
    )


class AgentStartupPresetScenarioRead(APIModel):
    scenario: Literal["baseline", "upside", "downside"]
    company_id: str
    run: SimulationRunRead
    startup_kpi_pack: StartupKPIPackRead | None = None
    report_id: str | None = None
    report_path: str
    decision_trace_path: str


class AgentStartupPresetRunRead(APIModel):
    preset_id: str
    tenant_id: str
    ingest_run: IngestRunRead
    scenarios: list[AgentStartupPresetScenarioRead] = Field(default_factory=list)


class DebateTriggerRequest(APIModel):
    run_id: str | None = None
    claim_id: str | None = None
    topic: str = Field(min_length=1)
    trigger_type: Literal[
        "manual",
        "evidence_assessment",
        "conflict_resolution",
        "pivot_decision",
        "branch_evaluation",
        "report_challenge",
    ] = "manual"
    target_type: Literal["run", "claim", "branch", "report"] = "run"
    target_id: str | None = None
    context_lines: list[str] = Field(default_factory=list)


class DebateRoundRead(APIModel):
    round_number: int
    role: str
    position: str
    confidence: float
    arguments: list[dict[str, Any]] = Field(default_factory=list)
    rebuttals: list[dict[str, Any]] = Field(default_factory=list)
    concessions: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime


class DebateVerdictRead(APIModel):
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
    created_at: datetime


class DebateDetailRead(APIModel):
    id: str
    run_id: str | None = None
    claim_id: str | None = None
    topic: str
    trigger_type: str
    status: str
    target_type: str
    target_id: str | None = None
    context_payload: dict[str, Any] = Field(default_factory=dict)
    rounds: list[DebateRoundRead] = Field(default_factory=list)
    verdict: DebateVerdictRead | None = None
    created_at: datetime
    updated_at: datetime


class RuleReloadResponse(APIModel):
    domains: list[str]
    rules_loaded: int


class QueueHealthBucketRead(APIModel):
    queue: str
    pending: int = 0
    processing: int = 0
    completed: int = 0
    failed: int = 0
    reclaimable: int = 0


class ReviewQueueReasonRead(APIModel):
    queue_reason: str
    pending: int = 0
    processing: int = 0
    completed: int = 0
    reclaimable: int = 0


class RuntimeQueueHealthRead(APIModel):
    generated_at: datetime
    tenant_id: str | None = None
    preset_id: str | None = None
    queues: list[QueueHealthBucketRead] = Field(default_factory=list)
    review_queue_reasons: list[ReviewQueueReasonRead] = Field(default_factory=list)
    dead_letter_count: int = 0
    degraded_sources: list[dict[str, Any]] = Field(default_factory=list)
    backpressure_active: bool = False


class StrategicAssistantRequest(APIModel):
    topic: str = Field(min_length=1)
    domain_id: Literal["auto", "corporate", "military"] = "auto"
    session_id: str | None = None
    session_name: str | None = None
    subject_id: str | None = None
    subject_name: str | None = None
    market: str = "ai"
    theater: str | None = None
    actor_template: str | None = None
    tick_count: int | None = Field(default=None, ge=1, le=12)
    tenant_id: str | None = None
    preset_id: str | None = None
    auto_refresh_enabled: bool = True
    refresh_timezone: str = "UTC"
    refresh_hour_local: int = Field(default=9, ge=0, le=23)
    auto_fetch_news: bool = True
    include_google_news: bool = True
    include_reddit: bool = True
    include_hacker_news: bool = True
    include_github: bool = True
    include_rss_feeds: bool = True
    include_gdelt: bool = True
    include_weather: bool = False
    include_aviation: bool = False
    include_x: bool = True
    source_types: list[str] = Field(default_factory=list)
    max_source_items: dict[str, int] = Field(default_factory=dict)
    max_news_items: int = Field(default=5, ge=0, le=10)
    max_tech_items: int = Field(default=3, ge=0, le=10)
    max_reddit_items: int = Field(default=3, ge=0, le=10)
    max_github_items: int = Field(default=3, ge=0, le=10)
    max_rss_items: int = Field(default=3, ge=0, le=10)
    max_gdelt_items: int = Field(default=3, ge=0, le=10)
    max_weather_items: int = Field(default=1, ge=0, le=3)
    max_aviation_items: int = Field(default=1, ge=0, le=3)
    max_x_items: int = Field(default=3, ge=0, le=10)


class PanelDiscussionMessageRead(APIModel):
    participant_id: str
    label: str
    model_target: Literal["primary", "extraction", "x_search", "report"] | str
    stance: Literal["support", "challenge", "monitor"]
    summary: str
    key_points: list[str] = Field(default_factory=list)
    recommendation: str
    confidence: float = Field(ge=0.0, le=1.0)


class StrategicAssistantResponse(APIModel):
    session_id: str | None = None
    topic: str
    domain_id: str
    subject_id: str
    subject_name: str
    analysis: AnalysisResponse
    ingest_run: IngestRunRead
    simulation_run: SimulationRunRead
    latest_report: GeneratedReportModel | None = None
    debate: DebateDetailRead | None = None
    workbench: RunWorkbenchRead
    panel_discussion: list[PanelDiscussionMessageRead] = Field(default_factory=list)
    generated_at: datetime


class AnalysisRequest(APIModel):
    content: str = Field(min_length=1)
    domain_id: Literal["auto", "general", "corporate", "military"] = "auto"
    auto_fetch_news: bool = True
    include_google_news: bool = True
    include_reddit: bool = True
    include_hacker_news: bool = True
    include_github: bool = True
    include_rss_feeds: bool = True
    include_gdelt: bool = True
    include_weather: bool = False
    include_aviation: bool = False
    include_x: bool = False
    source_types: list[str] = Field(default_factory=list)
    max_source_items: dict[str, int] = Field(default_factory=dict)
    max_news_items: int = Field(default=5, ge=0, le=10)
    max_tech_items: int = Field(default=3, ge=0, le=10)
    max_reddit_items: int = Field(default=3, ge=0, le=10)
    max_github_items: int = Field(default=3, ge=0, le=10)
    max_rss_items: int = Field(default=3, ge=0, le=10)
    max_gdelt_items: int = Field(default=3, ge=0, le=10)
    max_weather_items: int = Field(default=1, ge=0, le=3)
    max_aviation_items: int = Field(default=1, ge=0, le=3)
    max_x_items: int = Field(default=3, ge=0, le=10)


class AnalysisSourceRead(APIModel):
    source_type: str
    title: str
    url: str
    summary: str
    published_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AnalysisStepRead(APIModel):
    stage: str
    message: str
    detail: str | None = None


class AnalysisResponse(APIModel):
    query: str
    domain_id: str
    status: Literal["completed"]
    summary: str
    reasoning_steps: list[AnalysisStepRead] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    sources: list[AnalysisSourceRead] = Field(default_factory=list)
    generated_at: datetime


StrategicAssistantResponse.model_rebuild()


class StrategicSessionRead(APIModel):
    id: str
    name: str
    topic: str
    domain_id: str
    subject_id: str | None = None
    subject_name: str | None = None
    market: str | None = None
    theater: str | None = None
    actor_template: str | None = None
    tick_count: int | None = None
    tenant_id: str | None = None
    preset_id: str | None = None
    source_preferences: dict[str, Any] = Field(default_factory=dict)
    auto_refresh_enabled: bool = True
    refresh_timezone: str = "UTC"
    refresh_hour_local: int = 9
    next_refresh_at: datetime | None = None
    refresh_attempts: int = 0
    last_refresh_error: str | None = None
    latest_brief_summary: str | None = None
    latest_run_summary: str | None = None
    latest_debate_verdict: str | None = None
    latest_briefed_at: datetime | None = None
    latest_run_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class StrategicBriefRecordRead(APIModel):
    id: str
    session_id: str
    tenant_id: str | None = None
    preset_id: str | None = None
    domain_id: str
    summary: str
    source_count: int = 0
    analysis: AnalysisResponse
    generated_at: datetime


class StrategicRunSnapshotRead(APIModel):
    id: str
    session_id: str
    tenant_id: str | None = None
    preset_id: str | None = None
    ingest_run_id: str | None = None
    simulation_run_id: str | None = None
    debate_id: str | None = None
    generated_report_id: str | None = None
    result: StrategicAssistantResponse
    generated_at: datetime


class StrategicSessionDetailRead(APIModel):
    session: StrategicSessionRead
    daily_briefs: list[StrategicBriefRecordRead] = Field(default_factory=list)
    recent_runs: list[StrategicRunSnapshotRead] = Field(default_factory=list)


StrategicRunSnapshotRead.model_rebuild()


class OpenAIStatusResponse(APIModel):
    configured: bool
    responses_api: bool = True
    auth_mode: str = "api_key"
    configured_targets: list[str] = Field(default_factory=list)
    primary_configured: bool
    extraction_configured: bool
    x_search_configured: bool
    report_configured: bool
    primary_model: str
    resolved_primary_model: str
    extraction_model: str
    x_search_model: str
    report_model: str
    primary_base_url: str | None = None
    extraction_base_url: str | None = None
    x_search_base_url: str | None = None
    report_base_url: str | None = None
    resolved_extraction_model: str
    resolved_x_search_model: str
    resolved_report_model: str
    model_sources: dict[str, str] = Field(default_factory=dict)
    api_key_sources: dict[str, str] = Field(default_factory=dict)
    base_url_sources: dict[str, str] = Field(default_factory=dict)
    target_diagnostics: dict[str, dict[str, Any]] = Field(default_factory=dict)
    base_url: str | None = None
    last_error: str | None = None


class OpenAITestRequest(APIModel):
    target: Literal[
        "primary",
        "extraction",
        "x_search",
        "report",
        "debate_advocate",
        "debate_challenger",
        "debate_arbitrator",
    ] = "primary"
    model: str | None = None
    prompt: str = "Reply with exactly: OK"
    max_output_tokens: int = Field(default=32, ge=1, le=256)


class OpenAITestResponse(APIModel):
    ok: bool
    configured: bool
    target: str
    model: str
    resolved_model: str
    base_url: str | None = None
    api_mode: Literal["responses", "chat.completions", "chat.completions.raw"] | None = None
    response_id: str | None = None
    output_text: str | None = None
    last_error: str | None = None


class WatchRuleCreate(APIModel):
    name: str = Field(min_length=1)
    domain_id: Literal["corporate", "military"]
    query: str = Field(min_length=1)
    source_types: list[str] = Field(
        default_factory=lambda: ["google_news", "reddit", "hacker_news", "github", "rss", "gdelt", "aviation"]
    )
    keywords: list[str] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)
    entity_tags: list[str] = Field(default_factory=list)
    trigger_threshold: float = Field(default=0.0, ge=0.0, le=1.0)
    min_new_evidence_count: int = Field(default=1, ge=0, le=50)
    importance_threshold: float = Field(default=0.0, ge=0.0, le=1.0)
    poll_interval_minutes: int = Field(default=60, ge=5, le=1440)
    auto_trigger_simulation: bool = False
    auto_trigger_debate: bool = False
    tick_count: int = Field(default=0, ge=0)
    tenant_id: str | None = None
    preset_id: str | None = None


class WatchRuleUpdate(APIModel):
    name: str | None = None
    query: str | None = None
    source_types: list[str] | None = None
    keywords: list[str] | None = None
    exclude_keywords: list[str] | None = None
    entity_tags: list[str] | None = None
    trigger_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    min_new_evidence_count: int | None = Field(default=None, ge=0, le=50)
    importance_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    poll_interval_minutes: int | None = Field(default=None, ge=5, le=1440)
    enabled: bool | None = None
    auto_trigger_simulation: bool | None = None
    auto_trigger_debate: bool | None = None
    tick_count: int | None = Field(default=None, ge=0)


class WatchRuleRead(APIModel):
    id: str
    name: str
    domain_id: str
    query: str
    source_types: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)
    entity_tags: list[str] = Field(default_factory=list)
    trigger_threshold: float = 0.0
    min_new_evidence_count: int = 1
    importance_threshold: float = 0.0
    poll_interval_minutes: int
    enabled: bool
    next_poll_at: datetime | None = None
    poll_attempts: int = 0
    last_poll_at: datetime | None = None
    last_poll_error: str | None = None
    auto_trigger_simulation: bool
    auto_trigger_debate: bool
    tick_count: int
    tenant_id: str | None = None
    preset_id: str | None = None
    created_at: datetime
    updated_at: datetime


class WatchRuleTriggerRead(APIModel):
    rule_id: str
    rule_name: str
    status: str
    ingest_run_id: str | None = None
    sources_fetched: int = 0
    simulation_run_id: str | None = None
    debate_id: str | None = None
    error: str | None = None


class ReplayPackageRead(APIModel):
    run_id: str
    domain_id: str
    package: dict[str, Any]
    created_at: datetime


class JarvisRunCreate(APIModel):
    run_id: str | None = None
    target_type: Literal["run", "claim", "report", "debate", "analysis"] = "run"
    target_id: str | None = None
    prompt: str | None = None


class JarvisRunRead(APIModel):
    id: str
    run_id: str | None = None
    target_type: str
    target_id: str | None = None
    status: str
    profile_id: str
    result_payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class DecisionOptionCreate(APIModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    expected_effects: dict[str, Any] = Field(default_factory=dict)
    risks: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    conditions: list[str] = Field(default_factory=list)
    ranking: int = Field(default=1, ge=1)


class DecisionOptionRead(APIModel):
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


class HypothesisCreate(APIModel):
    prediction: str = Field(min_length=1)
    time_horizon: str = Field(default="3_months", min_length=1, max_length=64)
    decision_option_id: str | None = None


class HypothesisVerify(APIModel):
    verification_status: Literal["PENDING", "CONFIRMED", "REFUTED", "PARTIAL"]
    actual_outcome: str | None = None


class HypothesisRead(APIModel):
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


class CalibrationRead(APIModel):
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


class CalibrationComputeRequest(APIModel):
    domain_id: str
    tenant_id: str | None = None
