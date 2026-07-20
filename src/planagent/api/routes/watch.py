from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from planagent.api.routes._deps import (
    get_analysis_service,
    get_debate_workflow,
    get_pipeline_service,
    get_simulation_service,
)
from planagent.config import get_settings
from planagent.db import get_session
from planagent.domain.api import (
    IngestRunCreate,
    SourceCursorStateRead,
    WatchRuleCreate,
    WatchRuleRead,
    WatchRuleTriggerRead,
    WatchRuleUpdate,
)
from planagent.domain.models import SourceCursorState, WatchRule, utc_now
from planagent.services.community_monitoring import (
    monitoring_window_expired,
    next_poll_within_window,
)
from planagent.services.recommendations import RecommendationVersionService
from planagent.services.source_state import SourceStateService
from planagent.services.watch_evidence import (
    build_watch_analysis_request,
    build_watch_ingest_items,
    qualified_watch_sources,
    record_watch_source_health,
    watch_recommendation_summary,
    watch_threshold_met,
)
from planagent.services.watch_execution import (
    WatchExecutionLeaseLostError,
    WatchExecutionLeaseManager,
    WatchExecutionService,
    new_watch_execution_owner,
)

logger = logging.getLogger(__name__)

router = APIRouter()


async def _seed_watch_rule_sources(session: AsyncSession, rule: WatchRule) -> None:
    await SourceStateService(get_settings()).seed_watch_rule_sources(
        session,
        watch_rule_id=rule.id,
        query=rule.query,
        source_types=rule.source_types or [],
        tenant_id=rule.tenant_id,
        preset_id=rule.preset_id,
    )


@router.post("/watch/rules", response_model=WatchRuleRead, status_code=201)
async def create_watch_rule(
    payload: WatchRuleCreate,
    session: AsyncSession = Depends(get_session),
) -> WatchRuleRead:
    now = utc_now()
    rule = WatchRule(
        session_id=payload.session_id,
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
    await session.flush()
    await _seed_watch_rule_sources(session, rule)
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


@router.get("/watch/rules/{rule_id}/sources", response_model=list[SourceCursorStateRead])
async def list_watch_rule_sources(
    rule_id: str,
    session: AsyncSession = Depends(get_session),
) -> list[SourceCursorStateRead]:
    rule = await session.get(WatchRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Watch rule not found.")
    rows = list(
        (
            await session.scalars(
                select(SourceCursorState)
                .where(SourceCursorState.watch_rule_id == rule_id)
                .order_by(SourceCursorState.source_type.asc(), SourceCursorState.updated_at.desc())
            )
        ).all()
    )
    return [SourceCursorStateRead.model_validate(row) for row in rows]


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
    updates = payload.model_dump(exclude_unset=True)
    for field_name, value in updates.items():
        setattr(rule, field_name, value)
    if "source_types" in updates:
        await _seed_watch_rule_sources(session, rule)
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
    if monitoring_window_expired(rule.created_at, now=now):
        rule.enabled = False
        rule.next_poll_at = None
        rule.lease_owner = None
        rule.lease_expires_at = None
        await session.commit()
        raise HTTPException(
            status_code=409,
            detail="Community monitoring window expired after 24 hours",
        )

    execution_owner = new_watch_execution_owner("api-trigger")
    lease_manager = WatchExecutionLeaseManager(get_settings())
    failure_enabled = rule.enabled
    failure_next_poll_at = rule.next_poll_at
    if not await lease_manager.claim_manual(session, rule_id, execution_owner, now):
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Watch rule is already being processed",
        )
    await session.commit()
    await session.refresh(rule)

    try:
        analysis_service = get_analysis_service(request)
        analysis_request = build_watch_analysis_request(rule)
        analysis = await analysis_service.analyze(analysis_request)
        await record_watch_source_health(
            session,
            analysis_service,
            analysis.reasoning_steps,
        )

        qualified_sources = qualified_watch_sources(rule, analysis.sources)
        items = build_watch_ingest_items(rule, qualified_sources)

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

        threshold_met = watch_threshold_met(rule, qualified_sources)
        action_result = await WatchExecutionService(
            get_simulation_service(request),
            get_debate_workflow(request),
        ).run_actions(
            session,
            rule,
            should_run=threshold_met,
        )
        simulation_run_id = action_result.simulation_run_id
        debate_id = action_result.debate_id

        next_poll_at = next_poll_within_window(
            rule.created_at,
            rule.poll_interval_minutes,
            now=now,
        )
        recommendation_version_id = None
        if rule.session_id is not None:
            recommendation_service = RecommendationVersionService()
            recommendation = await recommendation_service.create_version(
                session,
                session_id=rule.session_id,
                watch_rule_id=rule.id,
                tenant_id=rule.tenant_id,
                preset_id=rule.preset_id,
                trigger_type="manual_trigger",
                significance="none",
                recommendation_summary=watch_recommendation_summary(
                    analysis.recommendations,
                    analysis.summary,
                    debate_id,
                    simulation_run_id,
                ),
                result_payload={
                    "kind": "watch_manual_trigger",
                    "analysis": analysis.model_dump(mode="json"),
                    "sources_fetched": len(analysis.sources),
                    "threshold_met": threshold_met,
                },
                source_snapshot=await recommendation_service.source_snapshot(
                    session,
                    watch_rule_id=rule.id,
                ),
                ingest_run_id=ingest_run.id,
                simulation_run_id=simulation_run_id,
                debate_id=debate_id,
            )
            recommendation_version_id = recommendation.id
        if not await lease_manager.complete(
            session,
            rule_id,
            execution_owner,
            completed_at=now,
            next_poll_at=next_poll_at,
        ):
            raise WatchExecutionLeaseLostError(rule_id)
        await session.commit()

        return WatchRuleTriggerRead(
            rule_id=rule.id,
            rule_name=rule.name,
            status="completed",
            ingest_run_id=ingest_run.id,
            sources_fetched=len(analysis.sources),
            simulation_run_id=simulation_run_id,
            debate_id=debate_id,
            recommendation_version_id=recommendation_version_id,
        )
    except WatchExecutionLeaseLostError as exc:
        await session.rollback()
        logger.warning("Watch rule execution lease lost: rule_id=%s", rule_id)
        raise HTTPException(
            status_code=409,
            detail="Watch rule execution lease was lost",
        ) from exc
    except Exception as exc:
        await session.rollback()
        logger.error(
            "Watch rule processing failed: rule_id=%s error_type=%s",
            rule_id,
            type(exc).__name__,
        )
        await lease_manager.fail(
            session,
            rule_id,
            execution_owner,
            error="Watch rule processing failed",
            failed_at=utc_now(),
            enabled=failure_enabled,
            next_poll_at=failure_next_poll_at,
        )
        await session.commit()
        raise HTTPException(
            status_code=502,
            detail="Watch rule processing failed",
        ) from exc
