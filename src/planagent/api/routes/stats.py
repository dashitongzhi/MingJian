from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from planagent.db import get_session
from planagent.domain.models import (
    PredictionBacktestRecord,
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

    verified_counts = {"CONFIRMED": 0, "REFUTED": 0, "PARTIAL": 0}
    rows = (
        await session.execute(
            select(
                PredictionBacktestRecord.verification_status,
                func.count(PredictionBacktestRecord.id),
            )
            .where(PredictionBacktestRecord.verification_status.in_(verified_counts))
            .group_by(PredictionBacktestRecord.verification_status)
        )
    ).all()
    for status, count in rows:
        verified_counts[str(status)] = int(count or 0)
    verified_total = sum(verified_counts.values())
    prediction_accuracy = (
        round(
            ((verified_counts["CONFIRMED"] + 0.5 * verified_counts["PARTIAL"]) / verified_total)
            * 100,
            0,
        )
        if verified_total
        else None
    )

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
        "prediction_accuracy": prediction_accuracy,
        "prediction_accuracy_sample_size": verified_total,
        "prediction_accuracy_status": "verified" if verified_total else "no_verified_samples",
        "pending_items": pending_items,
    }
