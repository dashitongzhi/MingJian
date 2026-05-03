from __future__ import annotations

from datetime import timedelta
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
    AnalysisRequest,
    AnalysisSourceRead,
    CalibrationComputeRequest,
    CalibrationRead,
    DebateTriggerRequest,
    EvidenceGraphRead,
    IngestRunCreate,
    IngestRunRead,
    JarvisRunCreate,
    JarvisRunRead,
    KnowledgeSearchResultRead,
    OpenAIStatusResponse,
    OpenAITestRequest,
    OpenAITestResponse,
    RuleReloadResponse,
    RuntimeQueueHealthRead,
    SimulationRunCreate,
    SimulationRunRead,
    WatchRuleCreate,
    WatchRuleRead,
    WatchRuleTriggerRead,
    WatchRuleUpdate,
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
    WatchRule,
    utc_now,
)
from planagent.api.routes._deps import (
    _datetime_is_future,
    ensure_app_services,
    get_analysis_service,
    get_debate_service,
    get_pipeline_service,
    get_runtime_monitor_service,
    get_simulation_service,
)
from planagent.services.startup import (
    AGENT_STARTUP_PRESET_ID,
    build_startup_kpi_pack,
    ensure_tenant_id,
    load_agent_startup_ingest_payload,
    load_agent_startup_simulation_payload,
)
from planagent.workers.graph import embed_query, search_nodes_sql
from planagent.services.jarvis import JarvisOrchestrator, JarvisTask

router = APIRouter()


# ── Jarvis ───────────────────────────────────────────────────────────────────


def _get_jarvis(request: Request) -> JarvisOrchestrator:
    return JarvisOrchestrator(get_settings(), request.app.state.openai_service, getattr(request.app.state, "event_bus", None))


