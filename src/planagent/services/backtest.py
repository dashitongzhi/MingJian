from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from planagent.config import Settings
from planagent.domain.models import (
    EventArchive,
    PredictionBacktestRecord,
    PredictionSeries,
    PredictionVersion,
    utc_now,
)
from planagent.events.bus import EventBus

_BACKTEST_EVENT_TOPIC = "prediction.backtest_recorded"
_VERIFIED_STATUSES = {"CONFIRMED", "REFUTED", "PARTIAL"}


class BacktestService:
    """预测回测与校准——验证预测准确性，生成校准分数。"""

    def __init__(self, settings: Settings, event_bus: EventBus) -> None:
        self.settings = settings
        self.event_bus = event_bus

    async def verify_prediction(
        self,
        session: AsyncSession,
        prediction_version_id: str,
        actual_outcome: str,
        verification_status: str = "CONFIRMED",
        score: float = 1.0,
    ) -> PredictionBacktestRecord:
        """手动或自动验证一个预测版本。"""
        status = verification_status.upper()
        if status not in _VERIFIED_STATUSES:
            raise ValueError("verification_status must be CONFIRMED, REFUTED, or PARTIAL.")

        version = await session.get(PredictionVersion, prediction_version_id)
        if version is None:
            raise LookupError(f"Prediction version {prediction_version_id} was not found.")
        series = await session.get(PredictionSeries, version.series_id)
        if series is None:
            raise LookupError(f"Prediction series {version.series_id} was not found.")

        now = utc_now()
        normalized_score = max(0.0, min(float(score), 1.0))
        record = (
            await session.scalars(
                select(PredictionBacktestRecord)
                .where(PredictionBacktestRecord.prediction_version_id == version.id)
                .limit(1)
            )
        ).first()
        if record is None:
            record = PredictionBacktestRecord(
                prediction_version_id=version.id,
                series_id=series.id,
                run_id=version.run_id,
                domain_id=series.domain_id,
                tenant_id=series.tenant_id,
                preset_id=series.preset_id,
                verification_status=status,
                actual_outcome=actual_outcome[:1000],
                score=normalized_score,
                verified_at=now,
            )
            session.add(record)
        else:
            record.verification_status = status
            record.actual_outcome = actual_outcome[:1000]
            record.score = normalized_score
            record.verified_at = now
            record.updated_at = now

        version.status = status
        version.updated_at = now
        version.version_metadata = {
            **(version.version_metadata or {}),
            "verification_status": status,
            "actual_outcome": actual_outcome[:1000],
            "backtest_score": normalized_score,
            "verified_at": now.isoformat(),
        }
        await session.flush()

        payload = {
            "record_id": record.id,
            "prediction_version_id": version.id,
            "series_id": series.id,
            "run_id": version.run_id,
            "domain_id": series.domain_id,
            "tenant_id": series.tenant_id,
            "preset_id": series.preset_id,
            "verification_status": status,
            "score": normalized_score,
        }
        session.add(EventArchive(topic=_BACKTEST_EVENT_TOPIC, payload=payload))
        await session.commit()
        await self.event_bus.publish(_BACKTEST_EVENT_TOPIC, payload)
        await session.refresh(record)
        return record

    async def get_backtest_summary(
        self,
        session: AsyncSession,
        domain_id: str | None = None,
        tenant_id: str | None = None,
    ) -> dict[str, Any]:
        """获取回测汇总统计。"""
        counts = {"CONFIRMED": 0, "REFUTED": 0, "PARTIAL": 0}
        query = select(
            PredictionBacktestRecord.verification_status,
            func.count(PredictionBacktestRecord.id),
        ).group_by(PredictionBacktestRecord.verification_status)
        if domain_id is not None:
            query = query.where(PredictionBacktestRecord.domain_id == domain_id)
        if tenant_id is not None:
            query = query.where(PredictionBacktestRecord.tenant_id == tenant_id)

        for status, count in (await session.execute(query)).all():
            if status in counts:
                counts[status] = int(count or 0)

        pending = await self._pending_count(session, domain_id=domain_id, tenant_id=tenant_id)
        confirmed = counts["CONFIRMED"]
        refuted = counts["REFUTED"]
        partial = counts["PARTIAL"]
        verified_total = confirmed + refuted + partial
        return {
            "total": verified_total + pending,
            "confirmed": confirmed,
            "refuted": refuted,
            "partial": partial,
            "pending": pending,
            "accuracy_rate": round((confirmed + 0.5 * partial) / verified_total, 4)
            if verified_total
            else 0.0,
        }

    async def get_calibration_by_domain(
        self,
        session: AsyncSession,
    ) -> list[dict[str, Any]]:
        """按 domain 分组的校准统计。"""
        domain_stats: dict[str, dict[str, Any]] = {}
        record_rows = (
            await session.execute(
                select(
                    PredictionBacktestRecord.domain_id,
                    PredictionBacktestRecord.verification_status,
                    func.count(PredictionBacktestRecord.id),
                ).group_by(
                    PredictionBacktestRecord.domain_id,
                    PredictionBacktestRecord.verification_status,
                )
            )
        ).all()
        for domain_id, status, count in record_rows:
            stats = domain_stats.setdefault(str(domain_id), self._empty_summary(str(domain_id)))
            if status == "CONFIRMED":
                stats["confirmed"] = int(count or 0)
            elif status == "REFUTED":
                stats["refuted"] = int(count or 0)
            elif status == "PARTIAL":
                stats["partial"] = int(count or 0)

        pending_rows = (
            await session.execute(
                select(PredictionSeries.domain_id, func.count(PredictionVersion.id))
                .select_from(PredictionVersion)
                .join(PredictionSeries, PredictionSeries.id == PredictionVersion.series_id)
                .outerjoin(
                    PredictionBacktestRecord,
                    PredictionBacktestRecord.prediction_version_id == PredictionVersion.id,
                )
                .where(
                    PredictionVersion.status == "ACTIVE",
                    PredictionBacktestRecord.id.is_(None),
                )
                .group_by(PredictionSeries.domain_id)
            )
        ).all()
        for domain_id, count in pending_rows:
            stats = domain_stats.setdefault(str(domain_id), self._empty_summary(str(domain_id)))
            stats["pending"] = int(count or 0)

        for stats in domain_stats.values():
            verified_total = stats["confirmed"] + stats["refuted"] + stats["partial"]
            stats["total"] = verified_total + stats["pending"]
            stats["accuracy_rate"] = (
                round((stats["confirmed"] + 0.5 * stats["partial"]) / verified_total, 4)
                if verified_total
                else 0.0
            )
        return sorted(domain_stats.values(), key=lambda item: item["domain_id"])

    async def _pending_count(
        self,
        session: AsyncSession,
        domain_id: str | None,
        tenant_id: str | None,
    ) -> int:
        query = (
            select(func.count(PredictionVersion.id))
            .select_from(PredictionVersion)
            .join(PredictionSeries, PredictionSeries.id == PredictionVersion.series_id)
            .outerjoin(
                PredictionBacktestRecord,
                PredictionBacktestRecord.prediction_version_id == PredictionVersion.id,
            )
            .where(
                PredictionVersion.status == "ACTIVE",
                PredictionBacktestRecord.id.is_(None),
            )
        )
        if domain_id is not None:
            query = query.where(PredictionSeries.domain_id == domain_id)
        if tenant_id is not None:
            query = query.where(PredictionSeries.tenant_id == tenant_id)
        return int((await session.scalar(query)) or 0)

    def _empty_summary(self, domain_id: str) -> dict[str, Any]:
        return {
            "domain_id": domain_id,
            "total": 0,
            "confirmed": 0,
            "refuted": 0,
            "partial": 0,
            "pending": 0,
            "accuracy_rate": 0.0,
        }
