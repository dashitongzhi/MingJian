from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from planagent.db import get_session
from planagent.domain.api import (
    DebateDetailRead,
    DebateSummaryRead,
    DebateTriggerRequest,
    DecisionOptionCreate,
    DecisionOptionRead,
    HypothesisCreate,
    HypothesisRead,
    HypothesisVerify,
    ReplayPackageRead,
    RunWorkbenchRead,
    ScenarioCompareRead,
    ScenarioRunCreate,
    ScenarioRunRead,
    ScenarioSearchRequest,
    SimulationRunCreate,
    SimulationRunRead,
    StartupKPIPackRead,
)
from planagent.domain.models import (
    DecisionOption,
    GeneratedReport,
    Hypothesis,
    ScenarioReplayPackageRecord,
    SimulationRun,
    StateSnapshotRecord,
    utc_now,
)
from planagent.domain.types import (
    DecisionRecordModel,
    ExternalShockModel,
    GeneratedReportModel,
    GeoAssetModel,
)
from planagent.api.routes._deps import (
    get_debate_service,
    get_simulation_service,
    get_workbench_service,
)
from planagent.services.startup import (
    build_startup_kpi_pack,
)

router = APIRouter()


def _scenario_search_overrides(domain_id: str, index: int) -> dict[str, float]:
    scale = index + 1
    if domain_id == "military":
        return {
            "logistics_throughput": max(0.2, 0.78 - scale * 0.04),
            "civilian_risk": min(0.9, 0.35 + scale * 0.05),
            "isr_coverage": min(0.98, 0.75 + scale * 0.03),
        }
    return {
        "pipeline": min(1.4, 0.9 + scale * 0.04),
        "infra_cost_index": min(1.4, 1.0 + scale * 0.03),
        "delivery_velocity": max(0.55, 0.9 - scale * 0.03),
    }


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


