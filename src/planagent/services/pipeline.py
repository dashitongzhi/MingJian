from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from planagent.config import Settings
from planagent.domain.api import IngestRunCreate, ReviewDecisionRequest, SourceSeedInput
from planagent.domain.enums import ClaimStatus, EventTopic, ExecutionMode, IngestRunStatus, ReviewItemStatus
from planagent.domain.models import (
    Claim,
    EventArchive,
    EventRecord,
    EvidenceItem,
    IngestRun,
    NormalizedItem,
    RawSourceItem,
    ReviewItem,
    Signal,
    Trend,
    utc_now,
)
from planagent.events.bus import EventBus
from planagent.services.openai_client import OpenAIService
from planagent.services.openai_client import TargetRole

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?。！？])\s+")
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_url(url: str) -> str:
    parts = urlsplit(url)
    normalized_path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), normalized_path, "", ""))


def normalize_text(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", value).strip()


def build_dedupe_key(item: SourceSeedInput) -> str:
    normalized = "|".join(
        [
            normalize_url(item.source_url),
            normalize_text(item.title).lower(),
            normalize_text(item.content_text)[:512].lower(),
        ]
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def summarize_text(body_text: str, max_length: int = 220) -> str:
    summary = normalize_text(body_text)
    if len(summary) <= max_length:
        return summary
    return f"{summary[: max_length - 3].rstrip()}..."


def estimate_evidence_confidence(item: SourceSeedInput) -> float:
    score = 0.45
    if item.title:
        score += 0.10
    if item.source_url:
        score += 0.10
    if item.published_at:
        score += 0.05
    score += min(len(normalize_text(item.content_text)) / 1500, 0.25)
    return max(0.25, min(score, 0.95))


def extract_claim_sentences(body_text: str) -> list[str]:
    sentences = [normalize_text(chunk) for chunk in _SENTENCE_SPLIT_RE.split(body_text)]
    filtered = [sentence for sentence in sentences if sentence]
    return filtered[:5]


def estimate_claim_confidence(evidence_confidence: float, sentence: str) -> float:
    score = evidence_confidence - 0.20 + min(len(sentence) / 240, 0.20)
    return max(0.25, min(score, 0.95))


def classify_claim(statement: str) -> tuple[str | None, str]:
    lowered = statement.lower()
    if any(keyword in lowered for keyword in ["launch", "release", "ship", "strike", "deploy", "announce"]):
        return "event", "notable_action"
    if any(keyword in lowered for keyword in ["increase", "decrease", "rise", "drop", "percent", "%"]):
        return "signal", "metric_shift"
    if any(keyword in lowered for keyword in ["trend", "momentum", "adoption", "growing", "declining"]):
        return "trend", "trajectory"
    return None, "unclassified"


def select_extraction_target(source_type: str) -> TargetRole:
    normalized = normalize_text(source_type).lower()
    if normalized in {"x", "twitter", "tweet", "x.com"}:
        return "x_search"
    return "extraction"


@dataclass
class EventEnvelope:
    topic: EventTopic
    payload: dict[str, Any]


@dataclass
class ClaimCandidate:
    statement: str
    confidence: float | None = None
    kind: str | None = None
    reasoning: str | None = None


class PhaseOnePipelineService:
    def __init__(
        self,
        settings: Settings,
        event_bus: EventBus,
        openai_service: OpenAIService | None = None,
    ) -> None:
        self.settings = settings
        self.event_bus = event_bus
        self.openai_service = openai_service

    async def create_ingest_run(self, session: AsyncSession, payload: IngestRunCreate) -> IngestRun:
        execution_mode = payload.execution_mode or (
            ExecutionMode.INLINE if self.settings.inline_ingest_default else ExecutionMode.QUEUED
        )
        run = IngestRun(
            requested_by=payload.requested_by,
            execution_mode=execution_mode.value,
            status=IngestRunStatus.PENDING.value,
            source_types=sorted({item.source_type for item in payload.items}),
            request_payload={"items": [item.model_dump(mode="json") for item in payload.items]},
            summary=self._empty_summary(),
        )
        session.add(run)
        await session.flush()

        emitted_events: list[EventEnvelope] = []
        if execution_mode == ExecutionMode.INLINE:
            await self._process_run_items(
                session=session,
                run=run,
                items=payload.items,
                emitted_events=emitted_events,
            )

        await session.commit()
        await self._publish_events(emitted_events)
        await session.refresh(run)
        return run

    async def process_queued_runs(self, session: AsyncSession, limit: int = 10) -> int:
        query = (
            select(IngestRun)
            .where(IngestRun.status == IngestRunStatus.PENDING.value)
            .order_by(IngestRun.created_at.asc())
            .limit(limit)
        )
        runs = list((await session.scalars(query)).all())
        processed = 0
        emitted_events: list[EventEnvelope] = []

        for run in runs:
            items = [SourceSeedInput.model_validate(item) for item in run.request_payload.get("items", [])]
            await self._process_run_items(session=session, run=run, items=items, emitted_events=emitted_events)
            processed += 1

        await session.commit()
        await self._publish_events(emitted_events)
        return processed

    async def accept_review_item(
        self, session: AsyncSession, review_item_id: str, payload: ReviewDecisionRequest
    ) -> ReviewItem:
        review_item = await session.get(ReviewItem, review_item_id)
        if review_item is None:
            raise LookupError(f"Review item {review_item_id} was not found.")

        claim = await session.get(Claim, review_item.claim_id)
        if claim is None:
            raise LookupError(f"Claim {review_item.claim_id} was not found.")

        review_item.status = ReviewItemStatus.ACCEPTED.value
        review_item.reviewer_id = payload.reviewer_id
        review_item.review_note = payload.note
        review_item.resolved_at = utc_now()
        claim.status = ClaimStatus.ACCEPTED.value
        claim.requires_review = False
        claim.updated_at = utc_now()

        session.add(
            EventArchive(
                topic=EventTopic.EVIDENCE_CREATED.value,
                payload={
                    "claim_id": claim.id,
                    "review_item_id": review_item.id,
                    "review_outcome": review_item.status,
                },
            )
        )
        await self._promote_claim_artifacts(session, claim)
        await session.commit()
        await self.event_bus.publish(
            EventTopic.EVIDENCE_CREATED.value,
            {
                "claim_id": claim.id,
                "review_item_id": review_item.id,
                "review_outcome": review_item.status,
            },
        )
        await session.refresh(review_item)
        return review_item

    async def reject_review_item(
        self, session: AsyncSession, review_item_id: str, payload: ReviewDecisionRequest
    ) -> ReviewItem:
        review_item = await session.get(ReviewItem, review_item_id)
        if review_item is None:
            raise LookupError(f"Review item {review_item_id} was not found.")

        claim = await session.get(Claim, review_item.claim_id)
        if claim is None:
            raise LookupError(f"Claim {review_item.claim_id} was not found.")

        review_item.status = ReviewItemStatus.REJECTED.value
        review_item.reviewer_id = payload.reviewer_id
        review_item.review_note = payload.note
        review_item.resolved_at = utc_now()
        claim.status = ClaimStatus.REJECTED.value
        claim.requires_review = False
        claim.updated_at = utc_now()

        await session.commit()
        await session.refresh(review_item)
        return review_item

    def _empty_summary(self) -> dict[str, int]:
        return {
            "processed_items": 0,
            "duplicate_items": 0,
            "accepted_claims": 0,
            "review_claims": 0,
            "archived_claims": 0,
        }

    async def _process_run_items(
        self,
        session: AsyncSession,
        run: IngestRun,
        items: list[SourceSeedInput],
        emitted_events: list[EventEnvelope],
    ) -> None:
        run.status = IngestRunStatus.PROCESSING.value
        summary = dict(run.summary or self._empty_summary())

        for item in items:
            duplicate = await self._find_duplicate(session, item)
            if duplicate is not None:
                summary["duplicate_items"] += 1
                continue

            await self._persist_seed_item(
                session=session,
                run=run,
                item=item,
                summary=summary,
                emitted_events=emitted_events,
            )

        run.summary = summary
        run.status = IngestRunStatus.COMPLETED.value
        run.updated_at = utc_now()

    async def _find_duplicate(self, session: AsyncSession, item: SourceSeedInput) -> RawSourceItem | None:
        dedupe_key = build_dedupe_key(item)
        query = select(RawSourceItem).where(RawSourceItem.dedupe_key == dedupe_key)
        return (await session.scalars(query)).first()

    async def _persist_seed_item(
        self,
        session: AsyncSession,
        run: IngestRun,
        item: SourceSeedInput,
        summary: dict[str, int],
        emitted_events: list[EventEnvelope],
    ) -> None:
        dedupe_key = build_dedupe_key(item)
        raw = RawSourceItem(
            ingest_run_id=run.id,
            source_type=item.source_type,
            source_url=normalize_url(item.source_url),
            title=normalize_text(item.title),
            content_text=normalize_text(item.content_text),
            published_at=item.published_at,
            source_metadata=item.source_metadata,
            dedupe_key=dedupe_key,
        )
        session.add(raw)
        await session.flush()
        self._buffer_event(
            session,
            emitted_events,
            EventTopic.RAW_INGESTED,
            {
                "ingest_run_id": run.id,
                "raw_source_item_id": raw.id,
                "source_type": raw.source_type,
            },
        )

        evidence_confidence = estimate_evidence_confidence(item)
        normalized = NormalizedItem(
            raw_source_item_id=raw.id,
            canonical_url=raw.source_url,
            title=raw.title,
            body_text=raw.content_text,
            confidence=evidence_confidence,
            normalized_metadata={"normalized_at": datetime.now(timezone.utc).isoformat()},
        )
        session.add(normalized)
        await session.flush()

        evidence = EvidenceItem(
            normalized_item_id=normalized.id,
            evidence_type="article",
            title=normalized.title,
            summary=summarize_text(normalized.body_text),
            body_text=normalized.body_text,
            source_url=normalized.canonical_url,
            confidence=evidence_confidence,
            provenance={"raw_source_item_id": raw.id},
        )
        session.add(evidence)
        await session.flush()
        self._buffer_event(
            session,
            emitted_events,
            EventTopic.EVIDENCE_CREATED,
            {
                "ingest_run_id": run.id,
                "evidence_item_id": evidence.id,
                "confidence": evidence.confidence,
            },
        )

        summary_text, claim_candidates = await self._extract_claim_candidates(item, evidence_confidence)
        evidence.summary = summary_text
        await session.flush()

        for candidate in claim_candidates:
            await self._create_claim(
                session=session,
                evidence=evidence,
                run=run,
                candidate=candidate,
                summary=summary,
                emitted_events=emitted_events,
            )

        self._buffer_event(
            session,
            emitted_events,
            EventTopic.KNOWLEDGE_EXTRACTED,
            {
                "ingest_run_id": run.id,
                "evidence_item_id": evidence.id,
            },
        )
        summary["processed_items"] += 1

    async def _create_claim(
        self,
        session: AsyncSession,
        evidence: EvidenceItem,
        run: IngestRun,
        candidate: ClaimCandidate,
        summary: dict[str, int],
        emitted_events: list[EventEnvelope],
    ) -> None:
        confidence = self._blend_claim_confidence(
            evidence_confidence=evidence.confidence,
            statement=candidate.statement,
            extracted_confidence=candidate.confidence,
        )
        if confidence >= self.settings.accepted_claim_confidence:
            status = ClaimStatus.ACCEPTED
            requires_review = False
            summary["accepted_claims"] += 1
        elif confidence >= self.settings.review_claim_confidence_floor:
            status = ClaimStatus.PENDING_REVIEW
            requires_review = True
            summary["review_claims"] += 1
        else:
            status = ClaimStatus.ARCHIVED
            requires_review = False
            summary["archived_claims"] += 1

        claim = Claim(
            evidence_item_id=evidence.id,
            subject=evidence.title[:255],
            predicate="states",
            object_text=candidate.statement,
            statement=candidate.statement,
            confidence=confidence,
            status=status.value,
            requires_review=requires_review,
            reasoning=candidate.reasoning or "heuristic_sentence_extraction",
        )
        session.add(claim)
        await session.flush()

        if status == ClaimStatus.ACCEPTED:
            await self._promote_claim_artifacts(session, claim, candidate.kind)
        elif status == ClaimStatus.PENDING_REVIEW:
            review_item = ReviewItem(
                claim_id=claim.id,
                queue_reason="Claim confidence landed in the manual review band.",
                status=ReviewItemStatus.PENDING.value,
            )
            session.add(review_item)
            await session.flush()
            self._buffer_event(
                session,
                emitted_events,
                EventTopic.CLAIM_REVIEW_REQUESTED,
                {
                    "ingest_run_id": run.id,
                    "claim_id": claim.id,
                    "review_item_id": review_item.id,
                    "confidence": claim.confidence,
                },
            )

    async def _promote_claim_artifacts(
        self,
        session: AsyncSession,
        claim: Claim,
        artifact_kind: str | None = None,
    ) -> None:
        artifact_type = "unclassified"
        if artifact_kind in {"signal", "event", "trend"}:
            artifact_type = {
                "signal": "model_signal",
                "event": "model_event",
                "trend": "model_trend",
            }[artifact_kind]
        else:
            artifact_kind, artifact_type = classify_claim(claim.statement)
        title = summarize_text(claim.statement, max_length=120)
        if artifact_kind == "signal":
            session.add(Signal(claim_id=claim.id, signal_type=artifact_type, title=title, confidence=claim.confidence))
        elif artifact_kind == "event":
            session.add(
                EventRecord(claim_id=claim.id, event_type=artifact_type, title=title, confidence=claim.confidence)
            )
        elif artifact_kind == "trend":
            session.add(Trend(claim_id=claim.id, trend_type=artifact_type, title=title, confidence=claim.confidence))

    def _buffer_event(
        self,
        session: AsyncSession,
        emitted_events: list[EventEnvelope],
        topic: EventTopic,
        payload: dict[str, Any],
    ) -> None:
        session.add(EventArchive(topic=topic.value, payload=payload))
        emitted_events.append(EventEnvelope(topic=topic, payload=payload))

    async def _publish_events(self, emitted_events: list[EventEnvelope]) -> None:
        for event in emitted_events:
            await self.event_bus.publish(event.topic.value, event.payload)

    async def _extract_claim_candidates(
        self,
        item: SourceSeedInput,
        evidence_confidence: float,
    ) -> tuple[str, list[ClaimCandidate]]:
        if self.openai_service is not None and self.openai_service.enabled:
            extraction = await self.openai_service.extract_evidence(
                item.title,
                item.content_text,
                target=select_extraction_target(item.source_type),
            )
            if extraction is not None and extraction.claims:
                candidates = [
                    ClaimCandidate(
                        statement=normalize_text(claim.statement),
                        confidence=claim.confidence,
                        kind=None if claim.kind == "unclassified" else claim.kind,
                        reasoning=f"openai_responses:{claim.rationale}",
                    )
                    for claim in extraction.claims[:5]
                    if normalize_text(claim.statement)
                ]
                if candidates:
                    return extraction.summary, candidates

        sentences = extract_claim_sentences(item.content_text) or [item.content_text]
        return (
            summarize_text(item.content_text),
            [ClaimCandidate(statement=sentence) for sentence in sentences],
        )

    def _blend_claim_confidence(
        self,
        evidence_confidence: float,
        statement: str,
        extracted_confidence: float | None,
    ) -> float:
        heuristic = estimate_claim_confidence(evidence_confidence, statement)
        if extracted_confidence is None:
            return heuristic
        blended = (heuristic + extracted_confidence) / 2
        return max(0.25, min(blended, 0.95))
