from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from planagent.db import get_session
from planagent.domain.api import (
    IngestRunCreate,
    IngestRunRead,
    ReviewDecisionRequest,
    ReviewItemRead,
)
from planagent.domain.models import (
    Claim,
    EventRecord,
    EvidenceItem,
    ReviewItem,
    Signal,
    Trend,
)
from planagent.domain.types import (
    ClaimModel,
    EventModel,
    EvidenceItemModel,
    SignalModel,
    TrendModel,
)
from planagent.api.routes._deps import get_pipeline_service

router = APIRouter()


class EvidencePage(BaseModel):
    items: list[EvidenceItemModel]
    total: int
    limit: int
    offset: int


class ClaimPage(BaseModel):
    items: list[ClaimModel]
    total: int
    limit: int
    offset: int


class SignalPage(BaseModel):
    items: list[SignalModel]
    total: int
    limit: int
    offset: int


class EventPage(BaseModel):
    items: list[EventModel]
    total: int
    limit: int
    offset: int


class TrendPage(BaseModel):
    items: list[TrendModel]
    total: int
    limit: int
    offset: int


@router.post("/ingest/runs", response_model=IngestRunRead, status_code=201)
async def create_ingest_run(
    payload: IngestRunCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> IngestRunRead:
    service = get_pipeline_service(request)
    run = await service.create_ingest_run(session, payload)
    return IngestRunRead.model_validate(run)


@router.get("/evidence", response_model=EvidencePage)
async def list_evidence(
    tenant_id: str | None = None,
    preset_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> EvidencePage:
    query = select(EvidenceItem).order_by(EvidenceItem.created_at.desc())
    if tenant_id:
        query = query.where(EvidenceItem.tenant_id == tenant_id)
    if preset_id:
        query = query.where(EvidenceItem.preset_id == preset_id)
    total = await session.scalar(
        select(func.count()).select_from(query.order_by(None).subquery())
    )
    evidence = list(
        (await session.scalars(query.limit(limit).offset(offset))).all()
    )
    return EvidencePage(
        items=[EvidenceItemModel.model_validate(item) for item in evidence],
        total=total or 0,
        limit=limit,
        offset=offset,
    )


@router.get("/claims", response_model=ClaimPage)
async def list_claims(
    status: str | None = None,
    tenant_id: str | None = None,
    preset_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> ClaimPage:
    query = select(Claim).order_by(Claim.created_at.desc())
    if status:
        query = query.where(Claim.status == status.upper())
    if tenant_id:
        query = query.where(Claim.tenant_id == tenant_id)
    if preset_id:
        query = query.where(Claim.preset_id == preset_id)
    total = await session.scalar(
        select(func.count()).select_from(query.order_by(None).subquery())
    )
    claims = list((await session.scalars(query.limit(limit).offset(offset))).all())
    return ClaimPage(
        items=[ClaimModel.model_validate(claim) for claim in claims],
        total=total or 0,
        limit=limit,
        offset=offset,
    )


@router.get("/signals", response_model=SignalPage)
async def list_signals(
    tenant_id: str | None = None,
    preset_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> SignalPage:
    query = select(Signal).order_by(Signal.created_at.desc())
    if tenant_id:
        query = query.where(Signal.tenant_id == tenant_id)
    if preset_id:
        query = query.where(Signal.preset_id == preset_id)
    total = await session.scalar(
        select(func.count()).select_from(query.order_by(None).subquery())
    )
    signals = list((await session.scalars(query.limit(limit).offset(offset))).all())
    return SignalPage(
        items=[SignalModel.model_validate(item) for item in signals],
        total=total or 0,
        limit=limit,
        offset=offset,
    )


@router.get("/events", response_model=EventPage)
async def list_events(
    tenant_id: str | None = None,
    preset_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> EventPage:
    query = select(EventRecord).order_by(EventRecord.created_at.desc())
    if tenant_id:
        query = query.where(EventRecord.tenant_id == tenant_id)
    if preset_id:
        query = query.where(EventRecord.preset_id == preset_id)
    total = await session.scalar(
        select(func.count()).select_from(query.order_by(None).subquery())
    )
    events = list((await session.scalars(query.limit(limit).offset(offset))).all())
    return EventPage(
        items=[EventModel.model_validate(item) for item in events],
        total=total or 0,
        limit=limit,
        offset=offset,
    )


@router.get("/trends", response_model=TrendPage)
async def list_trends(
    tenant_id: str | None = None,
    preset_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> TrendPage:
    query = select(Trend).order_by(Trend.created_at.desc())
    if tenant_id:
        query = query.where(Trend.tenant_id == tenant_id)
    if preset_id:
        query = query.where(Trend.preset_id == preset_id)
    total = await session.scalar(
        select(func.count()).select_from(query.order_by(None).subquery())
    )
    trends = list((await session.scalars(query.limit(limit).offset(offset))).all())
    return TrendPage(
        items=[TrendModel.model_validate(item) for item in trends],
        total=total or 0,
        limit=limit,
        offset=offset,
    )


@router.get("/review/items", response_model=list[ReviewItemRead])
async def list_review_items(
    status: str | None = None,
    tenant_id: str | None = None,
    preset_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> list[ReviewItemRead]:
    query = select(ReviewItem).order_by(ReviewItem.created_at.desc())
    if status:
        query = query.where(ReviewItem.status == status.upper())
    if tenant_id:
        query = query.where(ReviewItem.tenant_id == tenant_id)
    if preset_id:
        query = query.where(ReviewItem.preset_id == preset_id)
    review_items = list((await session.scalars(query.offset(offset).limit(limit))).all())
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
