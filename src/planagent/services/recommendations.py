from __future__ import annotations

from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from planagent.domain.models import (
    RecommendationVersion,
    SourceCursorState,
    StrategicSession,
    utc_now,
)


class RecommendationVersionService:
    """Persistent recommendation timeline for Community strategic sessions."""

    async def create_version(
        self,
        session: AsyncSession,
        *,
        session_id: str,
        recommendation_summary: str,
        trigger_type: str,
        watch_rule_id: str | None = None,
        tenant_id: str | None = None,
        preset_id: str | None = None,
        trigger_source_change_id: str | None = None,
        source_change_ids: list[str] | None = None,
        significance: str = "none",
        change_summary: str | None = None,
        result_payload: dict[str, Any] | None = None,
        source_snapshot: list[dict[str, Any]] | None = None,
        ingest_run_id: str | None = None,
        simulation_run_id: str | None = None,
        debate_id: str | None = None,
    ) -> RecommendationVersion:
        await self._lock_timeline(session, session_id)
        version_number = await self._next_version_number(session, session_id)
        record = RecommendationVersion(
            session_id=session_id,
            watch_rule_id=watch_rule_id,
            tenant_id=tenant_id,
            preset_id=preset_id,
            version_number=version_number,
            trigger_type=trigger_type,
            trigger_source_change_id=trigger_source_change_id,
            source_change_ids=source_change_ids or [],
            significance=significance,
            change_summary=change_summary,
            recommendation_summary=recommendation_summary,
            result_payload=result_payload or {},
            source_snapshot=source_snapshot or [],
            ingest_run_id=ingest_run_id,
            simulation_run_id=simulation_run_id,
            debate_id=debate_id,
            generated_at=utc_now(),
        )
        session.add(record)
        await session.flush()
        return record

    async def list_versions(
        self,
        session: AsyncSession,
        *,
        session_id: str,
        limit: int = 50,
    ) -> list[RecommendationVersion]:
        rows = await session.scalars(
            select(RecommendationVersion)
            .where(RecommendationVersion.session_id == session_id)
            .order_by(RecommendationVersion.version_number.desc())
            .limit(limit)
        )
        return list(rows.all())

    async def source_snapshot(
        self,
        session: AsyncSession,
        *,
        watch_rule_id: str | None,
    ) -> list[dict[str, Any]]:
        if watch_rule_id is None:
            return []
        rows = await session.scalars(
            select(SourceCursorState)
            .where(SourceCursorState.watch_rule_id == watch_rule_id)
            .order_by(SourceCursorState.source_type.asc(), SourceCursorState.updated_at.desc())
        )
        return [
            {
                "id": row.id,
                "source_type": row.source_type,
                "source_url_or_query": row.source_url_or_query,
                "health_status": row.health_status,
                "last_checked_at": row.last_checked_at.isoformat()
                if row.last_checked_at is not None
                else None,
                "last_success_at": row.last_success_at.isoformat()
                if row.last_success_at is not None
                else None,
                "last_failure_at": row.last_failure_at.isoformat()
                if row.last_failure_at is not None
                else None,
                "last_change_at": row.last_change_at.isoformat()
                if row.last_change_at is not None
                else None,
                "consecutive_failures": row.consecutive_failures,
            }
            for row in rows.all()
        ]

    async def _lock_timeline(self, session: AsyncSession, session_id: str) -> None:
        bind = session.get_bind()
        if bind.dialect.name == "sqlite":
            result = await session.execute(
                text("UPDATE strategic_sessions SET id = id WHERE id = :session_id"),
                {"session_id": session_id},
            )
            found = result.rowcount == 1
        else:
            found = (
                await session.scalar(
                    select(StrategicSession.id)
                    .where(StrategicSession.id == session_id)
                    .with_for_update()
                )
            ) is not None
        if not found:
            raise ValueError(f"Strategic session {session_id} not found.")

    async def _next_version_number(self, session: AsyncSession, session_id: str) -> int:
        current = await session.scalar(
            select(func.max(RecommendationVersion.version_number)).where(
                RecommendationVersion.session_id == session_id
            )
        )
        return int(current or 0) + 1
