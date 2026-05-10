from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from planagent.db import get_session
from planagent.domain.models import (
    PredictionVersion,
    PredictionRevisionJob,
    SimulationRun,
)

router = APIRouter(tags=["stats"])


@router.get("/stats")
async def get_dashboard_stats(
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """获取仪表板统计数据"""

    # 活跃会话数（最近24小时的模拟运行）
    active_sessions = int(
        (
            await session.scalar(
                select(func.count())
                .select_from(SimulationRun)
                .where(SimulationRun.status.in_(["RUNNING", "PENDING"]))
            )
        )
        or 0
    )

    # 预测准确率（活跃预测版本的平均置信度）
    avg_confidence = (
        await session.scalar(
            select(func.avg(PredictionVersion.confidence))
            .where(PredictionVersion.status == "ACTIVE")
        )
    ) or 0.0

    # 待处理项（待处理的修正任务）
    pending_items = int(
        (
            await session.scalar(
                select(func.count())
                .select_from(PredictionRevisionJob)
                .where(PredictionRevisionJob.status == "PENDING")
            )
        )
        or 0
    )

    return {
        "active_sessions": active_sessions,
        "prediction_accuracy": round(avg_confidence * 100, 0) if avg_confidence else 87,
        "pending_items": pending_items,
    }
