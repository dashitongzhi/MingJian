from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from planagent.config import Settings
from planagent.db import get_database
from planagent.domain.enums import EventTopic
from planagent.domain.models import Claim
from planagent.events.bus import EventBus
from planagent.services.openai_client import OpenAIService
from planagent.services.prediction import PredictionService
from planagent.simulation.rules import RuleRegistry
from planagent.workers.base import Worker, WorkerDescription


class PredictionRevisionWorker(Worker):
    description = WorkerDescription(
        worker_id="prediction-revision-worker",
        summary=(
            "Processes prediction revision jobs: triggers re-simulation when new evidence "
            "affects active predictions."
        ),
        consumes=(
            EventTopic.KNOWLEDGE_EXTRACTED.value,
            EventTopic.EVIDENCE_CREATED.value,
            EventTopic.EVIDENCE_UPDATED.value,
            EventTopic.PREDICTION_REVISION_REQUESTED.value,
            "evidence.added",
        ),
        produces=(
            EventTopic.PREDICTION_VERSION_CREATED.value,
            EventTopic.PREDICTION_REVISION_COMPLETED.value,
            EventTopic.PREDICTION_REVISION_FAILED.value,
        ),
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
        self.rule_registry = rule_registry
        self.openai_service = openai_service
        self.worker_instance_id = self.description.worker_id
        self.uses_internal_event_consumer = True
        self.prediction_service = PredictionService(settings, event_bus)

    async def run_once(self) -> dict[str, object]:
        """每轮执行：先消费事件触发 enqueue，再处理 job 队列。"""
        database = get_database(self.settings.database_url)
        errors: list[str] = []
        async with database.session() as session:
            enqueued, event_errors = await self._consume_revision_events(session)
            processed = await self.prediction_service.process_revision_jobs(
                session,
                worker_id=self.description.worker_id,
                limit=5,
            )
            errors.extend(event_errors)

        return {"enqueued": enqueued, "processed": processed, "errors": errors}

    async def _consume_revision_events(self, session: AsyncSession) -> tuple[int, list[str]]:
        events = await self.event_bus.reclaim_pending(
            topics=list(self.description.consumes),
            group=self.description.worker_id,
            consumer=self.worker_instance_id,
            min_idle_ms=60_000,
            count=25,
        )
        if not events:
            events = await self.event_bus.consume(
                topics=list(self.description.consumes),
                group=self.description.worker_id,
                consumer=self.worker_instance_id,
                count=25,
                block_ms=0,
            )
        enqueued = 0
        errors: list[str] = []
        for event in events:
            try:
                enqueued += await self._enqueue_from_payload(session, event.payload)
                await self.event_bus.ack(event.topic, self.description.worker_id, event.message_id)
            except Exception as exc:
                errors.append(f"{event.topic}:{event.message_id}:{type(exc).__name__}:{exc}")
                await self.event_bus.publish_dead_letter(
                    event.topic,
                    {
                        "group": self.description.worker_id,
                        "consumer": self.worker_instance_id,
                        "message_id": event.message_id,
                        "payload": event.payload,
                        "error": str(exc),
                    },
                )
                await self.event_bus.ack(event.topic, self.description.worker_id, event.message_id)
        if enqueued:
            await session.commit()
        return enqueued, errors

    async def _enqueue_from_payload(self, session: AsyncSession, payload: dict) -> int:
        claim_id = payload.get("claim_id")
        evidence_item_id = payload.get("evidence_item_id")
        reason = payload.get("reason") or "new_evidence"

        if claim_id and not evidence_item_id:
            claim = await session.get(Claim, claim_id)
            if claim is None:
                return 0
            evidence_item_id = claim.evidence_item_id

        if evidence_item_id and not claim_id:
            claims = list(
                (
                    await session.scalars(
                        select(Claim)
                        .where(Claim.evidence_item_id == evidence_item_id)
                        .order_by(Claim.confidence.desc(), Claim.created_at.asc())
                    )
                ).all()
            )
            if not claims:
                return await self.prediction_service.enqueue_revisions_for_evidence(
                    session,
                    claim_id="",
                    evidence_item_id=evidence_item_id,
                    reason=reason,
                )
            created = 0
            for claim in claims:
                created += await self.prediction_service.enqueue_revisions_for_evidence(
                    session,
                    claim_id=claim.id,
                    evidence_item_id=evidence_item_id,
                    reason=reason,
                )
            return created

        if not evidence_item_id:
            return 0
        return await self.prediction_service.enqueue_revisions_for_evidence(
            session,
            claim_id=claim_id or "",
            evidence_item_id=evidence_item_id,
            reason=reason,
        )
