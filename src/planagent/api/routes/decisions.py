from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from planagent.db import get_session
from planagent.domain.api import (
    UserDecisionCreate,
    UserDecisionOutcomeUpdate,
    UserDecisionRead,
    UserDecisionStatsRead,
)
from planagent.domain.models import StrategicSession, UserDecision, utc_now

router = APIRouter(tags=["Decisions"])

_DECISION_VALUES = ("adopt", "defer", "need_more_info", "reject")
_RATIO_VALUES = ("adopt", "defer", "reject")


@router.post("/decisions", response_model=UserDecisionRead, status_code=201)
async def create_user_decision(
    payload: UserDecisionCreate,
    session: AsyncSession = Depends(get_session),
) -> UserDecisionRead:
    await _require_strategic_session(session, payload.session_id)
    record = UserDecision(
        session_id=payload.session_id,
        decision=payload.decision,
        notes=payload.notes,
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return UserDecisionRead.model_validate(record)


@router.get("/decisions", response_model=list[UserDecisionRead])
async def list_user_decisions(
    session_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
) -> list[UserDecisionRead]:
    query = select(UserDecision).order_by(UserDecision.created_at.desc())
    if session_id is not None:
        query = query.where(UserDecision.session_id == session_id)
    records = list((await session.scalars(query.limit(limit))).all())
    return [UserDecisionRead.model_validate(record) for record in records]


@router.put("/decisions/{decision_id}/outcome", response_model=UserDecisionRead)
async def record_user_decision_outcome(
    decision_id: str,
    payload: UserDecisionOutcomeUpdate,
    session: AsyncSession = Depends(get_session),
) -> UserDecisionRead:
    record = await session.get(UserDecision, decision_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Decision not found.")
    now = utc_now()
    record.outcome = payload.outcome
    record.outcome_recorded_at = now
    record.updated_at = now
    await session.commit()
    await session.refresh(record)
    return UserDecisionRead.model_validate(record)


@router.get("/decisions/stats", response_model=UserDecisionStatsRead)
async def get_user_decision_stats(
    session_id: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> UserDecisionStatsRead:
    query = select(UserDecision.decision, func.count()).group_by(UserDecision.decision)
    if session_id is not None:
        query = query.where(UserDecision.session_id == session_id)
    rows = (await session.execute(query)).all()
    counts = {decision: 0 for decision in _DECISION_VALUES}
    counts.update({str(decision): int(count) for decision, count in rows})
    total = sum(counts.values())
    ratios = {
        decision: (counts[decision] / total if total else 0.0)
        for decision in _RATIO_VALUES
    }
    return UserDecisionStatsRead(total=total, counts=counts, ratios=ratios)


async def _require_strategic_session(session: AsyncSession, session_id: str) -> StrategicSession:
    record = await session.get(StrategicSession, session_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Strategic session not found.")
    return record
