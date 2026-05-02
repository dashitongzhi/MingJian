from __future__ import annotations

from datetime import timedelta
from difflib import unified_diff
from typing import Any

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from planagent.config import Settings
from planagent.domain.enums import EventTopic, ExecutionMode, SimulationRunStatus
from planagent.domain.models import (
    Claim,
    DecisionOption,
    DecisionRecordRecord,
    EventArchive,
    Hypothesis,
    PredictionEvidenceLink,
    PredictionRevisionJob,
    PredictionSeries,
    PredictionVersion,
    SimulationRun,
    utc_now,
)
from planagent.events.bus import EventBus
from planagent.services.pipeline import normalize_text


class PredictionService:
    """预测版本管理服务——实现预测版本化、证据影响映射、修正任务编排。"""

    def __init__(self, settings: Settings, event_bus: EventBus) -> None:
        self.settings = settings
        self.event_bus = event_bus

    async def create_initial_versions_for_run(
        self,
        session: AsyncSession,
        run_id: str,
    ) -> list[PredictionVersion]:
        """模拟运行完成后，为 run 生成的 DecisionOption/Hypothesis 创建初始预测版本。"""
        run = await session.get(SimulationRun, run_id)
        if run is None:
            raise LookupError(f"Simulation run {run_id} was not found.")
        if run.configuration.get("base_prediction_version_id"):
            return []

        options = list(
            (
                await session.scalars(
                    select(DecisionOption)
                    .where(DecisionOption.run_id == run_id)
                    .order_by(DecisionOption.ranking.asc(), DecisionOption.created_at.asc())
                )
            ).all()
        )
        hypotheses = list(
            (
                await session.scalars(
                    select(Hypothesis)
                    .where(Hypothesis.run_id == run_id)
                    .order_by(Hypothesis.created_at.asc())
                )
            ).all()
        )
        hypotheses_by_option = {
            hypothesis.decision_option_id: hypothesis
            for hypothesis in hypotheses
            if hypothesis.decision_option_id is not None
        }

        created: list[PredictionVersion] = []
        option_ids = {option.id for option in options}
        for option in options:
            hypothesis = hypotheses_by_option.get(option.id)
            version = await self._create_initial_version(session, run, option, hypothesis)
            if version is not None:
                created.append(version)

        for hypothesis in hypotheses:
            if hypothesis.decision_option_id in option_ids:
                continue
            version = await self._create_initial_version(session, run, None, hypothesis)
            if version is not None:
                created.append(version)

        return created

    async def link_run_evidence(self, session: AsyncSession, run_id: str, version_id: str) -> int:
        """将 run 的 DecisionRecord 中的 evidence_ids 链接到预测版本。"""
        version = await session.get(PredictionVersion, version_id)
        if version is None:
            raise LookupError(f"Prediction version {version_id} was not found.")

        records = list(
            (
                await session.scalars(
                    select(DecisionRecordRecord)
                    .where(DecisionRecordRecord.run_id == run_id)
                    .order_by(DecisionRecordRecord.tick.asc(), DecisionRecordRecord.sequence.asc())
                )
            ).all()
        )
        linked = 0
        seen: set[str] = set()
        for record in records:
            for evidence_item_id in record.evidence_ids or []:
                if evidence_item_id in seen:
                    continue
                seen.add(evidence_item_id)
                if await self._create_evidence_link(
                    session,
                    series_id=version.series_id,
                    version_id=version.id,
                    evidence_item_id=evidence_item_id,
                    claim_id=None,
                    link_type="decision_trace",
                    impact_score=0.0,
                ):
                    linked += 1
        return linked

    async def enqueue_revisions_for_evidence(
        self,
        session: AsyncSession,
        claim_id: str,
        evidence_item_id: str,
        reason: str = "new_evidence",
    ) -> int:
        """当新证据/Claim 变化时，查找受影响的预测系列并创建修正任务。"""
        links = list(
            (
                await session.scalars(
                    select(PredictionEvidenceLink).where(
                        PredictionEvidenceLink.evidence_item_id == evidence_item_id
                    )
                )
            ).all()
        )
        if not links:
            return 0

        series_ids = sorted({link.series_id for link in links})
        series_list = list(
            (
                await session.scalars(
                    select(PredictionSeries).where(
                        PredictionSeries.id.in_(series_ids),
                        PredictionSeries.status == "ACTIVE",
                        PredictionSeries.current_version_id.is_not(None),
                    )
                )
            ).all()
        )

        created = 0
        for series in series_list:
            existing_job = (
                await session.scalars(
                    select(PredictionRevisionJob)
                    .where(
                        PredictionRevisionJob.series_id == series.id,
                        PredictionRevisionJob.status.in_(["PENDING", "PROCESSING"]),
                    )
                    .limit(1)
                )
            ).first()
            if existing_job is not None or series.current_version_id is None:
                continue

            job = PredictionRevisionJob(
                series_id=series.id,
                base_version_id=series.current_version_id,
                claim_id=claim_id or None,
                trigger_claim_id=claim_id or None,
                evidence_item_id=evidence_item_id,
                trigger_evidence_item_id=evidence_item_id,
                trigger_topic=reason,
                reason=reason,
                status="PENDING",
            )
            session.add(job)
            await session.flush()
            created += 1
            await self._publish_event(
                session,
                EventTopic.PREDICTION_REVISION_REQUESTED.value,
                {
                    "job_id": job.id,
                    "series_id": series.id,
                    "base_version_id": job.base_version_id,
                    "claim_id": claim_id,
                    "evidence_item_id": evidence_item_id,
                    "reason": reason,
                },
            )
        return created

    async def process_revision_jobs(
        self,
        session: AsyncSession,
        worker_id: str,
        limit: int = 5,
    ) -> int:
        """处理待执行的修正任务。"""
        jobs = await self._claim_revision_jobs(session, worker_id=worker_id, limit=limit)
        processed = 0
        for job in jobs:
            try:
                if job.status == "PENDING":
                    await self._start_revision_simulation(session, job)
                    processed += 1
                elif job.status == "PROCESSING":
                    processed += await self._finalize_revision_job(session, job)
            except Exception as exc:
                job.status = "FAILED"
                job.last_error = f"{type(exc).__name__}: {normalize_text(str(exc))[:300]}"
                job.lease_owner = None
                job.lease_expires_at = None
                job.updated_at = utc_now()
                processed += 1
        await session.commit()
        return processed

    async def compare_versions(
        self,
        session: AsyncSession,
        old_version_id: str,
        new_version_id: str,
    ) -> dict[str, Any]:
        """对比两个预测版本的差异。"""
        old_version = await session.get(PredictionVersion, old_version_id)
        new_version = await session.get(PredictionVersion, new_version_id)
        if old_version is None:
            raise LookupError(f"Prediction version {old_version_id} was not found.")
        if new_version is None:
            raise LookupError(f"Prediction version {new_version_id} was not found.")

        old_links = await self._version_evidence_ids(session, old_version.id)
        new_links = await self._version_evidence_ids(session, new_version.id)
        text_diff = "\n".join(
            unified_diff(
                old_version.prediction_text.splitlines(),
                new_version.prediction_text.splitlines(),
                fromfile=f"v{old_version.version_number}",
                tofile=f"v{new_version.version_number}",
                lineterm="",
            )
        )
        return {
            "probability_delta": self._numeric_delta(old_version.probability, new_version.probability),
            "confidence_delta": self._numeric_delta(old_version.confidence, new_version.confidence),
            "text_diff": text_diff,
            "status_change": {
                "old": old_version.status,
                "new": new_version.status,
            },
            "new_evidence_count": len(new_links - old_links),
        }

    async def _create_initial_version(
        self,
        session: AsyncSession,
        run: SimulationRun,
        option: DecisionOption | None,
        hypothesis: Hypothesis | None,
    ) -> PredictionVersion | None:
        source_type = "decision_option" if option is not None else "hypothesis"
        source_id = option.id if option is not None else hypothesis.id if hypothesis is not None else None
        if source_id is None:
            return None

        existing = (
            await session.scalars(
                select(PredictionSeries)
                .where(PredictionSeries.source_type == source_type, PredictionSeries.source_id == source_id)
                .limit(1)
            )
        ).first()
        if existing is not None:
            return None

        subject_type, subject_id = self._infer_subject(run)
        series = PredictionSeries(
            tenant_id=run.tenant_id,
            preset_id=run.preset_id,
            subject_type=subject_type,
            subject_id=subject_id,
            domain_id=run.domain_id,
            source_type=source_type,
            source_id=source_id,
            source_run_id=run.id,
            decision_option_id=option.id if option is not None else None,
            hypothesis_id=hypothesis.id if hypothesis is not None else None,
            status="ACTIVE",
            series_metadata={"domain_id": run.domain_id},
        )
        session.add(series)
        await session.flush()

        prediction_text = (
            hypothesis.prediction
            if hypothesis is not None
            else option.description if option is not None
            else "Prediction unavailable."
        )
        confidence = option.confidence if option is not None else None
        version = PredictionVersion(
            series_id=series.id,
            run_id=run.id,
            version_number=1,
            trigger_type="initial",
            hypothesis_id=hypothesis.id if hypothesis is not None else None,
            decision_option_id=option.id if option is not None else None,
            prediction_text=prediction_text,
            time_horizon=hypothesis.time_horizon if hypothesis is not None else "3_months",
            probability=confidence if confidence is not None else 0.5,
            confidence=confidence if confidence is not None else 0.5,
            status="ACTIVE",
            version_metadata={
                "decision_option_id": option.id if option is not None else None,
                "hypothesis_id": hypothesis.id if hypothesis is not None else None,
                "option_title": option.title if option is not None else None,
                "time_horizon": hypothesis.time_horizon if hypothesis is not None else None,
            },
        )
        session.add(version)
        await session.flush()
        series.current_version_id = version.id

        for evidence_item_id in option.evidence_ids if option is not None else []:
            await self._create_evidence_link(
                session,
                series_id=series.id,
                version_id=version.id,
                evidence_item_id=evidence_item_id,
                claim_id=None,
                link_type="initial",
                impact_score=0.0,
            )
        await self.link_run_evidence(session, run.id, version.id)
        await self._publish_version_created(session, version, series)
        return version

    async def _claim_revision_jobs(
        self,
        session: AsyncSession,
        worker_id: str,
        limit: int,
    ) -> list[PredictionRevisionJob]:
        now = utc_now()
        lease_expires_at = now + timedelta(seconds=self.settings.worker_lease_seconds)
        candidate_ids = list(
            (
                await session.scalars(
                    select(PredictionRevisionJob.id)
                    .where(
                        PredictionRevisionJob.status.in_(["PENDING", "PROCESSING"]),
                        or_(
                            PredictionRevisionJob.lease_expires_at.is_(None),
                            PredictionRevisionJob.lease_expires_at < now,
                        ),
                    )
                    .order_by(PredictionRevisionJob.created_at.asc())
                    .limit(limit * 3)
                )
            ).all()
        )
        claimed: list[PredictionRevisionJob] = []
        for job_id in candidate_ids:
            result = await session.execute(
                update(PredictionRevisionJob)
                .where(
                    PredictionRevisionJob.id == job_id,
                    PredictionRevisionJob.status.in_(["PENDING", "PROCESSING"]),
                    or_(
                        PredictionRevisionJob.lease_expires_at.is_(None),
                        PredictionRevisionJob.lease_expires_at < now,
                    ),
                )
                .values(
                    lease_owner=worker_id,
                    lease_expires_at=lease_expires_at,
                    processing_attempts=PredictionRevisionJob.processing_attempts + 1,
                    attempts=PredictionRevisionJob.attempts + 1,
                    updated_at=now,
                )
            )
            if result.rowcount:
                job = await session.get(PredictionRevisionJob, job_id)
                if job is not None:
                    claimed.append(job)
            if len(claimed) >= limit:
                break
        return claimed

    async def _start_revision_simulation(self, session: AsyncSession, job: PredictionRevisionJob) -> None:
        series = await session.get(PredictionSeries, job.series_id)
        if job.base_version_id is None:
            raise LookupError(f"Revision job {job.id} has no base version.")
        base_version = await session.get(PredictionVersion, job.base_version_id)
        if series is None or base_version is None or base_version.run_id is None:
            raise LookupError(f"Revision job {job.id} has no usable base prediction.")

        base_run = await session.get(SimulationRun, base_version.run_id)
        if base_run is None:
            raise LookupError(f"Base simulation run {base_version.run_id} was not found.")

        revision_run = SimulationRun(
            company_id=base_run.company_id,
            force_id=base_run.force_id,
            tenant_id=base_run.tenant_id,
            preset_id=base_run.preset_id,
            domain_id=base_run.domain_id,
            actor_template=base_run.actor_template,
            military_use_mode=base_run.military_use_mode,
            execution_mode=ExecutionMode.QUEUED.value,
            status=SimulationRunStatus.PENDING.value,
            tick_count=base_run.tick_count,
            seed=base_run.seed,
            configuration={
                **(base_run.configuration or {}),
                "revision_of_run_id": base_run.id,
                "prediction_series_id": series.id,
                "base_prediction_version_id": base_version.id,
                "revision_job_id": job.id,
                "revision_reason": job.reason,
                "revision_evidence_item_id": self._job_evidence_item_id(job),
                "revision_claim_id": self._job_claim_id(job),
                "base_prediction_text": base_version.prediction_text,
            },
            summary={"revision_job_id": job.id, "revision_of_run_id": base_run.id},
        )
        session.add(revision_run)
        await session.flush()
        job.revision_run_id = revision_run.id
        job.new_run_id = revision_run.id
        job.status = "PROCESSING"
        job.last_error = None
        job.lease_owner = None
        job.lease_expires_at = None
        job.updated_at = utc_now()

    async def _finalize_revision_job(self, session: AsyncSession, job: PredictionRevisionJob) -> int:
        if job.revision_run_id is None:
            raise LookupError(f"Revision job {job.id} has no revision run.")
        revision_run = await session.get(SimulationRun, job.revision_run_id)
        if revision_run is None:
            raise LookupError(f"Revision run {job.revision_run_id} was not found.")
        if revision_run.status == SimulationRunStatus.FAILED.value:
            job.status = "FAILED"
            job.last_error = revision_run.last_error or "Revision simulation failed."
            job.lease_owner = None
            job.lease_expires_at = None
            job.updated_at = utc_now()
            return 1
        if revision_run.status != SimulationRunStatus.COMPLETED.value:
            job.lease_owner = None
            job.lease_expires_at = None
            job.updated_at = utc_now()
            return 0

        series = await session.get(PredictionSeries, job.series_id)
        if job.base_version_id is None:
            raise LookupError(f"Revision job {job.id} has no base version.")
        base_version = await session.get(PredictionVersion, job.base_version_id)
        if series is None or base_version is None:
            raise LookupError(f"Revision job {job.id} has no usable series/base version.")

        existing = (
            await session.scalars(
                select(PredictionVersion)
                .where(
                    PredictionVersion.series_id == series.id,
                    PredictionVersion.run_id == revision_run.id,
                    PredictionVersion.trigger_type == "evidence_update",
                )
                .limit(1)
            )
        ).first()
        if existing is not None:
            job.status = "COMPLETED"
            job.completed_at = utc_now()
            job.lease_owner = None
            job.lease_expires_at = None
            return 1

        next_number = int(
            await session.scalar(
                select(func.coalesce(func.max(PredictionVersion.version_number), 0)).where(
                    PredictionVersion.series_id == series.id
                )
            )
            or 0
        ) + 1
        prediction_text, confidence, hypothesis_id, option_id, time_horizon = (
            await self._revision_prediction_text(session, revision_run, base_version)
        )

        await session.execute(
            update(PredictionVersion)
            .where(PredictionVersion.series_id == series.id, PredictionVersion.status == "ACTIVE")
            .values(status="SUPERSEDED", updated_at=utc_now())
        )
        version = PredictionVersion(
            series_id=series.id,
            run_id=revision_run.id,
            base_version_id=base_version.id,
            parent_version_id=base_version.id,
            version_number=next_number,
            trigger_type="evidence_update",
            trigger_ref_id=self._job_evidence_item_id(job),
            trigger_event_id=job.trigger_topic,
            hypothesis_id=hypothesis_id,
            decision_option_id=option_id,
            prediction_text=prediction_text,
            time_horizon=time_horizon,
            probability=confidence if confidence is not None else 0.5,
            confidence=confidence if confidence is not None else 0.5,
            status="ACTIVE",
            version_metadata={
                "revision_job_id": job.id,
                "base_run_id": base_version.run_id,
                "revision_run_id": revision_run.id,
                "reason": job.reason,
            },
        )
        session.add(version)
        await session.flush()
        series.current_version_id = version.id
        series.updated_at = utc_now()

        await self._create_evidence_link(
            session,
            series_id=series.id,
            version_id=version.id,
            evidence_item_id=self._job_evidence_item_id(job),
            claim_id=self._job_claim_id(job),
            link_type="revision_trigger",
            impact_score=1.0,
        )
        await self.link_run_evidence(session, revision_run.id, version.id)

        job.status = "COMPLETED"
        job.new_version_id = version.id
        job.completed_at = utc_now()
        job.last_error = None
        job.lease_owner = None
        job.lease_expires_at = None
        job.updated_at = utc_now()
        await self._publish_version_created(session, version, series)
        await self._publish_event(
            session,
            EventTopic.PREDICTION_REVISION_COMPLETED.value,
            {
                "job_id": job.id,
                "series_id": series.id,
                "base_version_id": base_version.id,
                "new_version_id": version.id,
                "revision_run_id": revision_run.id,
                "evidence_item_id": self._job_evidence_item_id(job),
                "claim_id": self._job_claim_id(job),
            },
        )
        return 1

    async def _revision_prediction_text(
        self,
        session: AsyncSession,
        revision_run: SimulationRun,
        base_version: PredictionVersion,
    ) -> tuple[str, float | None, str | None, str | None, str]:
        hypothesis = (
            await session.scalars(
                select(Hypothesis)
                .where(Hypothesis.run_id == revision_run.id)
                .order_by(Hypothesis.created_at.asc())
                .limit(1)
            )
        ).first()
        if hypothesis is not None:
            option = None
            if hypothesis.decision_option_id is not None:
                option = await session.get(DecisionOption, hypothesis.decision_option_id)
            return (
                hypothesis.prediction,
                option.confidence if option is not None else base_version.confidence,
                hypothesis.id,
                option.id if option is not None else None,
                hypothesis.time_horizon,
            )

        option = (
            await session.scalars(
                select(DecisionOption)
                .where(DecisionOption.run_id == revision_run.id)
                .order_by(DecisionOption.ranking.asc(), DecisionOption.created_at.asc())
                .limit(1)
            )
        ).first()
        if option is not None:
            return option.description, option.confidence, None, option.id, base_version.time_horizon
        return base_version.prediction_text, base_version.confidence, None, None, base_version.time_horizon

    async def _create_evidence_link(
        self,
        session: AsyncSession,
        series_id: str,
        version_id: str,
        evidence_item_id: str | None,
        claim_id: str | None,
        link_type: str,
        impact_score: float,
    ) -> bool:
        effective_claim_id = claim_id
        if effective_claim_id is None and evidence_item_id is not None:
            claim = (
                await session.scalars(
                    select(Claim)
                    .where(Claim.evidence_item_id == evidence_item_id)
                    .order_by(Claim.confidence.desc(), Claim.created_at.asc())
                    .limit(1)
                )
            ).first()
            effective_claim_id = claim.id if claim is not None else None
        existing = (
            await session.scalars(
                select(PredictionEvidenceLink)
                .where(
                    PredictionEvidenceLink.version_id == version_id,
                    PredictionEvidenceLink.evidence_item_id == evidence_item_id,
                    (
                        PredictionEvidenceLink.claim_id.is_(None)
                        if effective_claim_id is None
                        else PredictionEvidenceLink.claim_id == effective_claim_id
                    ),
                )
                .limit(1)
            )
        ).first()
        if existing is not None:
            return False
        session.add(
            PredictionEvidenceLink(
                series_id=series_id,
                version_id=version_id,
                prediction_version_id=version_id,
                evidence_item_id=evidence_item_id,
                claim_id=effective_claim_id,
                link_type=link_type,
                impact_score=impact_score,
            )
        )
        await session.flush()
        return True

    async def _version_evidence_ids(self, session: AsyncSession, version_id: str) -> set[str]:
        evidence_ids = (
            (
                await session.scalars(
                    select(PredictionEvidenceLink.evidence_item_id).where(
                        PredictionEvidenceLink.version_id == version_id
                    )
                )
            ).all()
        )
        return {evidence_id for evidence_id in evidence_ids if evidence_id is not None}

    async def _publish_version_created(
        self,
        session: AsyncSession,
        version: PredictionVersion,
        series: PredictionSeries,
    ) -> None:
        await self._publish_event(
            session,
            EventTopic.PREDICTION_VERSION_CREATED.value,
            {
                "series_id": series.id,
                "version_id": version.id,
                "version_number": version.version_number,
                "run_id": version.run_id,
                "trigger_type": version.trigger_type,
                "tenant_id": series.tenant_id,
                "preset_id": series.preset_id,
            },
        )

    async def _publish_event(self, session: AsyncSession, topic: str, payload: dict[str, Any]) -> None:
        session.add(EventArchive(topic=topic, payload=payload))
        await self.event_bus.publish(topic, payload)

    def _job_evidence_item_id(self, job: PredictionRevisionJob) -> str | None:
        return job.evidence_item_id or job.trigger_evidence_item_id

    def _job_claim_id(self, job: PredictionRevisionJob) -> str | None:
        return job.claim_id or job.trigger_claim_id

    def _infer_subject(self, run: SimulationRun) -> tuple[str, str | None]:
        if run.domain_id == "corporate":
            return "company", run.company_id
        if run.domain_id == "military":
            return "force", run.force_id
        return run.domain_id, run.company_id or run.force_id

    def _numeric_delta(self, old_value: float | None, new_value: float | None) -> float | None:
        if old_value is None or new_value is None:
            return None
        return round(float(new_value) - float(old_value), 6)
