from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from planagent.api.routes._deps import ensure_app_services
from planagent.config import get_settings
from planagent.db import get_session
from planagent.domain.api import SourceChangeRecordRead, SourceCursorStateRead
from planagent.domain.enums import EventTopic
from planagent.domain.models import (
    EventArchive,
    EvidenceItem,
    NormalizedItem,
    PredictionEvidenceLink,
    PredictionRevisionJob,
    PredictionSeries,
    PredictionVersion,
    RawSourceItem,
    SourceChangeRecord,
    SourceCursorState,
)
from planagent.services.source_state import SourceStateService

router = APIRouter(tags=["sources"])


@router.get("/sources/states", response_model=list[SourceCursorStateRead])
async def list_source_states(
    watch_rule_id: str | None = None,
    source_type: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[SourceCursorStateRead]:
    """列出数据源游标状态"""
    service = SourceStateService(get_settings())
    states = await service.list_states(
        session,
        watch_rule_id=watch_rule_id,
        source_type=source_type,
    )
    return [SourceCursorStateRead.model_validate(item) for item in states]


@router.get("/sources/changes", response_model=list[SourceChangeRecordRead])
async def list_source_changes(
    watch_rule_id: str | None = None,
    significance: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> list[SourceChangeRecordRead]:
    """列出来源变更记录"""
    query = select(SourceChangeRecord).order_by(SourceChangeRecord.created_at.desc())
    if watch_rule_id is not None:
        query = query.where(SourceChangeRecord.watch_rule_id == watch_rule_id)
    if significance is not None:
        query = query.where(SourceChangeRecord.significance == significance)
    records = list((await session.scalars(query.limit(limit))).all())
    return [SourceChangeRecordRead.model_validate(item) for item in records]


@router.post("/watch/rules/{rule_id}/cursor/reset")
async def reset_cursor(
    rule_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    """重置数据源游标（强制全量重抓）"""
    service = SourceStateService(get_settings())
    reset_count = await service.reset_cursor(session, rule_id)
    return {"status": "ok", "rule_id": rule_id, "reset_count": reset_count}


@router.post("/sources/changes/{change_id}/reanalyze")
async def trigger_reanalyze(
    change_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    """手动触发重分析"""
    change = await session.get(SourceChangeRecord, change_id)
    if change is None:
        raise HTTPException(status_code=404, detail="Source change record not found.")
    state = await session.get(SourceCursorState, change.source_state_id)
    evidence_item_id = await _evidence_item_id_for_change(session, change)
    series = await _candidate_prediction_series(session, change, state)
    job_ids: list[str] = []
    for item in series:
        base_version_id = await _base_version_id(session, item)
        if base_version_id is None:
            continue
        existing = (
            await session.scalars(
                select(PredictionRevisionJob)
                .where(
                    PredictionRevisionJob.series_id == item.id,
                    PredictionRevisionJob.trigger_topic == change.id,
                    PredictionRevisionJob.status.in_(["PENDING", "PROCESSING"]),
                )
                .limit(1)
            )
        ).first()
        if existing is not None:
            job_ids.append(existing.id)
            continue
        trigger_claim_id = change.claim_ids[0] if change.claim_ids else None
        job = PredictionRevisionJob(
            series_id=item.id,
            base_version_id=base_version_id,
            claim_id=trigger_claim_id,
            trigger_claim_id=trigger_claim_id,
            evidence_item_id=evidence_item_id,
            trigger_evidence_item_id=evidence_item_id,
            trigger_topic=change.id,
            status="PENDING",
            reason=f"Manual reanalysis requested for source change {change.id}.",
            job_metadata={
                "trigger_type": "source_change",
                "source_change_id": change.id,
                "source_state_id": change.source_state_id,
                "significance": change.significance,
            },
        )
        session.add(job)
        await session.flush()
        job_ids.append(job.id)
        payload = {
            "job_id": job.id,
            "series_id": item.id,
            "base_version_id": base_version_id,
            "trigger_type": "source_change",
            "source_change_id": change.id,
            "trigger_claim_id": trigger_claim_id,
            "trigger_evidence_item_id": evidence_item_id,
            "reason": job.reason,
        }
        session.add(
            EventArchive(topic=EventTopic.PREDICTION_REVISION_REQUESTED.value, payload=payload)
        )

    change.prediction_revision_job_ids = sorted(
        set([*change.prediction_revision_job_ids, *job_ids])
    )
    await session.commit()

    if job_ids:
        ensure_app_services(request)
        for job_id in job_ids:
            await request.app.state.event_bus.publish(
                EventTopic.PREDICTION_REVISION_REQUESTED.value,
                {"job_id": job_id, "source_change_id": change.id},
            )
    return {
        "status": "queued" if job_ids else "no_prediction_series",
        "change_id": change.id,
        "job_ids": job_ids,
    }


async def _candidate_prediction_series(
    session: AsyncSession,
    change: SourceChangeRecord,
    state: SourceCursorState | None,
) -> list[PredictionSeries]:
    if change.claim_ids:
        series_ids = list(
            (
                await session.scalars(
                    select(PredictionEvidenceLink.series_id).where(
                        PredictionEvidenceLink.claim_id.in_(change.claim_ids)
                    )
                )
            ).all()
        )
        if series_ids:
            return list(
                (
                    await session.scalars(
                        select(PredictionSeries)
                        .where(PredictionSeries.id.in_(sorted(set(series_ids))))
                        .order_by(PredictionSeries.updated_at.desc())
                    )
                ).all()
            )
    query = (
        select(PredictionSeries)
        .where(PredictionSeries.status == "ACTIVE")
        .order_by(PredictionSeries.updated_at.desc())
    )
    if state is not None and state.tenant_id is not None:
        query = query.where(PredictionSeries.tenant_id == state.tenant_id)
    if state is not None and state.preset_id is not None:
        query = query.where(PredictionSeries.preset_id == state.preset_id)
    return list((await session.scalars(query.limit(20))).all())


async def _base_version_id(session: AsyncSession, series: PredictionSeries) -> str | None:
    latest = (
        await session.scalars(
            select(PredictionVersion)
            .where(PredictionVersion.series_id == series.id)
            .order_by(PredictionVersion.version_number.desc())
            .limit(1)
        )
    ).first()
    return latest.id if latest is not None else series.current_version_id


async def _evidence_item_id_for_change(
    session: AsyncSession,
    change: SourceChangeRecord,
) -> str | None:
    raw_id = change.new_raw_source_item_id or change.old_raw_source_item_id
    if raw_id is None:
        return None
    evidence = (
        await session.scalars(
            select(EvidenceItem)
            .join(NormalizedItem, EvidenceItem.normalized_item_id == NormalizedItem.id)
            .join(RawSourceItem, NormalizedItem.raw_source_item_id == RawSourceItem.id)
            .where(RawSourceItem.id == raw_id)
            .limit(1)
        )
    ).first()
    return evidence.id if evidence is not None else None
