from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from planagent.domain.api import QueueHealthBucketRead, ReviewQueueReasonRead, RuntimeQueueHealthRead
from planagent.domain.enums import IngestRunStatus, ReviewItemStatus, SimulationRunStatus
from planagent.domain.models import (
    DeadLetterEvent,
    IngestRun,
    RawSourceItem,
    ReviewItem,
    SimulationRun,
    SourceHealth,
    utc_now,
)
from planagent.services.startup import normalize_tenant_id


class RuntimeMonitorService:
    def __init__(self, backpressure_pending_threshold: int = 1000) -> None:
        self.backpressure_pending_threshold = backpressure_pending_threshold

    async def collect_queue_health(
        self,
        session: AsyncSession,
        tenant_id: str | None = None,
        preset_id: str | None = None,
    ) -> RuntimeQueueHealthRead:
        normalized_tenant = normalize_tenant_id(tenant_id)
        now = utc_now()
        queues = [
            await self._build_ingest_bucket(session, now, normalized_tenant, preset_id),
            await self._build_raw_bucket(session, now, normalized_tenant, preset_id),
            await self._build_review_bucket(session, now, normalized_tenant, preset_id),
            await self._build_simulation_bucket(session, now, normalized_tenant, preset_id),
        ]
        dead_letter_count = await self._count(
            session,
            select(func.count()).select_from(DeadLetterEvent),
        )
        degraded_sources = [
            {
                "source_type": item.source_type,
                "status": item.status,
                "consecutive_failures": item.consecutive_failures,
                "last_error": item.last_error,
            }
            for item in (
                await session.scalars(
                    select(SourceHealth).where(SourceHealth.status.in_(["ERROR", "DEGRADED"]))
                )
            ).all()
        ]
        return RuntimeQueueHealthRead(
            generated_at=now,
            tenant_id=normalized_tenant,
            preset_id=preset_id,
            queues=queues,
            review_queue_reasons=await self._build_review_reason_breakdown(
                session,
                now,
                normalized_tenant,
                preset_id,
            ),
            dead_letter_count=dead_letter_count,
            degraded_sources=degraded_sources,
            backpressure_active=any(
                bucket.pending + bucket.reclaimable > self.backpressure_pending_threshold for bucket in queues
            ),
        )

    async def _build_ingest_bucket(
        self,
        session: AsyncSession,
        now,
        tenant_id: str | None,
        preset_id: str | None,
    ) -> QueueHealthBucketRead:
        filters = self._optional_filters(IngestRun, tenant_id, preset_id)
        pending = await self._count(
            session,
            select(func.count()).select_from(IngestRun).where(*filters, IngestRun.status == IngestRunStatus.PENDING.value),
        )
        processing = await self._count(
            session,
            select(func.count()).select_from(IngestRun).where(
                *filters,
                IngestRun.status == IngestRunStatus.PROCESSING.value,
                or_(IngestRun.lease_owner.is_(None), IngestRun.lease_expires_at.is_(None), IngestRun.lease_expires_at >= now),
            ),
        )
        completed = await self._count(
            session,
            select(func.count()).select_from(IngestRun).where(
                *filters,
                IngestRun.status == IngestRunStatus.COMPLETED.value,
            ),
        )
        failed = await self._count(
            session,
            select(func.count()).select_from(IngestRun).where(*filters, IngestRun.status == IngestRunStatus.FAILED.value),
        )
        reclaimable = await self._count(
            session,
            select(func.count()).select_from(IngestRun).where(
                *filters,
                IngestRun.status == IngestRunStatus.PROCESSING.value,
                IngestRun.lease_owner.is_not(None),
                IngestRun.lease_expires_at.is_not(None),
                IngestRun.lease_expires_at < now,
            ),
        )
        return QueueHealthBucketRead(
            queue="ingest_runs",
            pending=pending,
            processing=processing,
            completed=completed,
            failed=failed,
            reclaimable=reclaimable,
        )

    async def _build_raw_bucket(
        self,
        session: AsyncSession,
        now,
        tenant_id: str | None,
        preset_id: str | None,
    ) -> QueueHealthBucketRead:
        filters = self._optional_filters(RawSourceItem, tenant_id, preset_id)
        pending = await self._count(
            session,
            select(func.count()).select_from(RawSourceItem).where(*filters, RawSourceItem.knowledge_status == "PENDING"),
        )
        processing = await self._count(
            session,
            select(func.count()).select_from(RawSourceItem).where(
                *filters,
                RawSourceItem.knowledge_status == "PROCESSING",
                or_(RawSourceItem.lease_owner.is_(None), RawSourceItem.lease_expires_at.is_(None), RawSourceItem.lease_expires_at >= now),
            ),
        )
        completed = await self._count(
            session,
            select(func.count()).select_from(RawSourceItem).where(*filters, RawSourceItem.knowledge_status == "COMPLETED"),
        )
        failed = await self._count(
            session,
            select(func.count()).select_from(RawSourceItem).where(*filters, RawSourceItem.knowledge_status == "FAILED"),
        )
        reclaimable = await self._count(
            session,
            select(func.count()).select_from(RawSourceItem).where(
                *filters,
                RawSourceItem.knowledge_status == "PROCESSING",
                RawSourceItem.lease_owner.is_not(None),
                RawSourceItem.lease_expires_at.is_not(None),
                RawSourceItem.lease_expires_at < now,
            ),
        )
        return QueueHealthBucketRead(
            queue="raw_source_items",
            pending=pending,
            processing=processing,
            completed=completed,
            failed=failed,
            reclaimable=reclaimable,
        )

    async def _build_review_bucket(
        self,
        session: AsyncSession,
        now,
        tenant_id: str | None,
        preset_id: str | None,
    ) -> QueueHealthBucketRead:
        filters = self._optional_filters(ReviewItem, tenant_id, preset_id)
        pending = await self._count(
            session,
            select(func.count()).select_from(ReviewItem).where(
                *filters,
                ReviewItem.status == ReviewItemStatus.PENDING.value,
                ReviewItem.lease_owner.is_(None),
            ),
        )
        processing = await self._count(
            session,
            select(func.count()).select_from(ReviewItem).where(
                *filters,
                ReviewItem.status == ReviewItemStatus.PENDING.value,
                ReviewItem.lease_owner.is_not(None),
                or_(ReviewItem.lease_expires_at.is_(None), ReviewItem.lease_expires_at >= now),
            ),
        )
        completed = await self._count(
            session,
            select(func.count()).select_from(ReviewItem).where(
                *filters,
                ReviewItem.status.in_([ReviewItemStatus.ACCEPTED.value, ReviewItemStatus.REJECTED.value]),
            ),
        )
        reclaimable = await self._count(
            session,
            select(func.count()).select_from(ReviewItem).where(
                *filters,
                ReviewItem.status == ReviewItemStatus.PENDING.value,
                ReviewItem.lease_owner.is_not(None),
                ReviewItem.lease_expires_at.is_not(None),
                ReviewItem.lease_expires_at < now,
            ),
        )
        return QueueHealthBucketRead(
            queue="review_items",
            pending=pending,
            processing=processing,
            completed=completed,
            failed=0,
            reclaimable=reclaimable,
        )

    async def _build_simulation_bucket(
        self,
        session: AsyncSession,
        now,
        tenant_id: str | None,
        preset_id: str | None,
    ) -> QueueHealthBucketRead:
        filters = self._optional_filters(SimulationRun, tenant_id, preset_id)
        pending = await self._count(
            session,
            select(func.count()).select_from(SimulationRun).where(
                *filters,
                SimulationRun.status == SimulationRunStatus.PENDING.value,
            ),
        )
        processing = await self._count(
            session,
            select(func.count()).select_from(SimulationRun).where(
                *filters,
                SimulationRun.status == SimulationRunStatus.PROCESSING.value,
                or_(SimulationRun.lease_owner.is_(None), SimulationRun.lease_expires_at.is_(None), SimulationRun.lease_expires_at >= now),
            ),
        )
        completed = await self._count(
            session,
            select(func.count()).select_from(SimulationRun).where(
                *filters,
                SimulationRun.status == SimulationRunStatus.COMPLETED.value,
            ),
        )
        failed = await self._count(
            session,
            select(func.count()).select_from(SimulationRun).where(
                *filters,
                SimulationRun.status == SimulationRunStatus.FAILED.value,
            ),
        )
        reclaimable = await self._count(
            session,
            select(func.count()).select_from(SimulationRun).where(
                *filters,
                SimulationRun.status == SimulationRunStatus.PROCESSING.value,
                SimulationRun.lease_owner.is_not(None),
                SimulationRun.lease_expires_at.is_not(None),
                SimulationRun.lease_expires_at < now,
            ),
        )
        return QueueHealthBucketRead(
            queue="simulation_runs",
            pending=pending,
            processing=processing,
            completed=completed,
            failed=failed,
            reclaimable=reclaimable,
        )

    async def _build_review_reason_breakdown(
        self,
        session: AsyncSession,
        now,
        tenant_id: str | None,
        preset_id: str | None,
    ) -> list[ReviewQueueReasonRead]:
        filters = self._optional_filters(ReviewItem, tenant_id, preset_id)
        rows = (
            await session.execute(
                select(
                    ReviewItem.queue_reason,
                    ReviewItem.status,
                    ReviewItem.lease_owner,
                    ReviewItem.lease_expires_at,
                    func.count().label("count"),
                )
                .where(*filters)
                .group_by(
                    ReviewItem.queue_reason,
                    ReviewItem.status,
                    ReviewItem.lease_owner,
                    ReviewItem.lease_expires_at,
                )
            )
        ).all()

        grouped: dict[str, dict[str, int]] = defaultdict(
            lambda: {"pending": 0, "processing": 0, "completed": 0, "reclaimable": 0}
        )
        for queue_reason, status, lease_owner, lease_expires_at, count in rows:
            bucket = grouped[str(queue_reason)]
            if status in {ReviewItemStatus.ACCEPTED.value, ReviewItemStatus.REJECTED.value}:
                bucket["completed"] += int(count)
            elif lease_owner is None:
                bucket["pending"] += int(count)
            elif lease_expires_at is not None and lease_expires_at < now:
                bucket["reclaimable"] += int(count)
            else:
                bucket["processing"] += int(count)

        return [
            ReviewQueueReasonRead(queue_reason=queue_reason, **counts)
            for queue_reason, counts in sorted(grouped.items(), key=lambda item: item[0].lower())
        ]

    def _optional_filters(
        self,
        model: Any,
        tenant_id: str | None,
        preset_id: str | None,
    ) -> list[Any]:
        filters: list[Any] = []
        if tenant_id is not None and hasattr(model, "tenant_id"):
            filters.append(model.tenant_id == tenant_id)
        if preset_id is not None and hasattr(model, "preset_id"):
            filters.append(model.preset_id == preset_id)
        return filters

    async def _count(self, session: AsyncSession, query) -> int:
        return int((await session.scalar(query)) or 0)
