from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import or_, update
from sqlalchemy.ext.asyncio import AsyncSession

from planagent.config import Settings
from planagent.domain.api import SimulationRunCreate
from planagent.domain.models import WatchRule
from planagent.services.debate import DebateCommand, DebateTarget, DebateWorkflow
from planagent.services.simulation import SimulationService

MIN_WATCH_EXECUTION_LEASE_SECONDS = 15 * 60


class WatchExecutionLeaseLostError(RuntimeError):
    pass


@dataclass(frozen=True)
class WatchActionResult:
    simulation_run_id: str | None = None
    debate_id: str | None = None


def new_watch_execution_owner(prefix: str) -> str:
    return f"{prefix}:{uuid4().hex}"


def watch_execution_lease_expires_at(settings: Settings, now: datetime) -> datetime:
    lease_seconds = max(settings.worker_lease_seconds, MIN_WATCH_EXECUTION_LEASE_SECONDS)
    return now + timedelta(seconds=lease_seconds)


class WatchExecutionLeaseManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def claim_manual(
        self,
        session: AsyncSession,
        rule_id: str,
        owner: str,
        now: datetime,
    ) -> bool:
        return await self._claim(session, rule_id, owner, now, due_only=False)

    async def claim_due(
        self,
        session: AsyncSession,
        rule_id: str,
        owner: str,
        now: datetime,
    ) -> bool:
        return await self._claim(session, rule_id, owner, now, due_only=True)

    async def complete(
        self,
        session: AsyncSession,
        rule_id: str,
        owner: str,
        *,
        completed_at: datetime,
        next_poll_at: datetime | None,
    ) -> bool:
        result = await session.execute(
            update(WatchRule)
            .where(
                WatchRule.id == rule_id,
                WatchRule.lease_owner == owner,
            )
            .values(
                enabled=next_poll_at is not None,
                last_poll_at=completed_at,
                last_poll_error=None,
                lease_owner=None,
                lease_expires_at=None,
                next_poll_at=next_poll_at,
                updated_at=completed_at,
            )
            .execution_options(synchronize_session=False)
        )
        return bool(result.rowcount)

    async def fail(
        self,
        session: AsyncSession,
        rule_id: str,
        owner: str,
        *,
        error: str,
        failed_at: datetime,
        enabled: bool,
        next_poll_at: datetime | None,
    ) -> bool:
        result = await session.execute(
            update(WatchRule)
            .where(
                WatchRule.id == rule_id,
                WatchRule.lease_owner == owner,
            )
            .values(
                enabled=enabled,
                lease_owner=None,
                lease_expires_at=None,
                last_poll_error=error,
                next_poll_at=next_poll_at,
                updated_at=failed_at,
            )
            .execution_options(synchronize_session=False)
        )
        return bool(result.rowcount)

    async def _claim(
        self,
        session: AsyncSession,
        rule_id: str,
        owner: str,
        now: datetime,
        *,
        due_only: bool,
    ) -> bool:
        conditions = [
            WatchRule.id == rule_id,
            or_(
                WatchRule.lease_owner.is_(None),
                WatchRule.lease_expires_at < now,
            ),
        ]
        if due_only:
            conditions.extend(
                [
                    WatchRule.enabled.is_(True),
                    WatchRule.next_poll_at.is_not(None),
                    WatchRule.next_poll_at <= now,
                ]
            )
        result = await session.execute(
            update(WatchRule)
            .where(*conditions)
            .values(
                poll_attempts=WatchRule.poll_attempts + 1,
                lease_owner=owner,
                lease_expires_at=watch_execution_lease_expires_at(self.settings, now),
                last_poll_error=None,
                updated_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        return bool(result.rowcount)


class WatchExecutionService:
    def __init__(
        self,
        simulation_service: SimulationService,
        debate_workflow: DebateWorkflow,
    ) -> None:
        self.simulation_service = simulation_service
        self.debate_workflow = debate_workflow

    async def run_actions(
        self,
        session: AsyncSession,
        rule: WatchRule,
        *,
        should_run: bool,
        debate_context: tuple[str, ...] = (),
    ) -> WatchActionResult:
        if not rule.auto_trigger_simulation or not should_run:
            return WatchActionResult()

        simulation_run = await self.simulation_service.create_simulation_run(
            session,
            self._simulation_payload(rule),
        )
        if not rule.auto_trigger_debate:
            return WatchActionResult(simulation_run_id=simulation_run.id)

        debate = await self.debate_workflow.decide(
            session,
            DebateCommand(
                target=DebateTarget.run(simulation_run.id),
                topic=f"Should the posture for {rule.query} be adjusted?",
                trigger_type="pivot_decision",
                context=debate_context,
                domain_id=rule.domain_id,
            ),
        )
        return WatchActionResult(
            simulation_run_id=simulation_run.id,
            debate_id=debate.id,
        )

    def _simulation_payload(self, rule: WatchRule) -> SimulationRunCreate:
        if rule.domain_id == "military":
            return SimulationRunCreate(
                domain_id="military",
                force_id=rule.query[:40].lower().replace(" ", "-"),
                force_name=rule.query[:60],
                theater="contested-theater",
                tick_count=rule.tick_count or None,
                tenant_id=rule.tenant_id,
                preset_id=rule.preset_id,
            )
        return SimulationRunCreate(
            domain_id="corporate",
            company_id=rule.query[:40].lower().replace(" ", "-"),
            company_name=rule.query[:60],
            market="ai",
            tick_count=rule.tick_count or None,
            tenant_id=rule.tenant_id,
            preset_id=rule.preset_id,
        )
