from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from planagent.config import get_settings
from planagent.db import get_session
from planagent.domain.api import (
    AgentStartupPresetRunCreate,
    AgentStartupPresetRunRead,
    AgentStartupPresetScenarioRead,
    CalibrationComputeRequest,
    CalibrationRead,
    EvidenceGraphEdgeRead,
    EvidenceGraphNodeRead,
    EvidenceGraphRead,
    IngestRunCreate,
    IngestRunRead,
    JarvisRunCreate,
    JarvisRunRead,
    KnowledgeSearchResultRead,
    OpenAIStatusResponse,
    OpenAITestRequest,
    OpenAITestResponse,
    PlatformTopologyRead,
    RuleReloadResponse,
    RuntimeQueueHealthRead,
    SimulationRunCreate,
    SimulationRunRead,
)
from planagent.domain.models import (
    AnalysisCacheRecord,
    CalibrationRecord,
    EvidenceItem,
    Hypothesis,
    JarvisRunRecord,
    KnowledgeGraphEdge,
    KnowledgeGraphNode,
    NormalizedItem,
    RawSourceItem,
    SimulationRun,
    SourceHealth,
    SourceSnapshot,
    StateSnapshotRecord,
    utc_now,
)

from planagent.api.routes._deps import (
    _datetime_is_future,
    ensure_app_services,
    get_platform_topology_service,
    get_pipeline_service,
    get_runtime_monitor_service,
    get_simulation_service,
)
from planagent.api.routes.auth import require_role
from planagent.api.edition import require_prediction_calibration
from planagent.services.startup import (
    AGENT_STARTUP_PRESET_ID,
    build_startup_kpi_pack,
    ensure_tenant_id,
    load_agent_startup_ingest_payload,
    load_agent_startup_simulation_payload,
)
from planagent.services.auth import UserRole
from planagent.workers.graph import embed_query, search_nodes_sql
from planagent.services.jarvis import JarvisOrchestrator, JarvisTask

router = APIRouter()
_ADMIN_ONLY = [Depends(require_role(UserRole.ADMIN))]


# ── Jarvis ───────────────────────────────────────────────────────────────────


def _get_jarvis(request: Request) -> JarvisOrchestrator:
    return JarvisOrchestrator(
        get_settings(),
        request.app.state.openai_service,
        getattr(request.app.state, "event_bus", None),
    )


