from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from planagent.config import get_settings
from planagent.db import get_session
from planagent.domain.api import (
    AnalysisRequest,
    AnalysisResponse,
    IngestRunCreate,
    IngestRunRead,
    OpenAIStatusResponse,
    OpenAITestRequest,
    OpenAITestResponse,
    PlannedFeatureResponse,
    ReviewDecisionRequest,
    ReviewItemRead,
    RuleReloadResponse,
    ScenarioCompareRead,
    ScenarioRunCreate,
    ScenarioRunRead,
    SimulationRunCreate,
    SimulationRunRead,
)
from planagent.domain.models import Claim, EventRecord, EvidenceItem, ReviewItem, Signal, SimulationRun, Trend
from planagent.domain.types import (
    ClaimModel,
    DecisionRecordModel,
    EventModel,
    EvidenceItemModel,
    ExternalShockModel,
    GeneratedReportModel,
    GeoAssetModel,
    SignalModel,
    TrendModel,
)
from planagent.services.analysis import AutomatedAnalysisService
from planagent.services.pipeline import PhaseOnePipelineService
from planagent.services.simulation import SimulationService

router = APIRouter()


def get_pipeline_service(request: Request) -> PhaseOnePipelineService:
    return PhaseOnePipelineService(
        get_settings(),
        request.app.state.event_bus,
        request.app.state.openai_service,
    )


def get_simulation_service(request: Request) -> SimulationService:
    return SimulationService(
        get_settings(),
        request.app.state.event_bus,
        request.app.state.rule_registry,
        request.app.state.openai_service,
    )


def get_analysis_service(request: Request) -> AutomatedAnalysisService:
    return AutomatedAnalysisService(get_settings(), request.app.state.openai_service)


def planned_feature(feature: str, phase: str) -> Any:
    raise HTTPException(
        status_code=501,
        detail=PlannedFeatureResponse(feature=feature, phase=phase).model_dump(),
    )


@router.get("/")
async def root(request: Request) -> dict[str, object]:
    return {
        "app": get_settings().app_name,
        "status": "ok",
        "docs_url": "/docs",
        "health_url": "/health",
        "openai": request.app.state.openai_service.status().model_dump(),
    }


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/analysis", response_model=AnalysisResponse)
async def analyze_content(
    payload: AnalysisRequest,
    request: Request,
) -> AnalysisResponse:
    service = get_analysis_service(request)
    return await service.analyze(payload)


@router.post("/analysis/stream")
async def analyze_content_stream(
    payload: AnalysisRequest,
    request: Request,
) -> StreamingResponse:
    service = get_analysis_service(request)

    async def event_stream():
        async for event in service.stream_analysis(payload):
            yield f"event: {event.event}\n"
            yield f"data: {json.dumps(event.payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/ingest/runs", response_model=IngestRunRead, status_code=201)
