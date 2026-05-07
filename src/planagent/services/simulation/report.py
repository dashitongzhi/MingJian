from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from planagent.domain.enums import EventTopic
from planagent.domain.models import (
    DecisionRecordRecord,
    EventArchive,
    GeneratedReport,
    SimulationRun,
    utc_now,
)
from planagent.services.pipeline import normalize_text
from planagent.services.startup import normalize_tenant_id


class SimulationReportMixin:
    async def _build_report(self, session: AsyncSession, run: SimulationRun) -> GeneratedReport:
        return await self._generate_report(session, run)

    def _format_results(self, run: SimulationRun) -> dict[str, Any]:
        return {
            "run_id": run.id,
            "domain_id": run.domain_id,
            "status": run.status,
            "summary": dict(run.summary),
        }

    async def generate_pending_reports(
        self,
        session: AsyncSession,
        limit: int = 10,
        worker_id: str | None = None,
    ) -> int:
        runs = await self._claim_report_runs(
            session,
            limit=limit,
            worker_id=worker_id or "report-worker",
        )
        generated = 0
        for run in runs:
            try:
                await self._generate_report(session, run)
                run.last_error = None
                generated += 1
            except Exception as exc:
                run.last_error = f"{type(exc).__name__}: {normalize_text(str(exc))[:300]}"
            finally:
                run.lease_owner = None
                run.lease_expires_at = None
                run.updated_at = utc_now()
        await session.commit()
        return generated

    async def list_decision_trace(
        self,
        session: AsyncSession,
        run_id: str,
    ) -> list[DecisionRecordRecord]:
        return list(
            (
                await session.scalars(
                    select(DecisionRecordRecord)
                    .where(DecisionRecordRecord.run_id == run_id)
                    .order_by(DecisionRecordRecord.tick.asc(), DecisionRecordRecord.sequence.asc())
                )
            ).all()
        )

    async def latest_company_report(
        self,
        session: AsyncSession,
        company_id: str,
        tenant_id: str | None = None,
    ) -> GeneratedReport | None:
        normalized_tenant = normalize_tenant_id(tenant_id)
        query = select(GeneratedReport).where(GeneratedReport.company_id == company_id)
        if normalized_tenant is not None:
            query = query.where(GeneratedReport.tenant_id == normalized_tenant)
        return (await session.scalars(query.order_by(GeneratedReport.created_at.desc()))).first()

    async def latest_military_report(
        self,
        session: AsyncSession,
        scenario_id: str,
    ) -> GeneratedReport | None:
        return await self.latest_scenario_report(session, scenario_id)

    async def latest_scenario_report(
        self,
        session: AsyncSession,
        scenario_id: str,
    ) -> GeneratedReport | None:
        return (
            await session.scalars(
                select(GeneratedReport)
                .where(GeneratedReport.scenario_id == scenario_id)
                .order_by(GeneratedReport.created_at.desc())
            )
        ).first()

    async def _latest_run_report(
        self,
        session: AsyncSession,
        run_id: str,
    ) -> GeneratedReport | None:
        return (
            await session.scalars(
                select(GeneratedReport)
                .where(GeneratedReport.run_id == run_id)
                .order_by(GeneratedReport.created_at.desc())
                .limit(1)
            )
        ).first()

    def _report_recommendations(self, report: GeneratedReport | None) -> list[str]:
        if report is None:
            return []
        recommendations = report.sections.get("strategy_recommendations", [])
        return [str(item) for item in recommendations[:3]]

    async def _generate_report(self, session: AsyncSession, run: SimulationRun) -> GeneratedReport:
        report = await self.report_service.generate_report(session, run)
        run.summary = {**run.summary, "report_id": report.id}
        payload = {
            "run_id": run.id,
            "report_id": report.id,
            "company_id": run.company_id,
            "force_id": run.force_id,
            "scenario_id": report.scenario_id,
        }
        session.add(EventArchive(topic=EventTopic.REPORT_GENERATED.value, payload=payload))
        await self.event_bus.publish(EventTopic.REPORT_GENERATED.value, payload)
        return report