@router.post("/runs/{run_id}/scenario-search", response_model=list[ScenarioRunRead], status_code=201)
async def create_scenario_search(
    run_id: str,
    payload: ScenarioSearchRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> list[ScenarioRunRead]:
    service = get_simulation_service(request)
    baseline = await session.get(SimulationRun, run_id)
    if baseline is None:
        raise HTTPException(status_code=404, detail=f"Simulation run {run_id} was not found.")

    created: list[ScenarioRunRead] = []
    beam = min(payload.beam_width, 5)
    for index in range(beam):
        fork_step = max(1, min(baseline.tick_count, 1 + index))
        probability = ["high", "medium-high", "medium", "medium-low", "low"][min(index, 4)]
        assumptions = [
            *(payload.assumptions or ["Automatic beam-search branch generated from baseline thresholds."]),
            f"branch_candidate={index + 1}",
            f"search_depth={payload.depth}",
        ]
        try:
            branch = await service.create_scenario_run(
                session,
                run_id,
                ScenarioRunCreate(
                    fork_step=fork_step,
                    tick_count=payload.tick_count,
                    assumptions=assumptions,
                    decision_deltas=[f"beam-search alternative {index + 1}"],
                    state_overrides=_scenario_search_overrides(baseline.domain_id, index),
                    probability_band=probability,
                ),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        branch_run = await session.get(SimulationRun, branch.run_id)
        created.append(
            ScenarioRunRead(
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
                report_id=branch_run.summary.get("report_id") if branch_run is not None else None,
                created_at=branch.created_at,
            )
        )
    return created


@router.get("/runs/{run_id}/decision-trace", response_model=list[DecisionRecordModel])
async def get_decision_trace(
    run_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> list[DecisionRecordModel]:
    service = get_simulation_service(request)
    records = await service.list_decision_trace(session, run_id)
    return [DecisionRecordModel.model_validate(record) for record in records]


@router.get("/runs/{run_id}/workbench", response_model=RunWorkbenchRead)
async def get_run_workbench(
    run_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> RunWorkbenchRead:
    workbench_service = get_workbench_service()
    simulation_service = get_simulation_service(request)
    try:
        workbench = await workbench_service.build_run_workbench(session, run_id)
        scenario_compare = await simulation_service.build_scenario_compare(session, run_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return workbench.model_copy(update={"scenario_compare": ScenarioCompareRead(**scenario_compare)})


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


@router.get("/runs/{run_id}/geojson")
async def get_run_geojson(
    run_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    service = get_simulation_service(request)
    assets = await service.list_geo_assets(session, run_id)
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": asset.id,
                "geometry": {
                    "type": "Point",
                    "coordinates": [asset.longitude, asset.latitude],
                },
                "properties": {
                    "name": asset.name,
                    "asset_type": asset.asset_type,
                    "force_id": asset.force_id,
                    **(asset.properties or {}),
                },
            }
            for asset in assets
        ],
    }


@router.get("/runs/{run_id}/replay-package", response_model=ReplayPackageRead)
async def get_replay_package(
    run_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> ReplayPackageRead:
    run = await session.get(SimulationRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Simulation run not found.")
    snapshots = list(
        (
            await session.scalars(
                select(StateSnapshotRecord)
                .where(StateSnapshotRecord.run_id == run_id)
                .order_by(StateSnapshotRecord.tick.asc())
            )
        ).all()
    )
    service = get_simulation_service(request)
    decisions = await service.list_decision_trace(session, run_id)
    shocks = await service.list_external_shocks(session, run_id)
    reports = list(
        (
            await session.scalars(
                select(GeneratedReport)
                .where(GeneratedReport.run_id == run_id)
                .order_by(GeneratedReport.created_at.asc())
            )
        ).all()
    )
    package = {
        "run": SimulationRunRead.model_validate(run).model_dump(mode="json"),
        "snapshots": [
            {"tick": item.tick, "actor_id": item.actor_id, "state": item.state}
            for item in snapshots
        ],
        "decisions": [DecisionRecordModel.model_validate(item).model_dump(mode="json") for item in decisions],
        "external_shocks": [ExternalShockModel.model_validate(item).model_dump(mode="json") for item in shocks],
        "reports": [GeneratedReportModel.model_validate(item).model_dump(mode="json") for item in reports],
    }
    record = ScenarioReplayPackageRecord(
        run_id=run.id,
        tenant_id=run.tenant_id,
        preset_id=run.preset_id,
        package_payload=package,
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return ReplayPackageRead(run_id=run.id, domain_id=run.domain_id, package=package, created_at=record.created_at)


@router.get("/companies/{company_id}/reports/latest", response_model=GeneratedReportModel)
async def get_company_report(
    company_id: str,
    request: Request,
    tenant_id: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> GeneratedReportModel:
    service = get_simulation_service(request)
    report = await service.latest_company_report(session, company_id, tenant_id=tenant_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"No report found for company {company_id}.")
    return GeneratedReportModel.model_validate(report)


@router.get("/runs/{run_id}/startup-kpis", response_model=StartupKPIPackRead)
async def get_run_startup_kpis(
    run_id: str,
    session: AsyncSession = Depends(get_session),
) -> StartupKPIPackRead:
    run = await session.get(SimulationRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Simulation run {run_id} was not found.")

    state_snapshots = list(
        (
            await session.scalars(
                select(StateSnapshotRecord)
                .where(StateSnapshotRecord.run_id == run.id)
                .order_by(StateSnapshotRecord.tick.asc())
            )
        ).all()
    )
    start_state = state_snapshots[0].state if state_snapshots else {}
    final_state = state_snapshots[-1].state if state_snapshots else {}
    kpi_pack = build_startup_kpi_pack(run, start_state, final_state, run.summary.get("matched_rules", []))
    if kpi_pack is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} does not expose a startup KPI pack.")
    return kpi_pack


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


@router.get("/scenarios/{scenario_id}/reports/latest", response_model=GeneratedReportModel)
async def get_scenario_report(
    scenario_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> GeneratedReportModel:
    service = get_simulation_service(request)
    report = await service.latest_scenario_report(session, scenario_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"No report found for scenario {scenario_id}.")
    return GeneratedReportModel.model_validate(report)


@router.get("/debates/{debate_id}", response_model=DebateDetailRead)
async def get_debate(
    debate_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> DebateDetailRead:
    service = get_debate_service(request)
    try:
        return await service.get_debate(session, debate_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/runs/{run_id}/debates", response_model=list[DebateSummaryRead])
async def get_run_debates(
    run_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> list[DebateSummaryRead]:
    service = get_debate_service(request)
    return await service.list_run_debates(session, run_id)


@router.post("/debates/trigger", response_model=DebateDetailRead, status_code=201)
async def trigger_debate(
    payload: DebateTriggerRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> DebateDetailRead:
    service = get_debate_service(request)
    try:
        return await service.trigger_debate(session, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ── Decision Options ─────────────────────────────────────────────────────────


@router.get("/runs/{run_id}/options", response_model=list[DecisionOptionRead])
async def list_decision_options(
    run_id: str,
    session: AsyncSession = Depends(get_session),
):
    run = await session.get(SimulationRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Simulation run not found.")
    options = list(
        (
            await session.scalars(
                select(DecisionOption)
                .where(DecisionOption.run_id == run_id)
                .order_by(DecisionOption.ranking.asc())
            )
        ).all()
    )
    return [DecisionOptionRead.model_validate(o) for o in options]


@router.post("/runs/{run_id}/options", response_model=DecisionOptionRead, status_code=201)
async def create_decision_option(
    run_id: str,
    payload: DecisionOptionCreate,
    session: AsyncSession = Depends(get_session),
):
    run = await session.get(SimulationRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Simulation run not found.")
    option = DecisionOption(
        run_id=run_id,
        tenant_id=run.tenant_id,
        preset_id=run.preset_id,
        title=payload.title,
        description=payload.description,
        expected_effects=payload.expected_effects,
        risks=payload.risks,
        evidence_ids=payload.evidence_ids,
        confidence=payload.confidence,
        conditions=payload.conditions,
        ranking=payload.ranking,
    )
    session.add(option)
    await session.commit()
    await session.refresh(option)
    return DecisionOptionRead.model_validate(option)


# ── Hypotheses ───────────────────────────────────────────────────────────────


@router.get("/runs/{run_id}/hypotheses", response_model=list[HypothesisRead])
async def list_hypotheses(
    run_id: str,
    session: AsyncSession = Depends(get_session),
):
    run = await session.get(SimulationRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Simulation run not found.")
    hypotheses = list(
        (
            await session.scalars(
                select(Hypothesis)
                .where(Hypothesis.run_id == run_id)
                .order_by(Hypothesis.created_at.desc())
            )
        ).all()
    )
    return [HypothesisRead.model_validate(h) for h in hypotheses]


@router.post("/runs/{run_id}/hypotheses", response_model=HypothesisRead, status_code=201)
async def create_hypothesis(
    run_id: str,
    payload: HypothesisCreate,
    session: AsyncSession = Depends(get_session),
):
    run = await session.get(SimulationRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Simulation run not found.")
    if payload.decision_option_id is not None:
        option = await session.get(DecisionOption, payload.decision_option_id)
        if option is None:
            raise HTTPException(status_code=404, detail="Decision option not found.")
        if option.run_id != run_id:
            raise HTTPException(
                status_code=400,
                detail="Decision option belongs to a different simulation run.",
            )
    hypothesis = Hypothesis(
        run_id=run_id,
        decision_option_id=payload.decision_option_id,
        tenant_id=run.tenant_id,
        preset_id=run.preset_id,
        prediction=payload.prediction,
        time_horizon=payload.time_horizon,
    )
    session.add(hypothesis)
    await session.commit()
    await session.refresh(hypothesis)
    return HypothesisRead.model_validate(hypothesis)


@router.post("/hypotheses/{hypothesis_id}/verify", response_model=HypothesisRead)
async def verify_hypothesis(
    hypothesis_id: str,
    payload: HypothesisVerify,
    session: AsyncSession = Depends(get_session),
):
    hypothesis = await session.get(Hypothesis, hypothesis_id)
    if hypothesis is None:
        raise HTTPException(status_code=404, detail="Hypothesis not found.")
    hypothesis.verification_status = payload.verification_status
    hypothesis.actual_outcome = payload.actual_outcome
    hypothesis.verified_at = utc_now()
    hypothesis.updated_at = utc_now()
    await session.commit()
    await session.refresh(hypothesis)
    return HypothesisRead.model_validate(hypothesis)