@router.post("/jarvis/runs", response_model=JarvisRunRead, status_code=201)
async def create_jarvis_run(
    payload: JarvisRunCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> JarvisRunRead:
    orchestrator = _get_jarvis(request)
    task = JarvisTask(task_type=payload.target_type, payload={"run_id": payload.run_id, "target_id": payload.target_id}, run_id=payload.run_id, target_id=payload.target_id, profile_id="plan-agent")
    jarvis_result = await orchestrator.orchestrate(task)
    result = jarvis_result.to_dict()
    if payload.run_id is not None:
        run = await session.get(SimulationRun, payload.run_id)
        if run is not None:
            result["run_status"] = run.status
            result["run_summary"] = run.summary
    record = JarvisRunRecord(run_id=payload.run_id, target_type=payload.target_type, target_id=payload.target_id, status=jarvis_result.status, profile_id="plan-agent", result_payload=result)
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return JarvisRunRead.model_validate(record)


@router.get("/jarvis/profiles")
async def get_jarvis_profiles(request: Request) -> dict[str, Any]:
    return _get_jarvis(request).get_profiles()


@router.post("/jarvis/test")
async def test_jarvis_target(target: str = Query(default="primary"), request: Request = None) -> dict[str, Any]:
    return await _get_jarvis(request).test_target(target)


@router.get("/jarvis/runs", response_model=list[JarvisRunRead])
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


@router.post("/presets/agent-startup/runs", response_model=AgentStartupPresetRunRead, status_code=201)
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


@router.post("/admin/rules/reload", response_model=RuleReloadResponse)
async def reload_rules(request: Request) -> RuleReloadResponse:
    domains, total = request.app.state.rule_registry.reload()
    return RuleReloadResponse(domains=domains, rules_loaded=total)


@router.get("/admin/runtime/queues", response_model=RuntimeQueueHealthRead)
async def runtime_queue_health(
    tenant_id: str | None = None,
    preset_id: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> RuntimeQueueHealthRead:
    service = get_runtime_monitor_service()
    return await service.collect_queue_health(session, tenant_id=tenant_id, preset_id=preset_id)


@router.get("/admin/analysis/cache")
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


@router.get("/admin/openai/status", response_model=OpenAIStatusResponse)
async def openai_status(request: Request) -> OpenAIStatusResponse:
    ensure_app_services(request)
    return request.app.state.openai_service.status()


@router.post("/admin/openai/test", response_model=OpenAITestResponse)
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
    return result


# ── Watch Rules ──────────────────────────────────────────────────────────────


@router.post("/watch/rules", response_model=WatchRuleRead, status_code=201)
async def create_watch_rule(
    payload: WatchRuleCreate,
    session: AsyncSession = Depends(get_session),
) -> WatchRuleRead:
    now = utc_now()
    rule = WatchRule(
        name=payload.name,
        domain_id=payload.domain_id,
        query=payload.query,
        source_types=payload.source_types,
        keywords=payload.keywords,
        exclude_keywords=payload.exclude_keywords,
        entity_tags=payload.entity_tags,
        trigger_threshold=payload.trigger_threshold,
        min_new_evidence_count=payload.min_new_evidence_count,
        importance_threshold=payload.importance_threshold,
        poll_interval_minutes=payload.poll_interval_minutes,
        auto_trigger_simulation=payload.auto_trigger_simulation,
        auto_trigger_debate=payload.auto_trigger_debate,
        tick_count=payload.tick_count,
        incremental_enabled=payload.incremental_enabled,
        force_full_refresh_every_minutes=payload.force_full_refresh_every_minutes,
        change_significance_threshold=payload.change_significance_threshold,
        tenant_id=payload.tenant_id,
        preset_id=payload.preset_id,
        next_poll_at=now,
    )
    session.add(rule)
    await session.commit()
    await session.refresh(rule)
    return WatchRuleRead.model_validate(rule)


@router.get("/watch/rules", response_model=list[WatchRuleRead])
async def list_watch_rules(
    domain_id: str | None = None,
    tenant_id: str | None = None,
    enabled: bool | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> list[WatchRuleRead]:
    query = select(WatchRule).order_by(WatchRule.updated_at.desc())
    if domain_id is not None:
        query = query.where(WatchRule.domain_id == domain_id)
    if tenant_id is not None:
        query = query.where(WatchRule.tenant_id == tenant_id)
    if enabled is not None:
        query = query.where(WatchRule.enabled == enabled)
    rules = list((await session.scalars(query.limit(limit))).all())
    return [WatchRuleRead.model_validate(r) for r in rules]


@router.get("/admin/watch-rules", response_model=list[WatchRuleRead], include_in_schema=False)
@router.get("/watch-rules", response_model=list[WatchRuleRead], include_in_schema=False)
async def list_watch_rules_alias(
    domain_id: str | None = None,
    tenant_id: str | None = None,
    enabled: bool | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> list[WatchRuleRead]:
    """Compatibility alias for the legacy /admin/watch-rules frontend path."""
    return await list_watch_rules(
        domain_id=domain_id,
        tenant_id=tenant_id,
        enabled=enabled,
        limit=limit,
        session=session,
    )


@router.get("/watch/rules/{rule_id}", response_model=WatchRuleRead)
async def get_watch_rule(
    rule_id: str,
    session: AsyncSession = Depends(get_session),
) -> WatchRuleRead:
    rule = await session.get(WatchRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Watch rule not found.")
    return WatchRuleRead.model_validate(rule)


@router.get("/admin/watch-rules/{rule_id}", response_model=WatchRuleRead, include_in_schema=False)
@router.get("/watch-rules/{rule_id}", response_model=WatchRuleRead, include_in_schema=False)
async def get_watch_rule_alias(
    rule_id: str,
    session: AsyncSession = Depends(get_session),
) -> WatchRuleRead:
    """Compatibility alias for the legacy /admin/watch-rules/{id} frontend path."""
    return await get_watch_rule(rule_id=rule_id, session=session)


@router.patch("/watch/rules/{rule_id}", response_model=WatchRuleRead)
async def update_watch_rule(
    rule_id: str,
    payload: WatchRuleUpdate,
    session: AsyncSession = Depends(get_session),
) -> WatchRuleRead:
    rule = await session.get(WatchRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Watch rule not found.")
    for field_name, value in payload.model_dump(exclude_unset=True).items():
        setattr(rule, field_name, value)
    await session.commit()
    await session.refresh(rule)
    return WatchRuleRead.model_validate(rule)


@router.delete("/watch/rules/{rule_id}", status_code=204)
async def delete_watch_rule(
    rule_id: str,
    session: AsyncSession = Depends(get_session),
) -> None:
    rule = await session.get(WatchRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Watch rule not found.")
    await session.delete(rule)
    await session.commit()


@router.post("/watch/rules/{rule_id}/trigger", response_model=WatchRuleTriggerRead)
async def trigger_watch_rule(
    rule_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> WatchRuleTriggerRead:
    rule = await session.get(WatchRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Watch rule not found.")

    now = utc_now()
    rule.poll_attempts += 1
    rule.lease_owner = "api-trigger"
    rule.lease_expires_at = now

    try:
        analysis_service = get_analysis_service(request)
        analysis_request = AnalysisRequest(
            content=rule.query,
            domain_id=rule.domain_id,
            auto_fetch_news=True,
            include_google_news="google_news" in rule.source_types,
            include_reddit="reddit" in rule.source_types,
            include_hacker_news="hacker_news" in rule.source_types,
            include_github="github" in rule.source_types,
            include_rss_feeds="rss" in rule.source_types,
            include_gdelt="gdelt" in rule.source_types,
            include_weather="weather" in rule.source_types,
            include_aviation="aviation" in rule.source_types,
            include_x="x" in rule.source_types,
            source_types=rule.source_types,
        )
        analysis = await analysis_service.analyze(analysis_request)
        for step in analysis.reasoning_steps:
            if step.stage == "source_complete":
                await analysis_service.record_source_success(session, _source_type_from_step(step.message))
            elif step.stage == "source_error":
                await analysis_service.record_source_failure(
                    session,
                    _source_type_from_step(step.message),
                    step.detail or step.message,
                )

        items = [
            {
                "source_type": "analyst_note",
                "source_url": f"https://local.planagent/watch/{rule.id}",
                "title": rule.name,
                "content_text": rule.query,
                "source_metadata": {"origin": "watch_rule", "rule_id": rule.id},
            }
        ]
        qualified_sources = _qualified_watch_sources(rule, analysis.sources)
        for source in qualified_sources:
            items.append(
                {
                    "source_type": source.source_type,
                    "source_url": source.url,
                    "title": source.title,
                    "content_text": source.summary,
                    "source_metadata": {
                        "origin": "watch_rule_source",
                        "importance_score": _watch_source_score(rule, source),
                        **source.metadata,
                    },
                }
            )

        pipeline_service = get_pipeline_service(request)
        ingest_run = await pipeline_service.create_ingest_run(
            session,
            IngestRunCreate(
                requested_by=f"watch-rule:{rule.id}",
                tenant_id=rule.tenant_id,
                preset_id=rule.preset_id,
                items=items,
            ),
        )

        simulation_run_id = None
        debate_id = None

        threshold_met = _watch_threshold_met(rule, qualified_sources)
        if rule.auto_trigger_simulation and threshold_met:
            sim_service = get_simulation_service(request)

            if rule.domain_id == "military":
                force_name = rule.query[:60]
                force_id = rule.query[:40].lower().replace(" ", "-")
                sim_payload = SimulationRunCreate(
                    domain_id="military",
                    force_id=force_id,
                    force_name=force_name,
                    theater="contested-theater",
                    tick_count=rule.tick_count or None,
                    tenant_id=rule.tenant_id,
                    preset_id=rule.preset_id,
                )
            else:
                company_name = rule.query[:60]
                company_id = rule.query[:40].lower().replace(" ", "-")
                sim_payload = SimulationRunCreate(
                    domain_id="corporate",
                    company_id=company_id,
                    company_name=company_name,
                    market="ai",
                    tick_count=rule.tick_count or None,
                    tenant_id=rule.tenant_id,
                    preset_id=rule.preset_id,
                )
            sim_run = await sim_service.create_simulation_run(session, sim_payload)
            simulation_run_id = sim_run.id

            if rule.auto_trigger_debate and simulation_run_id is not None:
                debate_service = get_debate_service(request)
                debate = await debate_service.trigger_debate(
                    session,
                    DebateTriggerRequest(
                        run_id=simulation_run_id,
                        topic=f"Should the posture for {rule.query} be adjusted?",
                        trigger_type="pivot_decision",
                        target_type="run",
                    ),
                )
                debate_id = debate.id

        rule.last_poll_at = now
        rule.last_poll_error = None
        rule.lease_owner = None
        rule.lease_expires_at = None
        rule.next_poll_at = now + timedelta(minutes=rule.poll_interval_minutes)
        await session.commit()

        return WatchRuleTriggerRead(
            rule_id=rule.id,
            rule_name=rule.name,
            status="completed",
            ingest_run_id=ingest_run.id,
            sources_fetched=len(analysis.sources),
            simulation_run_id=simulation_run_id,
            debate_id=debate_id,
        )
    except Exception as exc:
        rule.last_poll_error = f"{type(exc).__name__}: {' '.join(str(exc).split())[:300]}"
        rule.lease_owner = None
        rule.lease_expires_at = None
        await session.commit()
        return WatchRuleTriggerRead(
            rule_id=rule.id,
            rule_name=rule.name,
            status="failed",
            error=rule.last_poll_error,
        )


def _source_type_from_step(message: str) -> str:
    lowered = message.lower()
    if "google" in lowered:
        return "google_news"
    if "reddit" in lowered:
        return "reddit"
    if "hacker" in lowered:
        return "hacker_news"
    if "github" in lowered:
        return "github"
    if "gdelt" in lowered:
        return "gdelt"
    if "weather" in lowered:
        return "weather"
    if "aviation" in lowered or "opensky" in lowered:
        return "aviation"
    if "rss" in lowered:
        return "rss"
    if "linux.do" in lowered or "linux" in lowered:
        return "linux_do"
    if "xiaohongshu" in lowered:
        return "xiaohongshu"
    if "douyin" in lowered:
        return "douyin"
    if lowered.strip() == "x" or " x." in lowered or " x " in lowered:
        return "x"
    return "unknown"


def _qualified_watch_sources(rule: WatchRule, sources: list[AnalysisSourceRead]) -> list[AnalysisSourceRead]:
    qualified: list[AnalysisSourceRead] = []
    for source in sources:
        score = _watch_source_score(rule, source)
        if score >= float(rule.importance_threshold or 0.0):
            qualified.append(source)
    return qualified


def _watch_threshold_met(rule: WatchRule, sources: list[AnalysisSourceRead]) -> bool:
    if len(sources) < int(rule.min_new_evidence_count or 0):
        return False
    if not sources:
        return float(rule.trigger_threshold or 0.0) <= 0.0
    top_score = max(_watch_source_score(rule, source) for source in sources)
    return top_score >= float(rule.trigger_threshold or 0.0)


def _watch_source_score(rule: WatchRule, source: AnalysisSourceRead) -> float:
    haystack = f"{source.title} {source.summary}".lower()
    exclude_terms = [term.lower() for term in (rule.exclude_keywords or []) if term]
    if any(term in haystack for term in exclude_terms):
        return 0.0
    keywords = [term.lower() for term in (rule.keywords or []) if term]
    entity_tags = [term.lower() for term in (rule.entity_tags or []) if term]
    terms = keywords or entity_tags or [token.lower() for token in rule.query.split()[:6] if token]
    matched = sum(1 for term in terms if term and term in haystack)
    score = 0.35 + min(matched * 0.18, 0.45)
    engagement = source.metadata.get("engagement", {}) if isinstance(source.metadata, dict) else {}
    if isinstance(engagement, dict) and any(value for value in engagement.values() if isinstance(value, (int, float))):
        score += 0.1
    if source.published_at:
        score += 0.1
    return round(max(0.0, min(score, 1.0)), 4)


# ── Sources ──────────────────────────────────────────────────────────────────


@router.get("/sources/health")
async def list_source_health(
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    records = list(
        (
            await session.scalars(select(SourceHealth).order_by(SourceHealth.updated_at.desc()))
        ).all()
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


@router.get("/sources/snapshots")
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


@router.get("/knowledge/graph", response_model=EvidenceGraphRead)
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
            {
                "node_id": node.node_key,
                "label": node.label,
                "node_type": node.node_type,
                "metadata": {
                    **(node.node_metadata or {}),
                    "source_table": node.source_table,
                    "source_id": node.source_id,
                },
            }
            for node in nodes
        ],
        edges=[
            {
                "source_id": edge.source_node_key,
                "target_id": edge.target_node_key,
                "relation_type": edge.relation_type,
                "metadata": edge.edge_metadata or {},
            }
            for edge in edges
        ],
    )


@router.get("/knowledge/search", response_model=list[KnowledgeSearchResultRead])
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


@router.get("/hypotheses/scoreboard")
async def hypotheses_scoreboard(
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    """预测校准总览（scoreboard）"""
    from sqlalchemy import func as sa_func

    total = await session.scalar(select(sa_func.count(Hypothesis.id)))
    total = total or 0

    confirmed = await session.scalar(
        select(sa_func.count(Hypothesis.id)).where(
            Hypothesis.verification_status == "CONFIRMED"
        )
    )
    refuted = await session.scalar(
        select(sa_func.count(Hypothesis.id)).where(
            Hypothesis.verification_status == "REFUTED"
        )
    )
    pending = await session.scalar(
        select(sa_func.count(Hypothesis.id)).where(
            Hypothesis.verification_status == "PENDING"
        )
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


@router.get("/calibration", response_model=list[CalibrationRead])
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


@router.post("/calibration/compute", response_model=CalibrationRead, status_code=201)
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
                option_counts[h.decision_option_id] = option_counts.get(h.decision_option_id, 0.0) + 1.0
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
