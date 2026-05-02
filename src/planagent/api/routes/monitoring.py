from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from planagent.config import get_settings
from planagent.db import get_session
from planagent.domain.api import (
    PredictionEvidenceLinkRead,
    PredictionRevisionJobRead,
    PredictionSeriesRead,
    PredictionVersionRead,
    SourceChangeRecordRead,
)
from planagent.domain.models import (
    PredictionBacktestRecord,
    PredictionCalibrationContext,
    PredictionEvidenceLink,
    PredictionRevisionJob,
    PredictionSeries,
    PredictionVersion,
    RuleAccuracy,
    SourceChangeRecord,
    SourceCursorState,
    SourceTrustScore,
    WatchRule,
)
from planagent.events.bus import build_event_bus
from planagent.services.prediction import PredictionService

router = APIRouter(tags=["monitoring"])


@router.get("/monitoring/dashboard")
async def get_monitoring_dashboard(
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """监测看板：聚合WatchRule健康、变更趋势、修正队列。"""
    rules = list(
        (
            await session.scalars(
                select(WatchRule).order_by(WatchRule.updated_at.desc())
            )
        ).all()
    )
    watch_rules = []
    for rule in rules:
        change_count = int(
            (
                await session.scalar(
                    select(func.count())
                    .select_from(SourceChangeRecord)
                    .where(SourceChangeRecord.watch_rule_id == rule.id)
                )
            )
            or 0
        )
        cursor_failure_count = int(
            (
                await session.scalar(
                    select(func.coalesce(func.sum(SourceCursorState.consecutive_failures), 0))
                    .where(SourceCursorState.watch_rule_id == rule.id)
                )
            )
            or 0
        )
        if not rule.enabled:
            health = "disabled"
        elif rule.last_poll_error:
            health = "error"
        elif cursor_failure_count > 0:
            health = "degraded"
        else:
            health = "healthy"
        watch_rules.append(
            {
                "id": rule.id,
                "name": rule.name,
                "domain_id": rule.domain_id,
                "enabled": rule.enabled,
                "health": health,
                "last_poll_at": rule.last_poll_at,
                "next_poll_at": rule.next_poll_at,
                "last_poll_error": rule.last_poll_error,
                "poll_attempts": rule.poll_attempts,
                "recent_change_count": change_count,
                "cursor_failure_count": cursor_failure_count,
                "tenant_id": rule.tenant_id,
                "preset_id": rule.preset_id,
            }
        )

    recent_changes = list(
        (
            await session.scalars(
                select(SourceChangeRecord)
                .order_by(SourceChangeRecord.created_at.desc())
                .limit(20)
            )
        ).all()
    )
    revision_jobs = await _count_by_status(
        session,
        PredictionRevisionJob,
        ["PENDING", "PROCESSING", "COMPLETED", "FAILED"],
    )
    predictions = {
        "active": await _count_prediction_versions(session, "ACTIVE"),
        "superseded": await _count_prediction_versions(session, "SUPERSEDED"),
        "verified": int(
            (
                await session.scalar(
                    select(func.count())
                    .select_from(PredictionBacktestRecord)
                    .where(PredictionBacktestRecord.verification_status.in_(["CONFIRMED", "REFUTED", "PARTIAL"]))
                )
            )
            or 0
        ),
    }
    rule_accuracies = list((await session.scalars(select(RuleAccuracy))).all())
    source_trusts = list((await session.scalars(select(SourceTrustScore))).all())
    high_accuracy_count = sum(1 for r in rule_accuracies if r.accuracy_score >= 0.7)
    low_accuracy_count = sum(1 for r in rule_accuracies if r.accuracy_score < 0.3)
    medium_accuracy_count = len(rule_accuracies) - high_accuracy_count - low_accuracy_count
    high_trust_count = sum(1 for s in source_trusts if s.trust_score >= 0.7)
    low_trust_count = sum(1 for s in source_trusts if s.trust_score < 0.3)
    medium_trust_count = len(source_trusts) - high_trust_count - low_trust_count
    avg_accuracy = sum(r.accuracy_score for r in rule_accuracies) / max(len(rule_accuracies), 1)
    avg_trust = sum(s.trust_score for s in source_trusts) / max(len(source_trusts), 1)
    return {
        "watch_rules": watch_rules,
        "recent_changes": [SourceChangeRecordRead.model_validate(item) for item in recent_changes],
        "revision_jobs": revision_jobs,
        "predictions": predictions,
        "calibration": {
            "high_accuracy_rules": high_accuracy_count,
            "medium_accuracy_rules": medium_accuracy_count,
            "low_accuracy_rules": low_accuracy_count,
            "avg_accuracy": avg_accuracy,
            "total_rules": len(rule_accuracies),
            "source_trust_distribution": {
                "high": high_trust_count,
                "medium": medium_trust_count,
                "low": low_trust_count,
            },
            "total_sources": len(source_trusts),
            "avg_trust": avg_trust,
        },
    }


@router.get("/monitoring/calibration")
async def get_calibration_overview(
    domain_id: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    """校准概览——规则准确率、来源可信度、校准趋势"""
    query = select(RuleAccuracy).order_by(RuleAccuracy.accuracy_score.desc())
    if domain_id:
        query = query.where(RuleAccuracy.domain_id == domain_id)
    rule_accuracies = list((await session.scalars(query.limit(50))).all())

    trust_query = select(SourceTrustScore).order_by(SourceTrustScore.trust_score.desc())
    source_trusts = list((await session.scalars(trust_query.limit(50))).all())

    total_rules = len(rule_accuracies)
    high_accuracy = sum(1 for r in rule_accuracies if r.accuracy_score >= 0.7)
    low_accuracy = sum(1 for r in rule_accuracies if r.accuracy_score < 0.3)

    return {
        "rules": [
            {
                "rule_id": r.rule_id,
                "domain_id": r.domain_id,
                "accuracy_score": r.accuracy_score,
                "weight_multiplier": r.weight_multiplier,
                "total_predictions": r.total_predictions,
                "confirmed": r.confirmed,
                "refuted": r.refuted,
                "partial": r.partial,
            }
            for r in rule_accuracies
        ],
        "sources": [
            {
                "source_url_pattern": s.source_url_pattern,
                "trust_score": s.trust_score,
                "total_evidence": s.total_evidence,
                "confirmed": s.evidence_confirmed,
                "refuted": s.evidence_refuted,
            }
            for s in source_trusts
        ],
        "summary": {
            "total_rules": total_rules,
            "high_accuracy_rules": high_accuracy,
            "low_accuracy_rules": low_accuracy,
            "avg_accuracy": sum(r.accuracy_score for r in rule_accuracies) / max(total_rules, 1),
            "total_sources": len(source_trusts),
            "avg_trust": sum(s.trust_score for s in source_trusts) / max(len(source_trusts), 1),
        },
    }


@router.get("/monitoring/calibration/history")
async def get_calibration_history(
    run_id: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    """校准历史——每次推演使用的校准上下文"""
    query = select(PredictionCalibrationContext).order_by(
        PredictionCalibrationContext.created_at.desc()
    )
    if run_id:
        query = query.where(PredictionCalibrationContext.run_id == run_id)

    contexts = list((await session.scalars(query.limit(20))).all())

    return [
        {
            "id": ctx.id,
            "run_id": ctx.run_id,
            "prediction_version_id": ctx.prediction_version_id,
            "historical_versions_injected": ctx.historical_versions_injected,
            "rule_weights_applied": ctx.rule_weights_applied,
            "source_trust_applied": ctx.source_trust_applied,
            "confidence_adjustment": ctx.confidence_adjustment,
            "created_at": ctx.created_at.isoformat() if ctx.created_at else None,
        }
        for ctx in contexts
    ]


@router.get("/monitoring/events/stream")
async def monitoring_events_stream(request: Request) -> StreamingResponse:
    """SSE实时推送：监测事件流。"""
    settings = get_settings()
    bus = build_event_bus(settings)

    async def event_generator():
        topics = [
            "source.changed",
            "prediction.version_created",
            "prediction.revision_completed",
            "prediction.revision_failed",
            "watch.rule_triggered",
        ]
        group = "monitoring-sse"
        consumer = f"sse-{id(request)}"
        last_keepalive = time.monotonic()
        max_lifetime = 3600
        start_time = time.monotonic()

        try:
            while True:
                if time.monotonic() - start_time > max_lifetime:
                    data = json.dumps({"reason": "max_lifetime_reached"})
                    yield f"event: timeout\ndata: {data}\n\n"
                    break

                if await request.is_disconnected():
                    break

                try:
                    events = await bus.consume(
                        topics=topics,
                        group=group,
                        consumer=consumer,
                        count=10,
                        block_ms=5000,
                    )
                except Exception as exc:
                    data = json.dumps({"error": str(exc)[:100]}, ensure_ascii=False)
                    yield f"event: error\ndata: {data}\n\n"
                    await asyncio.sleep(5)
                    continue

                for event in events:
                    data = json.dumps(event.payload, ensure_ascii=False)
                    yield f"event: {event.topic}\ndata: {data}\n\n"
                    await bus.ack(event.topic, group, event.message_id)

                now = time.monotonic()
                if now - last_keepalive >= 30:
                    yield ": keepalive\n\n"
                    last_keepalive = now
        except asyncio.CancelledError:
            pass
        except Exception:
            pass
        finally:
            try:
                await bus.close()
            except Exception:
                pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/predictions/{series_id}/timeline")
async def get_prediction_timeline(
    series_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """预测时间线：版本1到当前版本的完整演化。"""
    series = await _require_series(session, series_id)
    versions = list(
        (
            await session.scalars(
                select(PredictionVersion)
                .where(PredictionVersion.series_id == series_id)
                .order_by(PredictionVersion.version_number.asc())
            )
        ).all()
    )
    version_ids = [version.id for version in versions]
    links_by_version: dict[str, list[PredictionEvidenceLink]] = {version_id: [] for version_id in version_ids}
    if version_ids:
        links = list(
            (
                await session.scalars(
                    select(PredictionEvidenceLink)
                    .where(PredictionEvidenceLink.version_id.in_(version_ids))
                    .order_by(PredictionEvidenceLink.created_at.asc())
                )
            ).all()
        )
        for link in links:
            links_by_version.setdefault(link.version_id, []).append(link)

    jobs_by_new_version: dict[str, PredictionRevisionJob] = {}
    if version_ids:
        jobs = list(
            (
                await session.scalars(
                    select(PredictionRevisionJob)
                    .where(PredictionRevisionJob.new_version_id.in_(version_ids))
                    .order_by(PredictionRevisionJob.created_at.asc())
                )
            ).all()
        )
        jobs_by_new_version = {
            job.new_version_id: job for job in jobs if job.new_version_id is not None
        }

    timeline = []
    previous: PredictionVersion | None = None
    for version in versions:
        timeline.append(
            {
                "version": PredictionVersionRead.model_validate(version),
                "trigger_evidence": [
                    PredictionEvidenceLinkRead.model_validate(link)
                    for link in links_by_version.get(version.id, [])
                ],
                "revision_job": (
                    PredictionRevisionJobRead.model_validate(jobs_by_new_version[version.id])
                    if version.id in jobs_by_new_version
                    else None
                ),
                "probability_delta": _numeric_delta(
                    previous.probability if previous is not None else None,
                    version.probability,
                ),
                "confidence_delta": _numeric_delta(
                    previous.confidence if previous is not None else None,
                    version.confidence,
                ),
            }
        )
        previous = version

    return {
        "series": PredictionSeriesRead.model_validate(series),
        "timeline": timeline,
        "version_count": len(timeline),
    }


@router.get("/predictions/{series_id}/versions/{version_id}/diff")
async def get_version_diff(
    series_id: str,
    version_id: str,
    against: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """版本对比：两个预测版本的差异。"""
    version = await _require_version(session, series_id, version_id)
    compare_version_id = against
    if compare_version_id is None:
        previous = (
            await session.scalars(
                select(PredictionVersion)
                .where(
                    PredictionVersion.series_id == series_id,
                    PredictionVersion.version_number < version.version_number,
                )
                .order_by(PredictionVersion.version_number.desc())
                .limit(1)
            )
        ).first()
        if previous is None:
            raise HTTPException(status_code=400, detail="Prediction version has no previous version.")
        compare_version_id = previous.id
    await _require_version(session, series_id, compare_version_id)

    settings = get_settings()
    bus = build_event_bus(settings)
    try:
        service = PredictionService(settings, bus)
        return await service.compare_versions(session, compare_version_id, version_id)
    finally:
        await bus.close()


@router.post("/predictions/{series_id}/versions/{version_id}/verify")
async def verify_prediction_version(
    series_id: str,
    version_id: str,
    actual_outcome: str = "",
    verification_status: str = "CONFIRMED",
    score: float = Query(default=1.0, ge=0.0, le=1.0),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    """手动验证预测版本。"""
    from planagent.services.backtest import BacktestService

    await _require_version(session, series_id, version_id)
    settings = get_settings()
    bus = build_event_bus(settings)
    try:
        service = BacktestService(settings, bus)
        try:
            record = await service.verify_prediction(
                session,
                version_id,
                actual_outcome,
                verification_status,
                score,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        await bus.close()
    return {"status": "ok", "backtest_id": record.id}


@router.get("/predictions/backtests")
async def list_backtests(
    domain_id: str | None = None,
    tenant_id: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """回测结果列表。"""
    from planagent.services.backtest import BacktestService

    settings = get_settings()
    bus = build_event_bus(settings)
    try:
        service = BacktestService(settings, bus)
        return await service.get_backtest_summary(session, domain_id, tenant_id)
    finally:
        await bus.close()


async def _count_by_status(
    session: AsyncSession,
    model: type,
    statuses: list[str],
) -> dict[str, int]:
    rows = (
        await session.execute(
            select(model.status, func.count()).group_by(model.status)
        )
    ).all()
    counts = {status.lower(): 0 for status in statuses}
    for status, count in rows:
        if status in statuses:
            counts[str(status).lower()] = int(count or 0)
    return counts


async def _count_prediction_versions(session: AsyncSession, status: str) -> int:
    return int(
        (
            await session.scalar(
                select(func.count())
                .select_from(PredictionVersion)
                .where(PredictionVersion.status == status)
            )
        )
        or 0
    )


async def _require_series(session: AsyncSession, series_id: str) -> PredictionSeries:
    series = await session.get(PredictionSeries, series_id)
    if series is None:
        raise HTTPException(status_code=404, detail="Prediction series not found.")
    return series


async def _require_version(
    session: AsyncSession,
    series_id: str,
    version_id: str,
) -> PredictionVersion:
    version = await session.get(PredictionVersion, version_id)
    if version is None or version.series_id != series_id:
        raise HTTPException(status_code=404, detail="Prediction version not found.")
    return version


def _numeric_delta(old_value: float | None, new_value: float | None) -> float | None:
    if old_value is None or new_value is None:
        return None
    return round(float(new_value) - float(old_value), 6)
