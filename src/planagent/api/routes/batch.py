"""批量任务 API 路由 —— 支持一次性提交多个方案并行辩论"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from planagent.db import get_session
from planagent.domain.api import (
    BatchSubTaskRead,
    BatchTaskDetailRead,
    BatchTaskRead,
    BatchTaskSubmitRequest,
)
from planagent.domain.enums import BatchSubTaskStatus, BatchTaskStatus
from planagent.domain.models import (
    BatchSubTask,
    BatchTask,
    DebateSessionRecord,
    utc_now,
)
from planagent.services.debate import DebateService
from planagent.domain.api import DebateTriggerRequest

router = APIRouter(prefix="/batch", tags=["Batch Tasks"])


# ── 辅助函数 ─────────────────────────────────────────────────────


async def _run_sub_task_debate(
    database_url: str,
    batch_id: str,
    sub_task_id: str,
    topic: str,
    proposal_title: str,
    proposal_description: str,
    trigger_type: str,
) -> None:
    """后台运行单个子任务辩论（独立 session）"""
    from planagent.db import get_database
    from planagent.events.bus import build_event_bus
    from planagent.config import get_settings
    from planagent.services.openai_client import OpenAIService

    settings = get_settings()
    database = get_database()

    async with database.session() as session:
        try:
            # 更新状态为 PROCESSING
            sub_task = await session.get(BatchSubTask, sub_task_id)
            if sub_task is None or sub_task.status == BatchSubTaskStatus.CANCELLED.value:
                return

            sub_task.status = BatchSubTaskStatus.PROCESSING.value
            batch = await session.get(BatchTask, batch_id)
            if batch is None or batch.status == BatchTaskStatus.CANCELLED.value:
                sub_task.status = BatchSubTaskStatus.CANCELLED.value
                await session.commit()
                return

            batch.status = BatchTaskStatus.PROCESSING.value
            await session.commit()

            # 构建辩论上下文
            context_lines = [
                f"## 决策点\n{batch.decision_point}",
                f"## 待评估方案：{proposal_title}",
                proposal_description,
            ]

            event_bus = build_event_bus(settings)
            openai_service = OpenAIService(settings)
            debate_service = DebateService(
                settings=settings,
                event_bus=event_bus,
                openai_service=openai_service,
            )

            payload = DebateTriggerRequest(
                topic=topic,
                trigger_type=trigger_type,
                target_type="run",
                context_lines=context_lines,
            )

            debate_detail = await debate_service.trigger_debate(session, payload)

            # 更新子任务结果
            sub_task = await session.get(BatchSubTask, sub_task_id)
            if sub_task is not None:
                sub_task.debate_id = debate_detail.id
                sub_task.status = BatchSubTaskStatus.COMPLETED.value
                if debate_detail.verdict:
                    sub_task.verdict = debate_detail.verdict.verdict
                    sub_task.confidence = debate_detail.verdict.confidence
                    sub_task.result_summary = debate_detail.verdict.conclusion_summary
                sub_task.completed_at = utc_now()

            # 更新批量任务计数
            batch = await session.get(BatchTask, batch_id)
            if batch is not None:
                batch.completed_tasks += 1
                _update_batch_status(batch)
                await session.commit()

            await openai_service.close()
            await event_bus.close()

        except Exception as exc:
            # 任务失败
            sub_task = await session.get(BatchSubTask, sub_task_id)
            if sub_task is not None:
                sub_task.status = BatchSubTaskStatus.FAILED.value
                sub_task.error_message = str(exc)[:2000]
                sub_task.completed_at = utc_now()

            batch = await session.get(BatchTask, batch_id)
            if batch is not None:
                batch.failed_tasks += 1
                _update_batch_status(batch)

            await session.commit()


def _update_batch_status(batch: BatchTask) -> None:
    """根据子任务完成情况更新批量任务状态"""
    if batch.status == BatchTaskStatus.CANCELLED.value:
        return
    total = batch.total_tasks
    done = batch.completed_tasks
    failed = batch.failed_tasks
    if done + failed >= total:
        if failed == 0:
            batch.status = BatchTaskStatus.COMPLETED.value
        elif done == 0:
            batch.status = BatchTaskStatus.FAILED.value
        else:
            batch.status = BatchTaskStatus.PARTIAL.value
        batch.completed_at = utc_now()


# ── API 端点 ─────────────────────────────────────────────────────


@router.post("/submit", response_model=BatchTaskDetailRead, status_code=201)
async def submit_batch_task(
    payload: BatchTaskSubmitRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> BatchTaskDetailRead:
    """提交批量任务：为每个方案自动创建子任务并并行启动辩论"""
    batch = BatchTask(
        title=payload.title,
        decision_point=payload.decision_point,
        trigger_type=payload.trigger_type,
        tenant_id=payload.tenant_id,
        preset_id=payload.preset_id,
        total_tasks=len(payload.proposals),
        configuration={
            "proposal_count": len(payload.proposals),
            "proposal_titles": [p.title for p in payload.proposals],
        },
    )
    session.add(batch)
    await session.flush()

    sub_tasks: list[BatchSubTask] = []
    for idx, proposal in enumerate(payload.proposals):
        topic = (
            f"评估方案「{proposal.title}」对于决策点「{payload.decision_point}」的可行性"
        )
        sub_task = BatchSubTask(
            batch_id=batch.id,
            index=idx,
            proposal_title=proposal.title,
            proposal_description=proposal.description,
            topic=topic,
        )
        session.add(sub_task)
        sub_tasks.append(sub_task)

    await session.commit()

    # 刷新获取完整数据
    for st in sub_tasks:
        await session.refresh(st)

    # 在后台并行启动所有辩论
    from planagent.config import get_settings

    settings = get_settings()
    for st in sub_tasks:
        background_tasks.add_task(
            _run_sub_task_debate,
            settings.database_url,
            batch.id,
            st.id,
            st.topic,
            st.proposal_title,
            st.proposal_description,
            payload.trigger_type,
        )

    await session.refresh(batch)
    return _build_detail_read(batch, sub_tasks)


@router.get("/{batch_id}", response_model=BatchTaskRead)
async def get_batch_task(
    batch_id: str,
    session: AsyncSession = Depends(get_session),
) -> BatchTaskRead:
    """查看批量任务整体进度"""
    batch = await session.get(BatchTask, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="批量任务不存在。")
    return BatchTaskRead.model_validate(batch)


@router.get("/{batch_id}/tasks", response_model=list[BatchSubTaskRead])
async def get_batch_sub_tasks(
    batch_id: str,
    session: AsyncSession = Depends(get_session),
) -> list[BatchSubTaskRead]:
    """查看各子任务状态"""
    batch = await session.get(BatchTask, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="批量任务不存在。")

    query = (
        select(BatchSubTask)
        .where(BatchSubTask.batch_id == batch_id)
        .order_by(BatchSubTask.index)
    )
    sub_tasks = list((await session.scalars(query)).all())
    return [BatchSubTaskRead.model_validate(st) for st in sub_tasks]


@router.post("/{batch_id}/cancel", response_model=BatchTaskRead)
async def cancel_batch_task(
    batch_id: str,
    session: AsyncSession = Depends(get_session),
) -> BatchTaskRead:
    """取消整个批量任务（仅取消尚未开始的子任务）"""
    batch = await session.get(BatchTask, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="批量任务不存在。")

    if batch.status in (
        BatchTaskStatus.COMPLETED.value,
        BatchTaskStatus.CANCELLED.value,
        BatchTaskStatus.FAILED.value,
    ):
        raise HTTPException(
            status_code=400,
            detail=f"批量任务已处于 {batch.status} 状态，无法取消。",
        )

    # 取消所有 PENDING 状态的子任务
    query = select(BatchSubTask).where(
        BatchSubTask.batch_id == batch_id,
        BatchSubTask.status == BatchSubTaskStatus.PENDING.value,
    )
    pending_tasks = list((await session.scalars(query)).all())
    for st in pending_tasks:
        st.status = BatchSubTaskStatus.CANCELLED.value
        st.completed_at = utc_now()

    batch.status = BatchTaskStatus.CANCELLED.value
    batch.completed_at = utc_now()
    await session.commit()
    await session.refresh(batch)
    return BatchTaskRead.model_validate(batch)


@router.get("", response_model=list[BatchTaskRead])
async def list_batch_tasks(
    limit: int = 20,
    session: AsyncSession = Depends(get_session),
) -> list[BatchTaskRead]:
    """列出批量任务"""
    query = select(BatchTask).order_by(BatchTask.created_at.desc()).limit(limit)
    tasks = list((await session.scalars(query)).all())
    return [BatchTaskRead.model_validate(t) for t in tasks]


# ── 辅助 ─────────────────────────────────────────────────────────


def _build_detail_read(
    batch: BatchTask, sub_tasks: list[BatchSubTask]
) -> BatchTaskDetailRead:
    return BatchTaskDetailRead(
        id=batch.id,
        title=batch.title,
        decision_point=batch.decision_point,
        trigger_type=batch.trigger_type,
        status=batch.status,
        total_tasks=batch.total_tasks,
        completed_tasks=batch.completed_tasks,
        failed_tasks=batch.failed_tasks,
        tenant_id=batch.tenant_id,
        preset_id=batch.preset_id,
        sub_tasks=[BatchSubTaskRead.model_validate(st) for st in sub_tasks],
        created_at=batch.created_at,
        updated_at=batch.updated_at,
        completed_at=batch.completed_at,
    )