async def create_ingest_run(
    payload: IngestRunCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> IngestRunRead:
    service = get_pipeline_service(request)
    run = await service.create_ingest_run(session, payload)
    return IngestRunRead.model_validate(run)


@router.get("/evidence", response_model=list[EvidenceItemModel])
async def list_evidence(session: AsyncSession = Depends(get_session)) -> list[EvidenceItemModel]:
    evidence = list(
        (await session.scalars(select(EvidenceItem).order_by(EvidenceItem.created_at.desc()))).all()
    )
    return [EvidenceItemModel.model_validate(item) for item in evidence]


@router.get("/claims", response_model=list[ClaimModel])
async def list_claims(
    status: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[ClaimModel]:
    query = select(Claim).order_by(Claim.created_at.desc())
    if status:
        query = query.where(Claim.status == status.upper())
    claims = list((await session.scalars(query)).all())
    return [ClaimModel.model_validate(claim) for claim in claims]


@router.get("/signals", response_model=list[SignalModel])
async def list_signals(session: AsyncSession = Depends(get_session)) -> list[SignalModel]:
    signals = list((await session.scalars(select(Signal).order_by(Signal.created_at.desc()))).all())
    return [SignalModel.model_validate(item) for item in signals]


@router.get("/events", response_model=list[EventModel])
async def list_events(session: AsyncSession = Depends(get_session)) -> list[EventModel]:
    events = list((await session.scalars(select(EventRecord).order_by(EventRecord.created_at.desc()))).all())
    return [EventModel.model_validate(item) for item in events]


@router.get("/trends", response_model=list[TrendModel])
async def list_trends(session: AsyncSession = Depends(get_session)) -> list[TrendModel]:
    trends = list((await session.scalars(select(Trend).order_by(Trend.created_at.desc()))).all())
    return [TrendModel.model_validate(item) for item in trends]


@router.get("/review/items", response_model=list[ReviewItemRead])
async def list_review_items(session: AsyncSession = Depends(get_session)) -> list[ReviewItemRead]:
    review_items = list((await session.scalars(select(ReviewItem).order_by(ReviewItem.created_at.desc()))).all())
    return [ReviewItemRead.model_validate(item) for item in review_items]


@router.post("/review/items/{review_item_id}/accept", response_model=ReviewItemRead)
async def accept_review_item(
    review_item_id: str,
    payload: ReviewDecisionRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> ReviewItemRead:
    service = get_pipeline_service(request)
    try:
        review_item = await service.accept_review_item(session, review_item_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ReviewItemRead.model_validate(review_item)


@router.post("/review/items/{review_item_id}/reject", response_model=ReviewItemRead)
async def reject_review_item(
    review_item_id: str,
    payload: ReviewDecisionRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> ReviewItemRead:
    service = get_pipeline_service(request)
    try:
        review_item = await service.reject_review_item(session, review_item_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ReviewItemRead.model_validate(review_item)


@router.post("/simulation/runs", response_model=SimulationRunRead, status_code=201)
async def create_simulation_run(
    payload: SimulationRunCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> SimulationRunRead:
    service = get_simulation_service(request)
    try:
        run = await service.create_simulation_run(session, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SimulationRunRead.model_validate(run)


@router.post("/scenario/runs/{simulation_run_id}", response_model=ScenarioRunRead, status_code=201)
async def create_scenario_run(
    simulation_run_id: str,
    payload: ScenarioRunCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> ScenarioRunRead:
    service = get_simulation_service(request)
    try:
        branch = await service.create_scenario_run(session, simulation_run_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    run = await session.get(SimulationRun, branch.run_id)
    report_id = run.summary.get("report_id") if run is not None else None
    return ScenarioRunRead(
        branch_id=branch.id,
        run_id=branch.run_id,
        parent_run_id=branch.parent_run_id,
        fork_step=branch.fork_step,
        assumptions=branch.assumptions,
        decision_deltas=branch.decision_deltas,
        kpi_trajectory=branch.kpi_trajectory,
        probability_band=branch.probability_band,
        notable_events=branch.notable_events,
        evidence_summary=branch.evidence_summary,
        report_id=report_id,
        created_at=branch.created_at,
    )


@router.get("/runs/{run_id}/decision-trace", response_model=list[DecisionRecordModel])
async def get_decision_trace(
    run_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> list[DecisionRecordModel]:
    service = get_simulation_service(request)
    records = await service.list_decision_trace(session, run_id)
    return [DecisionRecordModel.model_validate(record) for record in records]


@router.get("/runs/{run_id}/scenario-compare", response_model=ScenarioCompareRead)
async def get_scenario_compare(
    run_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> ScenarioCompareRead:
    service = get_simulation_service(request)
    try:
        payload = await service.build_scenario_compare(session, run_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ScenarioCompareRead(**payload)


@router.get("/runs/{run_id}/geo-assets", response_model=list[GeoAssetModel])
async def get_run_geo_assets(
    run_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> list[GeoAssetModel]:
    service = get_simulation_service(request)
    assets = await service.list_geo_assets(session, run_id)
    return [GeoAssetModel.model_validate(asset) for asset in assets]


@router.get("/runs/{run_id}/external-shocks", response_model=list[ExternalShockModel])
async def get_run_external_shocks(
    run_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> list[ExternalShockModel]:
    service = get_simulation_service(request)
    shocks = await service.list_external_shocks(session, run_id)
    return [ExternalShockModel.model_validate(shock) for shock in shocks]


@router.get("/companies/{company_id}/reports/latest", response_model=GeneratedReportModel)
async def get_company_report(
    company_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> GeneratedReportModel:
    service = get_simulation_service(request)
    report = await service.latest_company_report(session, company_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"No report found for company {company_id}.")
    return GeneratedReportModel.model_validate(report)


@router.get("/military/scenarios/{scenario_id}/reports/latest", response_model=GeneratedReportModel)
async def get_military_report(
    scenario_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> GeneratedReportModel:
    service = get_simulation_service(request)
    report = await service.latest_military_report(session, scenario_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"No report found for military scenario {scenario_id}.")
    return GeneratedReportModel.model_validate(report)


@router.get("/debates/{debate_id}")
async def get_debate(debate_id: str) -> Any:
    planned_feature(f"debate {debate_id}", "Phase 5")


@router.get("/runs/{run_id}/debates")
async def get_run_debates(run_id: str) -> Any:
    planned_feature(f"debates for run {run_id}", "Phase 5")


@router.post("/debates/trigger")
async def trigger_debate() -> Any:
    planned_feature("manual debate trigger", "Phase 5")


@router.post("/admin/rules/reload", response_model=RuleReloadResponse)
async def reload_rules(request: Request) -> RuleReloadResponse:
    domains, total = request.app.state.rule_registry.reload()
    return RuleReloadResponse(domains=domains, rules_loaded=total)


@router.get("/admin/openai/status", response_model=OpenAIStatusResponse)
async def openai_status(request: Request) -> OpenAIStatusResponse:
    return request.app.state.openai_service.status()


@router.post("/admin/openai/test", response_model=OpenAITestResponse)
async def openai_test(
    payload: OpenAITestRequest,
    request: Request,
) -> OpenAITestResponse:
    result = await request.app.state.openai_service.test_connection(
        target=payload.target,
        model=payload.model,
        prompt=payload.prompt,
        max_output_tokens=payload.max_output_tokens,
    )
    if not result.ok and not result.configured:
        raise HTTPException(status_code=503, detail=result.last_error)
    if not result.ok:
        raise HTTPException(status_code=502, detail=result.last_error)
    return result