@router.post(
    "/jarvis/runs",
    response_model=JarvisRunRead,
    status_code=201,
    dependencies=_ADMIN_ONLY,
)
async def create_jarvis_run(
    payload: JarvisRunCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> JarvisRunRead:
    orchestrator = _get_jarvis(request)
    run = await session.get(SimulationRun, payload.run_id) if payload.run_id is not None else None
    task_payload: dict[str, Any] = {
        "run_id": payload.run_id,
        "target_id": payload.target_id,
        "prompt": payload.prompt,
    }
    if run is not None:
        task_payload["run_status"] = run.status
        task_payload["run_summary"] = run.summary
    task = JarvisTask(
        task_type=payload.target_type,
        payload=task_payload,
        run_id=payload.run_id,
        target_id=payload.target_id,
        profile_id="plan-agent",
    )
    jarvis_result = await orchestrator.orchestrate(task)
    result = jarvis_result.to_dict()
    if run is not None:
        result["run_status"] = run.status
        result["run_summary"] = run.summary
    record = JarvisRunRecord(
        run_id=payload.run_id,
        target_type=payload.target_type,
        target_id=payload.target_id,
        status=jarvis_result.status,
        profile_id="plan-agent",
        result_payload=result,
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return JarvisRunRead.model_validate(record)


@router.get("/jarvis/profiles", dependencies=_ADMIN_ONLY)
async def get_jarvis_profiles(request: Request) -> dict[str, Any]:
    return _get_jarvis(request).get_profiles()


@router.post("/jarvis/test", response_model=None, dependencies=_ADMIN_ONLY)
async def test_jarvis_target(
    target: str = Query(default="primary"), request: Request = None
) -> dict[str, Any]:
    assert request is not None  # FastAPI 保证注入 request 对象
    return await _get_jarvis(request).test_target(target)


@router.get("/jarvis/runs", response_model=list[JarvisRunRead], dependencies=_ADMIN_ONLY)
async def list_jarvis_runs(
    run_id: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> list[JarvisRunRead]:
    query = select(JarvisRunRecord).order_by(JarvisRunRecord.created_at.desc())
    if run_id is not None:
        query = query.where(JarvisRunRecord.run_id == run_id)
    records = list((await session.scalars(query.limit(limit))).all())
    return [JarvisRunRead.model_validate(item) for item in records]


# ── Agent Startup Presets ────────────────────────────────────────────────────


@router.post(
    "/presets/agent-startup/runs",
    response_model=AgentStartupPresetRunRead,
    status_code=201,
    dependencies=_ADMIN_ONLY,
)
async def create_agent_startup_preset_runs(
    payload: AgentStartupPresetRunCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> AgentStartupPresetRunRead:
    pipeline_service = get_pipeline_service(request)
    simulation_service = get_simulation_service(request)
    tenant_id = ensure_tenant_id(payload.tenant_id)

    ingest_body = load_agent_startup_ingest_payload()
    ingest_run = await pipeline_service.create_ingest_run(
        session,
        IngestRunCreate(
            requested_by=payload.requested_by,
            tenant_id=tenant_id,
            preset_id=AGENT_STARTUP_PRESET_ID,
            items=ingest_body.get("items", []),
        ),
    )

    scenario_reads: list[AgentStartupPresetScenarioRead] = []
    for scenario_name in payload.scenarios:
        simulation_body = load_agent_startup_simulation_payload(scenario_name)
        run = await simulation_service.create_simulation_run(
            session,
            SimulationRunCreate(
                **simulation_body,
                tenant_id=tenant_id,
                preset_id=AGENT_STARTUP_PRESET_ID,
            ),
        )
        state_snapshots = list(
            (
                await session.scalars(
                    select(StateSnapshotRecord)
                    .where(StateSnapshotRecord.run_id == run.id)
                    .order_by(StateSnapshotRecord.tick.asc())
                )
            ).all()
        )
        startup_kpi_pack = build_startup_kpi_pack(
            run,
            state_snapshots[0].state if state_snapshots else {},
            state_snapshots[-1].state if state_snapshots else {},
            run.summary.get("matched_rules", []),
        )
        scenario_reads.append(
            AgentStartupPresetScenarioRead(
                scenario=scenario_name,
                company_id=simulation_body["company_id"],
                run=SimulationRunRead.model_validate(run),
                startup_kpi_pack=startup_kpi_pack,
                report_id=run.summary.get("report_id"),
                report_path=f"/companies/{simulation_body['company_id']}/reports/latest?tenant_id={tenant_id}",
                decision_trace_path=f"/runs/{run.id}/decision-trace",
            )
        )

    return AgentStartupPresetRunRead(
        preset_id=AGENT_STARTUP_PRESET_ID,
        tenant_id=tenant_id,
        ingest_run=IngestRunRead.model_validate(ingest_run),
        scenarios=scenario_reads,
    )


# ── Admin ────────────────────────────────────────────────────────────────────


@router.post("/admin/rules/reload", response_model=RuleReloadResponse, dependencies=_ADMIN_ONLY)
async def reload_rules(request: Request) -> RuleReloadResponse:
    domains, total = request.app.state.rule_registry.reload()
    return RuleReloadResponse(domains=domains, rules_loaded=total)


@router.get(
    "/admin/runtime/queues",
    response_model=RuntimeQueueHealthRead,
    dependencies=_ADMIN_ONLY,
)
async def runtime_queue_health(
    tenant_id: str | None = None,
    preset_id: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> RuntimeQueueHealthRead:
    service = get_runtime_monitor_service()
    return await service.collect_queue_health(session, tenant_id=tenant_id, preset_id=preset_id)


@router.get(
    "/admin/runtime/platform-topology",
    response_model=PlatformTopologyRead,
    dependencies=_ADMIN_ONLY,
)
async def runtime_platform_topology(request: Request) -> PlatformTopologyRead:
    service = get_platform_topology_service(request)
    return await service.collect()


@router.get("/admin/analysis/cache", dependencies=_ADMIN_ONLY)
async def analysis_cache_status(
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    now = utc_now()
    total = int((await session.scalar(select(func.count()).select_from(AnalysisCacheRecord))) or 0)
    active = int(
        (
            await session.scalar(
                select(func.count())
                .select_from(AnalysisCacheRecord)
                .where(AnalysisCacheRecord.expires_at > now)
            )
        )
        or 0
    )
    records = list(
        (
            await session.scalars(
                select(AnalysisCacheRecord)
                .order_by(AnalysisCacheRecord.created_at.desc())
                .limit(limit)
            )
        ).all()
    )
    return {
        "enabled": get_settings().analysis_cache_enabled,
        "ttl_seconds": get_settings().api_cache_ttl_seconds,
        "total_records": total,
        "active_records": active,
        "records": [
            {
                "cache_key": record.cache_key,
                "domain_id": record.domain_id,
                "query": record.query,
                "created_at": record.created_at,
                "expires_at": record.expires_at,
                "active": _datetime_is_future(record.expires_at, now),
            }
            for record in records
        ],
    }


@router.get(
    "/admin/openai/status",
    response_model=OpenAIStatusResponse,
    dependencies=_ADMIN_ONLY,
)
async def openai_status(request: Request) -> OpenAIStatusResponse:
    ensure_app_services(request)
    return request.app.state.openai_service.status()  # type: ignore[no-any-return]  # app.state 动态属性


@router.post(
    "/admin/openai/test",
    response_model=OpenAITestResponse,
    dependencies=_ADMIN_ONLY,
)
async def openai_test(
    payload: OpenAITestRequest,
    request: Request,
) -> OpenAITestResponse:
    ensure_app_services(request)
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
    return result  # type: ignore[no-any-return]  # openai_service 返回 Any


# ── Sources ──────────────────────────────────────────────────────────────────


@router.get("/sources/health", dependencies=_ADMIN_ONLY)
async def list_source_health(
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    records = list(
        (await session.scalars(select(SourceHealth).order_by(SourceHealth.updated_at.desc()))).all()
    )
    return [
        {
            "source_type": item.source_type,
            "status": item.status,
            "consecutive_failures": item.consecutive_failures,
            "last_error": item.last_error,
            "last_success_at": item.last_success_at,
            "last_failure_at": item.last_failure_at,
            "updated_at": item.updated_at,
        }
        for item in records
    ]


@router.get("/sources/snapshots", dependencies=_ADMIN_ONLY)
async def list_source_snapshots(
    tenant_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    query = select(SourceSnapshot).order_by(SourceSnapshot.created_at.desc())
    if tenant_id is not None:
        query = query.where(SourceSnapshot.tenant_id == tenant_id)
    snapshots = list((await session.scalars(query.limit(limit))).all())
    return [
        {
            "id": item.id,
            "raw_source_item_id": item.raw_source_item_id,
            "tenant_id": item.tenant_id,
            "preset_id": item.preset_id,
            "storage_backend": item.storage_backend,
            "storage_uri": item.storage_uri,
            "content_sha256": item.content_sha256,
            "byte_size": item.byte_size,
            "created_at": item.created_at,
        }
        for item in snapshots
    ]


# ── Knowledge Graph ──────────────────────────────────────────────────────────


@router.get("/knowledge/graph", response_model=EvidenceGraphRead, dependencies=_ADMIN_ONLY)
async def get_knowledge_graph(
    tenant_id: str | None = None,
    preset_id: str | None = None,
    node_type: str | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
) -> EvidenceGraphRead:
    node_query = select(KnowledgeGraphNode).order_by(KnowledgeGraphNode.updated_at.desc())
    if tenant_id is not None:
        node_query = node_query.where(KnowledgeGraphNode.tenant_id == tenant_id)
    if preset_id is not None:
        node_query = node_query.where(KnowledgeGraphNode.preset_id == preset_id)
    if node_type is not None:
        node_query = node_query.where(KnowledgeGraphNode.node_type == node_type)

    nodes = list((await session.scalars(node_query.limit(limit))).all())
    node_keys = {node.node_key for node in nodes}
    edge_query = select(KnowledgeGraphEdge)
    if tenant_id is not None:
        edge_query = edge_query.where(KnowledgeGraphEdge.tenant_id == tenant_id)
    if preset_id is not None:
        edge_query = edge_query.where(KnowledgeGraphEdge.preset_id == preset_id)
    if node_keys:
        edge_query = edge_query.where(
            KnowledgeGraphEdge.source_node_key.in_(node_keys),
            KnowledgeGraphEdge.target_node_key.in_(node_keys),
        )
    edges = list((await session.scalars(edge_query.limit(limit * 3))).all()) if node_keys else []

    return EvidenceGraphRead(
        nodes=[
            EvidenceGraphNodeRead(
                node_id=node.node_key,
                label=node.label,
                node_type=node.node_type,
                metadata={
                    **(node.node_metadata or {}),
                    "source_table": node.source_table,
                    "source_id": node.source_id,
                },
            )
            for node in nodes
        ],
        edges=[
            EvidenceGraphEdgeRead(
                source_id=edge.source_node_key,
                target_id=edge.target_node_key,
                relation_type=edge.relation_type,
                metadata=edge.edge_metadata or {},
            )
            for edge in edges
        ],
    )


@router.get(
    "/knowledge/search",
    response_model=list[KnowledgeSearchResultRead],
    dependencies=_ADMIN_ONLY,
)
async def search_knowledge_graph(
    q: str = Query(min_length=1),
    tenant_id: str | None = None,
    limit: int = Query(default=10, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
) -> list[KnowledgeSearchResultRead]:
    query_vector = embed_query(q, get_settings().graph_embedding_dimensions)
    rows = await search_nodes_sql(session, query_vector, tenant_id, limit)
    return [KnowledgeSearchResultRead.model_validate(row) for row in rows]


# ── Hypotheses Scoreboard ────────────────────────────────────────────────────


@router.get(
    "/hypotheses/scoreboard",
    dependencies=[Depends(require_prediction_calibration), *_ADMIN_ONLY],
)
async def hypotheses_scoreboard(
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    """预测校准总览（scoreboard）"""
    from sqlalchemy import func as sa_func

    total = await session.scalar(select(sa_func.count(Hypothesis.id)))
    total = total or 0

    confirmed = await session.scalar(
        select(sa_func.count(Hypothesis.id)).where(Hypothesis.verification_status == "CONFIRMED")
    )
    refuted = await session.scalar(
        select(sa_func.count(Hypothesis.id)).where(Hypothesis.verification_status == "REFUTED")
    )
    pending = await session.scalar(
        select(sa_func.count(Hypothesis.id)).where(Hypothesis.verification_status == "PENDING")
    )
    confirmed = confirmed or 0
    refuted = refuted or 0
    pending = pending or 0
    verified = confirmed + refuted
    accuracy = round(confirmed / verified, 4) if verified > 0 else 0.0

    return {
        "total_hypotheses": total,
        "confirmed": confirmed,
        "refuted": refuted,
        "pending": pending,
        "accuracy": accuracy,
        "brier_score": None,
        "human_baseline_accuracy": None,
        "lift_over_human_baseline": None,
    }


# ── Calibration ──────────────────────────────────────────────────────────────


@router.get(
    "/calibration",
    response_model=list[CalibrationRead],
    dependencies=[Depends(require_prediction_calibration), *_ADMIN_ONLY],
)
async def list_calibration(
    domain_id: str | None = None,
    tenant_id: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    query = select(CalibrationRecord).order_by(CalibrationRecord.created_at.desc())
    if domain_id is not None:
        query = query.where(CalibrationRecord.domain_id == domain_id)
    if tenant_id is not None:
        query = query.where(CalibrationRecord.tenant_id == tenant_id)
    records = list((await session.scalars(query.limit(20))).all())
    return [CalibrationRead.model_validate(r) for r in records]


@router.post(
    "/calibration/compute",
    response_model=CalibrationRead,
    status_code=201,
    dependencies=[Depends(require_prediction_calibration), *_ADMIN_ONLY],
)
async def compute_calibration(
    payload: CalibrationComputeRequest,
    session: AsyncSession = Depends(get_session),
):
    from planagent.domain.models import DecisionRecordRecord

    now = utc_now()
    query = (
        select(Hypothesis)
        .join(SimulationRun, Hypothesis.run_id == SimulationRun.id)
        .where(Hypothesis.prediction != "")
        .where(SimulationRun.domain_id == payload.domain_id)
    )
    if payload.tenant_id is not None:
        query = query.where(Hypothesis.tenant_id == payload.tenant_id)
    hypotheses = list((await session.scalars(query)).all())

    total = len(hypotheses)
    confirmed = sum(1 for h in hypotheses if h.verification_status == "CONFIRMED")
    refuted = sum(1 for h in hypotheses if h.verification_status == "REFUTED")
    partial = sum(1 for h in hypotheses if h.verification_status == "PARTIAL")
    pending = sum(1 for h in hypotheses if h.verification_status == "PENDING")
    verified = confirmed + refuted + partial
    calibration_score = round(confirmed / verified, 4) if verified > 0 else 0.0

    rule_accuracy: dict[str, float] = {}
    decision_option_accuracy: dict[str, float] = {}
    source_type_accuracy: dict[str, float] = {}
    if verified > 0:
        verified_run_ids = sorted(
            {
                h.run_id
                for h in hypotheses
                if h.verification_status in {"CONFIRMED", "REFUTED", "PARTIAL"}
            }
        )
        decisions_by_run: dict[str, list[DecisionRecordRecord]] = {}
        if verified_run_ids:
            decision_rows = list(
                (
                    await session.scalars(
                        select(DecisionRecordRecord).where(
                            DecisionRecordRecord.run_id.in_(verified_run_ids)
                        )
                    )
                ).all()
            )
            for decision in decision_rows:
                decisions_by_run.setdefault(decision.run_id, []).append(decision)

        for h in hypotheses:
            if h.verification_status == "PENDING":
                continue
            decisions = decisions_by_run.get(h.run_id, [])
            for d in decisions:
                for rule_id in d.policy_rule_ids or []:
                    if rule_id not in rule_accuracy:
                        rule_accuracy[rule_id] = 0.0
                    if h.verification_status in ("CONFIRMED", "PARTIAL"):
                        rule_accuracy[rule_id] += 1.0
        rule_count = {rule_id: 0.0 for rule_id in rule_accuracy}
        for h in hypotheses:
            if h.verification_status == "PENDING":
                continue
            decisions = decisions_by_run.get(h.run_id, [])
            for d in decisions:
                for rule_id in d.policy_rule_ids or []:
                    if rule_id in rule_count:
                        rule_count[rule_id] += 1.0
        rule_accuracy = {
            rid: round(rule_accuracy[rid] / cnt, 4) if cnt > 0 else 0.0
            for rid, cnt in rule_count.items()
        }
        option_counts: dict[str, float] = {}
        option_hits: dict[str, float] = {}
        source_counts: dict[str, float] = {}
        source_hits: dict[str, float] = {}
        evidence_ids = sorted(
            {
                evidence_id
                for decisions in decisions_by_run.values()
                for decision in decisions
                for evidence_id in (decision.evidence_ids or [])
            }
        )
        evidence_source_types: dict[str, str] = {}
        if evidence_ids:
            evidence_rows = list(
                (
                    await session.execute(
                        select(EvidenceItem.id, RawSourceItem.source_type)
                        .join(NormalizedItem, EvidenceItem.normalized_item_id == NormalizedItem.id)
                        .join(RawSourceItem, NormalizedItem.raw_source_item_id == RawSourceItem.id)
                        .where(EvidenceItem.id.in_(evidence_ids))
                    )
                ).all()
            )
            evidence_source_types = {row[0]: row[1] for row in evidence_rows}
        for h in hypotheses:
            if h.verification_status == "PENDING":
                continue
            hit = 1.0 if h.verification_status in {"CONFIRMED", "PARTIAL"} else 0.0
            if h.decision_option_id:
                option_counts[h.decision_option_id] = (
                    option_counts.get(h.decision_option_id, 0.0) + 1.0
                )
                option_hits[h.decision_option_id] = option_hits.get(h.decision_option_id, 0.0) + hit
            for d in decisions_by_run.get(h.run_id, []):
                for evidence_id in d.evidence_ids or []:
                    source_type = evidence_source_types.get(evidence_id)
                    if not source_type:
                        continue
                    source_counts[source_type] = source_counts.get(source_type, 0.0) + 1.0
                    source_hits[source_type] = source_hits.get(source_type, 0.0) + hit
        decision_option_accuracy = {
            option_id: round(option_hits.get(option_id, 0.0) / count, 4)
            for option_id, count in option_counts.items()
            if count > 0
        }
        source_type_accuracy = {
            source_type: round(source_hits.get(source_type, 0.0) / count, 4)
            for source_type, count in source_counts.items()
            if count > 0
        }

    record = CalibrationRecord(
        domain_id=payload.domain_id,
        tenant_id=payload.tenant_id,
        period_start=now,
        period_end=now,
        total_hypotheses=total,
        confirmed=confirmed,
        refuted=refuted,
        partial=partial,
        pending=pending,
        calibration_score=calibration_score,
        rule_accuracy={
            "rules": rule_accuracy,
            "decision_options": decision_option_accuracy,
            "source_types": source_type_accuracy,
        },
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return CalibrationRead.model_validate(record)
