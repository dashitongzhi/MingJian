"""辩论回放 API 端点 — Debate Replay API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from planagent.db import get_session
from planagent.domain.api import (
    DebateComparisonRead,
    DebateReplayRead,
    DebateReplaySummaryRead,
    DebateRoundDetailRead,
    DebateTimelineRead,
)
from planagent.services.debate_replay import DebateReplayService

router = APIRouter()


def _get_replay_service(request: Request) -> DebateReplayService:
    """Lazily create and cache the DebateReplayService on app state."""
    if not hasattr(request.app.state, "debate_replay_service"):
        request.app.state.debate_replay_service = DebateReplayService()
    return request.app.state.debate_replay_service


# ── GET /debates/{debate_id}/replay ──────────────────────────────────────────

@router.get(
    "/debates/{debate_id}/replay",
    response_model=DebateReplayRead,
)
async def get_debate_replay(
    debate_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> DebateReplayRead:
    """获取完整回放数据（支持按时间顺序和按轮次两种视图）"""
    service = _get_replay_service(request)
    try:
        return await service.get_replay(session, debate_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ── GET /debates/{debate_id}/replay/rounds/{round_number} ───────────────────

@router.get(
    "/debates/{debate_id}/replay/rounds/{round_number}",
    response_model=DebateRoundDetailRead,
)
async def get_round_replay(
    debate_id: str,
    round_number: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> DebateRoundDetailRead:
    """单轮回放"""
    service = _get_replay_service(request)
    try:
        return await service.get_round_detail(session, debate_id, round_number)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ── GET /debates/{debate_id}/timeline ────────────────────────────────────────

@router.get(
    "/debates/{debate_id}/timeline",
    response_model=DebateTimelineRead,
)
async def get_debate_timeline(
    debate_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> DebateTimelineRead:
    """辩论时间线（每个发言的时间戳）"""
    service = _get_replay_service(request)
    try:
        return await service.get_debate_timeline(session, debate_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ── GET /debates/compare ─────────────────────────────────────────────────────

@router.get(
    "/debates/compare",
    response_model=DebateComparisonRead,
)
async def compare_debates(
    debate_id_1: str = Query(..., alias="debate_id_1", description="First debate ID"),
    debate_id_2: str = Query(..., alias="debate_id_2", description="Second debate ID"),
    request: Request = None,  # type: ignore[assignment]
    session: AsyncSession = Depends(get_session),
) -> DebateComparisonRead:
    """对比两场辩论"""
    service = _get_replay_service(request)
    try:
        return await service.compare_debates(session, debate_id_1, debate_id_2)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ── GET /debates/{debate_id}/summary ─────────────────────────────────────────

@router.get(
    "/debates/{debate_id}/summary",
    response_model=DebateReplaySummaryRead,
)
async def get_debate_summary(
    debate_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> DebateReplaySummaryRead:
    """辩论摘要（包含关键转折点）"""
    service = _get_replay_service(request)
    try:
        return await service.get_summary(session, debate_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
