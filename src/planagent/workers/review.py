from __future__ import annotations

from datetime import timedelta

from sqlalchemy import or_, select, update

from planagent.config import Settings
from planagent.db import get_database
from planagent.domain.api import ReviewDecisionRequest
from planagent.domain.enums import ClaimStatus, EventTopic, ReviewItemStatus
from planagent.domain.models import (
    Claim,
    DebateSessionRecord,
    DebateVerdictRecord,
    ReviewItem,
    utc_now,
)
from planagent.events.bus import EventBus
from planagent.services.debate import DebateCommand, DebateService, DebateTarget
from planagent.services.openai_client import OpenAIService
from planagent.services.pipeline import PhaseOnePipelineService
from planagent.workers.base import Worker, WorkerDescription


class ReviewWorker(Worker):
    description = WorkerDescription(
        worker_id="review-worker",
        summary="Auto-resolves review items that have accepted corroborating or conflicting claims.",
        consumes=(EventTopic.CLAIM_REVIEW_REQUESTED.value,),
        produces=(
            EventTopic.DEBATE_TRIGGERED.value,
            EventTopic.DEBATE_COMPLETED.value,
            EventTopic.EVIDENCE_CREATED.value,
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
        self.pipeline_service = PhaseOnePipelineService(settings, event_bus, openai_service)
        self.debate_service = DebateService(settings, event_bus, openai_service)
        self.debate_workflow = self.debate_service.workflow

    async def run_once(self) -> dict[str, object]:
        database = get_database()
        async with database.session() as session:
            pending_items = await self._claim_review_items(
                session,
                limit=20,
                worker_id=self.worker_instance_id,
            )
            await session.commit()

        debated_items = 0
        auto_accepted = 0
        auto_rejected = 0
        manual_queue = 0

        for review_item in pending_items:
            result = await self._process_review_item(database, review_item.id)
            debated_items += result["debated_items"]
            auto_accepted += result["auto_accepted"]
            auto_rejected += result["auto_rejected"]
            manual_queue += result["manual_queue"]

        return {
            "pending_items": len(pending_items),
            "debated_items": debated_items,
            "auto_accepted": auto_accepted,
            "auto_rejected": auto_rejected,
            "manual_queue": manual_queue,
        }

    async def _process_review_item(self, database, review_item_id: str) -> dict[str, int]:
        async with database.session() as session:
            try:
                review_item = await session.get(ReviewItem, review_item_id)
                if review_item is None or review_item.status != ReviewItemStatus.PENDING.value:
                    return self._empty_result()

                claim = await session.get(Claim, review_item.claim_id)
                if claim is None:
                    self._release_review_item(review_item, "claim_not_found")
                    await session.commit()
                    return self._manual_result()

                existing_verdict = await self._latest_automated_verdict(session, claim.id)
                if existing_verdict == "ACCEPTED":
                    await self.pipeline_service.accept_review_item(
                        session,
                        review_item.id,
                        ReviewDecisionRequest(
                            reviewer_id="review-worker",
                            note="review-worker reused existing automated debate verdict=ACCEPTED.",
                        ),
                    )
                    return self._result(auto_accepted=1)
                if existing_verdict == "REJECTED":
                    await self.pipeline_service.reject_review_item(
                        session,
                        review_item.id,
                        ReviewDecisionRequest(
                            reviewer_id="review-worker",
                            note="review-worker reused existing automated debate verdict=REJECTED.",
                        ),
                    )
                    return self._result(auto_rejected=1)
                if existing_verdict is not None:
                    return await self._resolve_or_release_conditional(
                        session,
                        review_item,
                        claim,
                        f"existing_debate_verdict={existing_verdict}",
                    )

                relations = await self.debate_service.find_claim_relations(session, claim)
                has_conflict = bool(relations.conflicting_claims)
                has_accepted_support = any(
                    related.status == ClaimStatus.ACCEPTED.value
                    for related in relations.supportive_claims
                )
                has_accepted_conflict = any(
                    related.status == ClaimStatus.ACCEPTED.value
                    for related in relations.conflicting_claims
                )
                if has_accepted_conflict:
                    trigger_type = "conflict_resolution"
                    context_line = (
                        "Auto-triggered by review-worker because accepted conflicting "
                        "evidence was found."
                    )
                elif has_accepted_support and not has_conflict:
                    trigger_type = "evidence_assessment"
                    context_line = (
                        "Auto-triggered by review-worker because accepted corroborating "
                        "evidence was found."
                    )
                elif (
                    claim.confidence >= self.settings.review_auto_process_confidence
                    or review_item.processing_attempts >= self.settings.worker_max_attempts
                ):
                    trigger_type = "evidence_assessment"
                    context_line = (
                        "Auto-triggered by review-worker for a high-confidence or repeatedly "
                        "deferred gray-zone claim."
                    )
                else:
                    self._release_review_item(review_item, None)
                    await session.commit()
                    return self._manual_result()

                debate = await self.debate_workflow.decide(
                    session,
                    DebateCommand(
                        target=DebateTarget.claim(claim.id),
                        topic=f"Should claim {claim.id} enter the simulation chain?",
                        trigger_type=trigger_type,
                        context=(context_line,),
                    ),
                )
                verdict = debate.verdict.verdict if debate.verdict is not None else None
                conflict_ids = [item.id for item in relations.conflicting_claims]
                note = (
                    f"review-worker {trigger_type} verdict={verdict}; "
                    f"supporting_claim_ids={[item.id for item in relations.supportive_claims]}; "
                    f"conflicting_claim_ids={conflict_ids}"
                )
                if verdict == "ACCEPTED":
                    await self.pipeline_service.accept_review_item(
                        session,
                        review_item.id,
                        ReviewDecisionRequest(reviewer_id="review-worker", note=note),
                    )
                    return self._result(debated_items=1, auto_accepted=1)
                if verdict == "REJECTED":
                    await self.pipeline_service.reject_review_item(
                        session,
                        review_item.id,
                        ReviewDecisionRequest(reviewer_id="review-worker", note=note),
                    )
                    return self._result(debated_items=1, auto_rejected=1)
                result = await self._resolve_or_release_conditional(
                    session,
                    review_item,
                    claim,
                    f"{note}; unresolved_verdict={verdict or 'pending'}",
                )
                result["debated_items"] = 1
                return result
            except Exception as exc:
                await session.rollback()
                review_item = await session.get(ReviewItem, review_item_id)
                if review_item is not None and review_item.status == ReviewItemStatus.PENDING.value:
                    self._release_review_item(
                        review_item,
                        f"{type(exc).__name__}: {' '.join(str(exc).split())[:300]}",
                    )
                    await session.commit()
                return self._manual_result()

    async def _claim_review_items(
        self,
        session,
        limit: int,
        worker_id: str,
    ) -> list[ReviewItem]:
        now = utc_now()
        lease_expires_at = now + timedelta(seconds=self.settings.worker_lease_seconds)
        candidate_ids = list(
            (
                await session.scalars(
                    select(ReviewItem.id)
                    .where(
                        ReviewItem.status == ReviewItemStatus.PENDING.value,
                        or_(
                            ReviewItem.lease_expires_at.is_(None),
                            ReviewItem.lease_expires_at < now,
                        ),
                    )
                    .order_by(ReviewItem.created_at.asc())
                    .limit(limit * 3)
                )
            ).all()
        )
        claimed: list[ReviewItem] = []
        for review_item_id in candidate_ids:
            result = await session.execute(
                update(ReviewItem)
                .where(
                    ReviewItem.id == review_item_id,
                    ReviewItem.status == ReviewItemStatus.PENDING.value,
                    or_(
                        ReviewItem.lease_expires_at.is_(None),
                        ReviewItem.lease_expires_at < now,
                    ),
                )
                .values(
                    lease_owner=worker_id,
                    lease_expires_at=lease_expires_at,
                    processing_attempts=ReviewItem.processing_attempts + 1,
                    last_error=None,
                    updated_at=now,
                )
            )
            if result.rowcount:
                review_item = await session.get(ReviewItem, review_item_id)
                if review_item is not None:
                    claimed.append(review_item)
            if len(claimed) >= limit:
                break
        return claimed

    async def _latest_automated_verdict(self, session, claim_id: str) -> str | None:
        verdict = (
            await session.execute(
                select(DebateVerdictRecord.verdict)
                .join(DebateSessionRecord, DebateSessionRecord.id == DebateVerdictRecord.debate_id)
                .where(
                    DebateSessionRecord.claim_id == claim_id,
                    DebateSessionRecord.trigger_type.in_(
                        ["conflict_resolution", "evidence_assessment"]
                    ),
                )
                .order_by(DebateSessionRecord.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        return verdict

    async def _resolve_or_release_conditional(
        self,
        session,
        review_item: ReviewItem,
        claim: Claim,
        note: str,
    ) -> dict[str, int]:
        if review_item.processing_attempts < self.settings.worker_max_attempts:
            self._release_review_item(review_item, note)
            await session.commit()
            return self._manual_result()

        if claim.confidence >= self.settings.review_conditional_accept_confidence:
            await self.pipeline_service.accept_review_item(
                session,
                review_item.id,
                ReviewDecisionRequest(
                    reviewer_id="review-worker",
                    note=(
                        f"{note}; resolved after {review_item.processing_attempts} attempts "
                        "using review_conditional_accept_confidence."
                    ),
                ),
            )
            return self._result(auto_accepted=1)

        await self.pipeline_service.reject_review_item(
            session,
            review_item.id,
            ReviewDecisionRequest(
                reviewer_id="review-worker",
                note=(
                    f"{note}; rejected after {review_item.processing_attempts} attempts "
                    "using review_conditional_accept_confidence."
                ),
            ),
        )
        return self._result(auto_rejected=1)

    def _release_review_item(self, review_item: ReviewItem, error: str | None) -> None:
        review_item.lease_owner = None
        review_item.lease_expires_at = None
        review_item.last_error = error
        review_item.updated_at = utc_now()

    def _empty_result(self) -> dict[str, int]:
        return self._result()

    def _manual_result(self) -> dict[str, int]:
        return self._result(manual_queue=1)

    def _result(
        self,
        debated_items: int = 0,
        auto_accepted: int = 0,
        auto_rejected: int = 0,
        manual_queue: int = 0,
    ) -> dict[str, int]:
        return {
            "debated_items": debated_items,
            "auto_accepted": auto_accepted,
            "auto_rejected": auto_rejected,
            "manual_queue": manual_queue,
        }
