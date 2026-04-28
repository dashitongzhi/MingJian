from __future__ import annotations

from datetime import timedelta

from sqlalchemy import or_, select, update

from planagent.config import Settings
from planagent.db import get_database
from planagent.domain.models import StrategicSession, utc_now
from planagent.events.bus import EventBus
from planagent.services.analysis import AutomatedAnalysisService
from planagent.services.assistant import StrategicAssistantService
from planagent.services.debate import DebateService
from planagent.services.openai_client import OpenAIService
from planagent.services.pipeline import PhaseOnePipelineService
from planagent.services.simulation import SimulationService
from planagent.services.workbench import WorkbenchService
from planagent.simulation.rules import RuleRegistry
from planagent.workers.base import Worker, WorkerDescription


class StrategicWatchWorker(Worker):
    description = WorkerDescription(
        worker_id="strategic-watch-worker",
        summary="Refreshes saved strategic sessions that are due for their next daily brief.",
        consumes=(),
        produces=(),
    )

    def __init__(
        self,
        settings: Settings,
        event_bus: EventBus,
        rule_registry: RuleRegistry,
        openai_service: OpenAIService | None = None,
    ) -> None:
        self.settings = settings
        self.event_bus = event_bus
        self.openai_service = openai_service
        self.worker_instance_id = self.description.worker_id
        analysis_service = AutomatedAnalysisService(settings, openai_service)
        pipeline_service = PhaseOnePipelineService(settings, event_bus, openai_service)
        simulation_service = SimulationService(settings, event_bus, rule_registry, openai_service)
        debate_service = DebateService(settings, event_bus, openai_service)
        self.service = StrategicAssistantService(
            analysis_service=analysis_service,
            pipeline_service=pipeline_service,
            simulation_service=simulation_service,
            debate_service=debate_service,
            workbench_service=WorkbenchService(),
        )

    async def run_once(self) -> dict[str, object]:
        database = get_database(self.settings.database_url)
        async with database.session() as session:
            claimed_sessions = await self._claim_due_sessions(
                session,
                limit=10,
                worker_id=self.worker_instance_id,
            )
            refreshed = 0
            failed = 0
            for session_record in claimed_sessions:
                try:
                    payload = await self.service.load_session_payload(session, session_record.id)
                    if payload is None:
                        await self._mark_failure(session, session_record.id, "session_not_found")
                        failed += 1
                        continue
                    await self.service.daily_brief(session, payload)
                    refreshed += 1
                except Exception as exc:
                    await self._mark_failure(
                        session,
                        session_record.id,
                        f"{type(exc).__name__}: {' '.join(str(exc).split())[:300]}",
                    )
                    failed += 1

        return {
            "claimed_sessions": len(claimed_sessions),
            "refreshed_sessions": refreshed,
            "failed_sessions": failed,
        }

    async def _claim_due_sessions(
        self,
        session,
        limit: int,
        worker_id: str,
    ) -> list[StrategicSession]:
        now = utc_now()
        lease_expires_at = now + timedelta(seconds=self.settings.worker_lease_seconds)
        candidate_ids = list(
            (
                await session.scalars(
                    select(StrategicSession.id)
                    .where(
                        StrategicSession.auto_refresh_enabled.is_(True),
                        StrategicSession.next_refresh_at.is_not(None),
                        StrategicSession.next_refresh_at <= now,
                        or_(
                            StrategicSession.refresh_lease_expires_at.is_(None),
                            StrategicSession.refresh_lease_expires_at < now,
                        ),
                    )
                    .order_by(StrategicSession.next_refresh_at.asc())
                    .limit(limit * 3)
                )
            ).all()
        )
        claimed: list[StrategicSession] = []
        for session_id in candidate_ids:
            result = await session.execute(
                update(StrategicSession)
                .where(
                    StrategicSession.id == session_id,
                    StrategicSession.auto_refresh_enabled.is_(True),
                    StrategicSession.next_refresh_at.is_not(None),
                    StrategicSession.next_refresh_at <= now,
                    or_(
                        StrategicSession.refresh_lease_expires_at.is_(None),
                        StrategicSession.refresh_lease_expires_at < now,
                    ),
                )
                .values(
                    refresh_lease_owner=worker_id,
                    refresh_lease_expires_at=lease_expires_at,
                    refresh_attempts=StrategicSession.refresh_attempts + 1,
                    last_refresh_error=None,
                    updated_at=now,
                )
            )
            if result.rowcount:
                record = await session.get(StrategicSession, session_id)
                if record is not None:
                    claimed.append(record)
            if len(claimed) >= limit:
                break
        return claimed

    async def _mark_failure(self, session, session_id: str, error: str) -> None:
        now = utc_now()
        retry_at = now + timedelta(hours=1)
        await session.execute(
            update(StrategicSession)
            .where(StrategicSession.id == session_id)
            .values(
                refresh_lease_owner=None,
                refresh_lease_expires_at=None,
                last_refresh_error=error,
                next_refresh_at=retry_at,
                updated_at=now,
            )
        )
        await session.commit()
