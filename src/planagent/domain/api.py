from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from planagent.domain.enums import ExecutionMode, IngestRunStatus, ReviewItemStatus, SimulationRunStatus


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


class ReviewDecisionRequest(APIModel):
    reviewer_id: str
    note: str | None = None


class ReviewItemRead(APIModel):
    id: str
    claim_id: str
    queue_reason: str
    status: ReviewItemStatus
    reviewer_id: str | None = None
    review_note: str | None = None
    resolved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class PlannedFeatureResponse(APIModel):
    feature: str
    phase: str
    status: str = "planned"


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
    initial_state: dict[str, float] = Field(default_factory=dict)

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


class ScenarioRunCreate(APIModel):
    fork_step: int | None = Field(default=None, ge=1)
    tick_count: int | None = Field(default=None, ge=1)
    assumptions: list[str] = Field(default_factory=list)
    decision_deltas: list[str] = Field(default_factory=list)
    state_overrides: dict[str, float] = Field(default_factory=dict)
    probability_band: str = "medium"


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
    branches: list[dict[str, Any]] = Field(default_factory=list)


class RuleReloadResponse(APIModel):
    domains: list[str]
    rules_loaded: int


class OpenAIStatusResponse(APIModel):
    configured: bool
    responses_api: bool = True
    auth_mode: str = "api_key"
    primary_model: str
    resolved_primary_model: str
    extraction_model: str
    report_model: str
    resolved_extraction_model: str
    resolved_report_model: str
    base_url: str | None = None
    last_error: str | None = None


class OpenAITestRequest(APIModel):
    model: str | None = None
    prompt: str = "Reply with exactly: OK"
    max_output_tokens: int = Field(default=32, ge=1, le=256)


class OpenAITestResponse(APIModel):
    ok: bool
    configured: bool
    model: str
    resolved_model: str
    response_id: str | None = None
    output_text: str | None = None
    last_error: str | None = None
