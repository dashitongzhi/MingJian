from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from planagent.api.routes._deps import ensure_app_services, get_session
from planagent.domain.api import (
    PredictionEvidenceLinkRead,
    PredictionRevisionJobRead,
    PredictionSeriesRead,
    PredictionVersionRead,
    RefForecastRequest,
)
from planagent.domain.enums import EventTopic
from planagent.domain.models import (
    EventArchive,
    PredictionEvidenceLink,
    PredictionRevisionJob,
    PredictionSeries,
    PredictionVersion,
)

router = APIRouter(tags=["predictions"])


@router.get("/predictions", response_model=list[PredictionSeriesRead])
async def list_predictions(
    domain_id: str | None = None,
    tenant_id: str | None = None,
    preset_id: str | None = None,
    subject_id: str | None = None,
    status: str = "ACTIVE",
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> list[PredictionSeriesRead]:
    query = select(PredictionSeries).order_by(PredictionSeries.updated_at.desc())
    if tenant_id is not None:
        query = query.where(PredictionSeries.tenant_id == tenant_id)
    if preset_id is not None:
        query = query.where(PredictionSeries.preset_id == preset_id)
    if subject_id is not None:
        query = query.where(PredictionSeries.subject_id == subject_id)
    if status:
        query = query.where(PredictionSeries.status == status)
    records = list((await session.scalars(query.limit(limit * 2))).all())
    if domain_id is not None:
        records = [
            item
            for item in records
            if (item.series_metadata or {}).get("domain_id") == domain_id
        ]
    records = records[:limit]
    return [PredictionSeriesRead.model_validate(item) for item in records]


@router.get("/predictions/revision-jobs", response_model=list[PredictionRevisionJobRead])
async def list_revision_jobs(
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> list[PredictionRevisionJobRead]:
    query = select(PredictionRevisionJob).order_by(PredictionRevisionJob.created_at.desc())
    if status is not None:
        query = query.where(PredictionRevisionJob.status == status)
    records = list((await session.scalars(query.limit(limit))).all())
    return [PredictionRevisionJobRead.model_validate(item) for item in records]


@router.get("/predictions/{series_id}")
async def get_prediction_series(
    series_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    series = await session.get(PredictionSeries, series_id)
    if series is None:
        raise HTTPException(status_code=404, detail="Prediction series not found.")
    latest_version = await _latest_version(session, series_id)
    version_count = int(
        (
            await session.scalar(
                select(func.count())
                .select_from(PredictionVersion)
                .where(PredictionVersion.series_id == series_id)
            )
        )
        or 0
    )
    return {
        "series": PredictionSeriesRead.model_validate(series),
        "latest_version": (
            PredictionVersionRead.model_validate(latest_version)
            if latest_version is not None
            else None
        ),
        "version_count": version_count,
    }


@router.get("/predictions/{series_id}/versions", response_model=list[PredictionVersionRead])
async def list_prediction_versions(
    series_id: str,
    session: AsyncSession = Depends(get_session),
) -> list[PredictionVersionRead]:
    await _require_series(session, series_id)
    records = list(
        (
            await session.scalars(
                select(PredictionVersion)
                .where(PredictionVersion.series_id == series_id)
                .order_by(PredictionVersion.version_number.asc())
            )
        ).all()
    )
    return [PredictionVersionRead.model_validate(item) for item in records]


@router.get("/predictions/{series_id}/impact")
async def get_prediction_impact(
    series_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    series = await _require_series(session, series_id)
    links = list(
        (
            await session.scalars(
                select(PredictionEvidenceLink)
                .join(
                    PredictionVersion,
                    PredictionVersion.id == PredictionEvidenceLink.version_id,
                )
                .where(PredictionVersion.series_id == series_id)
                .order_by(PredictionEvidenceLink.created_at.desc())
            )
        ).all()
    )
    return {
        "series_id": series.id,
        "current_version_id": series.current_version_id,
        "links": [PredictionEvidenceLinkRead.model_validate(item) for item in links],
        "total_links": len(links),
    }


@router.post("/predictions/{series_id}/reforecast", response_model=PredictionRevisionJobRead, status_code=201)
async def trigger_reforecast(
    series_id: str,
    body: RefForecastRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> PredictionRevisionJobRead:
    series = await _require_series(session, series_id)
    latest_version = await _latest_version(session, series_id)
    if latest_version is None and series.current_version_id is None:
        raise HTTPException(status_code=400, detail="Prediction series has no base version.")
    job = PredictionRevisionJob(
        series_id=series_id,
        base_version_id=latest_version.id if latest_version is not None else series.current_version_id,
        claim_id=body.trigger_claim_id,
        evidence_item_id=body.trigger_evidence_item_id or "",
        status="PENDING",
        reason=body.reason or "Manual reforecast requested.",
        job_metadata={"trigger_topic": body.trigger_topic, "trigger_type": "manual"},
    )
    session.add(job)
    await session.flush()

    payload = {
        "job_id": job.id,
        "series_id": series_id,
        "base_version_id": job.base_version_id,
        "trigger_type": "manual",
        "trigger_claim_id": body.trigger_claim_id,
        "trigger_evidence_item_id": body.trigger_evidence_item_id,
        "reason": job.reason,
    }
    session.add(EventArchive(topic=EventTopic.PREDICTION_REVISION_REQUESTED.value, payload=payload))
    await session.commit()
    await session.refresh(job)

    ensure_app_services(request)
    await request.app.state.event_bus.publish(EventTopic.PREDICTION_REVISION_REQUESTED.value, payload)
    return PredictionRevisionJobRead.model_validate(job)


async def _require_series(session: AsyncSession, series_id: str) -> PredictionSeries:
    series = await session.get(PredictionSeries, series_id)
    if series is None:
        raise HTTPException(status_code=404, detail="Prediction series not found.")
    return series


async def _latest_version(session: AsyncSession, series_id: str) -> PredictionVersion | None:
    return (
        await session.scalars(
            select(PredictionVersion)
            .where(PredictionVersion.series_id == series_id)
            .order_by(PredictionVersion.version_number.desc())
            .limit(1)
        )
    ).first()
