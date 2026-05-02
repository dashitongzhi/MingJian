from __future__ import annotations

from sqlalchemy import select

from planagent.config import Settings
from planagent.db import get_database
from planagent.domain.enums import ClaimStatus, EventTopic
from planagent.domain.models import Claim, utc_now
from planagent.events.bus import EventBus
from planagent.services.openai_client import OpenAIService
from planagent.services.pipeline import PhaseOnePipelineService, normalize_text
from planagent.workers.base import Worker, WorkerDescription

_TOKEN_RE = __import__("re").compile(r"[a-z0-9]+")
_CLAIM_DIRECTION_POSITIVE = {
    "increase", "increased", "improve", "improved", "grow", "grew",
    "gain", "gained", "ship", "shipped", "launch", "launched",
    "deploy", "deployed", "restore", "restored", "rise", "rose",
    "support", "supported", "open", "opened",
}
_CLAIM_DIRECTION_NEGATIVE = {
    "decrease", "decreased", "decline", "declined", "drop", "dropped",
    "fall", "fell", "delay", "delayed", "cancel", "canceled",
    "block", "blocked", "disrupt", "disrupted", "reduce", "reduced",
    "damage", "damaged", "loss", "losses", "reject", "rejected",
    "withdraw", "withdrew",
}


class KnowledgeWorker(Worker):
    description = WorkerDescription(
        worker_id="knowledge-worker",
        summary="Processes staged raw items into evidence, claims, and review queue artifacts. Re-evaluates related claims when new evidence arrives.",
        consumes=(EventTopic.RAW_INGESTED.value,),
        produces=(
            EventTopic.EVIDENCE_CREATED.value,
            EventTopic.CLAIM_REVIEW_REQUESTED.value,
            EventTopic.KNOWLEDGE_EXTRACTED.value,
            EventTopic.EVIDENCE_UPDATED.value,
        ),
    )

    def __init__(
        self,
        settings: Settings,
        event_bus: EventBus,
        openai_service: OpenAIService | None = None,
    ) -> None:
        self.settings = settings
        self.event_bus = event_bus
        self.openai_service = openai_service
        self.worker_instance_id = self.description.worker_id
        self.service = PhaseOnePipelineService(settings, event_bus, openai_service)

    async def run_once(self) -> dict[str, object]:
        database = get_database(self.settings.database_url)
        errors: list[str] = []
        async with database.session() as session:
            processed_items, completed_runs = await self.service.process_pending_knowledge(
                session,
                worker_id=self.worker_instance_id,
            )
            reevaluated, re_errors = await self._reevaluate_related_claims(session)
            errors = re_errors
        return {
            "processed_items": processed_items,
            "completed_runs": completed_runs,
            "reevaluated_claims": reevaluated,
            "errors": errors,
        }

    async def _reevaluate_related_claims(self, session) -> tuple[int, list[str]]:
        recent_claims = list(
            (
                await session.scalars(
                    select(Claim)
                    .where(
                        Claim.status.in_([
                            ClaimStatus.ACCEPTED.value,
                            ClaimStatus.PENDING_REVIEW.value,
                        ]),
                    )
                    .order_by(Claim.updated_at.desc())
                    .limit(20)
                )
            ).all()
        )
        if not recent_claims:
            return 0, []

        reevaluated = 0
        errors: list[str] = []
        for claim in recent_claims:
            try:
                base_tokens = self._claim_tokens(claim.statement)
                if not base_tokens:
                    continue

                candidates = list(
                    (
                        await session.scalars(
                            select(Claim)
                            .where(
                                Claim.id != claim.id,
                                Claim.evidence_item_id != claim.evidence_item_id,
                                Claim.status.in_([
                                    ClaimStatus.ACCEPTED.value,
                                    ClaimStatus.PENDING_REVIEW.value,
                                ]),
                            )
                            .order_by(Claim.updated_at.desc())
                            .limit(50)
                        )
                    ).all()
                )

                base_direction = self._claim_direction(claim.statement)
                supportive_count = 0
                conflicting_count = 0
                max_support_confidence = 0.0
                max_conflict_confidence = 0.0

                for candidate in candidates:
                    similarity = self._claim_similarity(base_tokens, self._claim_tokens(candidate.statement))
                    subject_match = normalize_text(candidate.subject).lower() == normalize_text(claim.subject).lower()
                    threshold = 0.2 if subject_match else 0.3
                    if similarity < threshold:
                        continue

                    candidate_direction = self._claim_direction(candidate.statement)
                    if base_direction != 0 and candidate_direction != 0 and base_direction != candidate_direction:
                        conflicting_count += 1
                        max_conflict_confidence = max(max_conflict_confidence, float(candidate.confidence))
                    else:
                        supportive_count += 1
                        max_support_confidence = max(max_support_confidence, float(candidate.confidence))

                if supportive_count == 0 and conflicting_count == 0:
                    continue

                old_confidence = float(claim.confidence)
                new_confidence = self._recalculate_confidence(
                    old_confidence, supportive_count, conflicting_count,
                    max_support_confidence, max_conflict_confidence,
                )
                new_confidence = round(max(0.1, min(0.98, new_confidence)), 4)

                if abs(new_confidence - old_confidence) < 0.01:
                    continue

                old_status = claim.status
                claim.confidence = new_confidence

                if new_confidence >= self.settings.accepted_claim_confidence and old_status != ClaimStatus.ACCEPTED.value:
                    claim.status = ClaimStatus.ACCEPTED.value
                    claim.requires_review = False
                elif (
                    new_confidence < self.settings.review_claim_confidence_floor
                    and old_status == ClaimStatus.ACCEPTED.value
                ):
                    claim.status = ClaimStatus.PENDING_REVIEW.value
                    claim.requires_review = True

                claim.updated_at = utc_now()
                reevaluated += 1

                await self.event_bus.publish(
                    EventTopic.EVIDENCE_UPDATED.value,
                    {
                        "claim_id": claim.id,
                        "evidence_item_id": claim.evidence_item_id,
                        "old_confidence": old_confidence,
                        "new_confidence": new_confidence,
                        "old_status": old_status,
                        "new_status": claim.status,
                        "supportive_count": supportive_count,
                        "conflicting_count": conflicting_count,
                    },
                )
                await self.event_bus.publish(
                    EventTopic.KNOWLEDGE_EXTRACTED.value,
                    {
                        "claim_id": claim.id,
                        "evidence_item_id": claim.evidence_item_id,
                        "tenant_id": claim.tenant_id,
                        "preset_id": claim.preset_id,
                    },
                )
            except Exception as exc:
                errors.append(f"claim:{claim.id}:{type(exc).__name__}:{exc}")

        if reevaluated > 0:
            await session.commit()
        return reevaluated, errors

    def _claim_tokens(self, statement: str) -> set[str]:
        normalized = normalize_text(statement).lower()
        return {
            token
            for token in _TOKEN_RE.findall(normalized)
            if len(token) > 2
        }

    def _claim_similarity(self, base_tokens: set[str], candidate_tokens: set[str]) -> float:
        if not base_tokens or not candidate_tokens:
            return 0.0
        overlap = len(base_tokens & candidate_tokens)
        union = len(base_tokens | candidate_tokens)
        return overlap / union if union else 0.0

    def _claim_direction(self, statement: str) -> int:
        tokens = set(_TOKEN_RE.findall(normalize_text(statement).lower()))
        positive = len(tokens & _CLAIM_DIRECTION_POSITIVE)
        negative = len(tokens & _CLAIM_DIRECTION_NEGATIVE)
        if positive > negative:
            return 1
        if negative > positive:
            return -1
        return 0

    def _recalculate_confidence(
        self,
        base: float,
        supportive: int,
        conflicting: int,
        max_support: float,
        max_conflict: float,
    ) -> float:
        delta = 0.0
        delta += 0.05 * supportive
        delta += max_support * 0.10
        delta -= 0.05 * conflicting
        delta -= max_conflict * 0.12
        return base + delta
