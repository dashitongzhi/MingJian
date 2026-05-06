"""辩论插话 API 端点 — Debate Interrupt API routes.

用户可以在辩论进行中提交补充信息、修正方向或注入新证据。
插话内容会被记录并在下一轮辩论的 context 中注入。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from planagent.db import get_session
from planagent.domain.api import DebateInterruptCreate, DebateInterruptRead
from planagent.domain.enums import EventTopic
from planagent.domain.models import DebateInterruptRecord, DebateSessionRecord, EventArchive
from planagent.events.bus import EventBus

router = APIRouter(tags=["Debate Interrupts"])

_INTERRUPT_TYPE_LABELS = {
    "supplementary_info": "补充信息",
    "direction_correction": "修正方向",
    "new_evidence": "新证据",
    "general": "通用插话",
}


def _get_event_bus(request: Request) -> EventBus:
    return request.app.state.event_bus


# ── POST /debates/{debate_id}/interrupt ──────────────────────────────────────

@router.post(
    "/debates/{debate_id}/interrupt",
    response_model=DebateInterruptRead,
    status_code=201,
)
async def interrupt_debate(
    debate_id: str,
    payload: DebateInterruptCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> DebateInterruptRead:
    """在辩论进行中提交插话。

    - 用户可以提交补充信息、修正方向、新证据等
    - 插话内容会被记录，供下一轮辩论 context 注入
    - 通过事件总线广播通知
    """
    debate = await session.get(DebateSessionRecord, debate_id)
    if debate is None:
        raise HTTPException(
            status_code=404,
            detail=f"Debate {debate_id} was not found.",
        )

    # 只有运行中的辩论才允许插话
    if debate.status != "RUNNING":
        raise HTTPException(
            status_code=409,
            detail=f"Debate {debate_id} is not running (status={debate.status}). "
                   "Interruptions are only allowed for running debates.",
        )

    interrupt = DebateInterruptRecord(
        debate_session_id=debate_id,
        message=payload.message.strip(),
        interrupt_type=payload.interrupt_type,
        status="PENDING",
    )
    session.add(interrupt)

    # 记录事件
    interrupt_event = EventArchive(
        topic=EventTopic.DEBATE_INTERRUPTED.value,
        payload={
            "debate_id": debate_id,
            "interrupt_id": interrupt.id,
            "interrupt_type": payload.interrupt_type,
            "message_preview": payload.message[:200],
        },
    )
    session.add(interrupt_event)

    await session.commit()
    await session.refresh(interrupt)

    # 发布事件通知
    event_bus = _get_event_bus(request)
    await event_bus.publish(
        EventTopic.DEBATE_INTERRUPTED.value,
        {
            "debate_id": debate_id,
            "interrupt_id": interrupt.id,
            "interrupt_type": payload.interrupt_type,
            "message_preview": payload.message[:200],
        },
    )

    return DebateInterruptRead.model_validate(interrupt)


# ── GET /debates/{debate_id}/interrupts ───────────────────────────────────────

@router.get(
    "/debates/{debate_id}/interrupts",
    response_model=list[DebateInterruptRead],
)
async def list_debate_interrupts(
    debate_id: str,
    session: AsyncSession = Depends(get_session),
) -> list[DebateInterruptRead]:
    """获取辩论的所有插话记录"""
    debate = await session.get(DebateSessionRecord, debate_id)
    if debate is None:
        raise HTTPException(
            status_code=404,
            detail=f"Debate {debate_id} was not found.",
        )

    interrupts = list(
        (
            await session.scalars(
                select(DebateInterruptRecord)
                .where(DebateInterruptRecord.debate_session_id == debate_id)
                .order_by(DebateInterruptRecord.created_at.asc())
            )
        ).all()
    )
    return [DebateInterruptRead.model_validate(i) for i in interrupts]


# ── GET /debates/{debate_id}/pending-interrupts (internal helper) ────────────

@router.get(
    "/debates/{debate_id}/pending-interrupts",
    response_model=list[DebateInterruptRead],
)
async def list_pending_interrupts(
    debate_id: str,
    session: AsyncSession = Depends(get_session),
) -> list[DebateInterruptRead]:
    """获取辩论的待注入插话记录（PENDING 状态）"""
    debate = await session.get(DebateSessionRecord, debate_id)
    if debate is None:
        raise HTTPException(
            status_code=404,
            detail=f"Debate {debate_id} was not found.",
        )

    interrupts = list(
        (
            await session.scalars(
                select(DebateInterruptRecord)
                .where(
                    DebateInterruptRecord.debate_session_id == debate_id,
                    DebateInterruptRecord.status == "PENDING",
                )
                .order_by(DebateInterruptRecord.created_at.asc())
            )
        ).all()
    )
    return [DebateInterruptRead.model_validate(i) for i in interrupts]
