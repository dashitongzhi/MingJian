from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import re
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.exc import IntegrityError
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
    SourceSnapshot,
    Trend,
    utc_now,
)
from planagent.events.bus import EventBus
from planagent.services.evidence_weighting import EvidenceWeightingService
from planagent.services.startup import normalize_tenant_id

if TYPE_CHECKING:
    from planagent.services.openai_client import OpenAIService, TargetRole

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
    if normalized in {"x", "twitter", "tweet", "x.com", "x_recent_search", "x_model_search"}:
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
        self.evidence_weighting = EvidenceWeightingService(settings)

    async def create_ingest_run(self, session: AsyncSession, payload: IngestRunCreate) -> IngestRun:
        tenant_id = normalize_tenant_id(payload.tenant_id)
        execution_mode = payload.execution_mode or (
            ExecutionMode.INLINE if self.settings.inline_ingest_default else ExecutionMode.QUEUED
        )
        run = IngestRun(
            requested_by=payload.requested_by,
            tenant_id=tenant_id,
            preset_id=payload.preset_id,
            execution_mode=execution_mode.value,
            status=IngestRunStatus.PENDING.value,
            source_types=sorted({item.source_type for item in payload.items}),
            request_payload={
                "items": [item.model_dump(mode="json") for item in payload.items],
                "tenant_id": tenant_id,
                "preset_id": payload.preset_id,
            },
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

    async def process_queued_runs(
        self,
        session: AsyncSession,
        limit: int = 10,
        worker_id: str | None = None,
    ) -> int:
        runs = await self._claim_ingest_runs(
            session,
            limit=limit,
            worker_id=worker_id or "ingest-worker",
        )
        processed = 0
        emitted_events: list[EventEnvelope] = []

        for run in runs:
            try:
                items = [SourceSeedInput.model_validate(item) for item in run.request_payload.get("items", [])]
                await self._stage_run_items(session=session, run=run, items=items, emitted_events=emitted_events)
                run.last_error = None
                processed += 1
            except Exception as exc:
                run.last_error = f"{type(exc).__name__}: {normalize_text(str(exc))[:300]}"
                run.status = (
                    IngestRunStatus.FAILED.value
                    if run.processing_attempts >= self.settings.worker_max_attempts
                    else IngestRunStatus.PENDING.value
                )
            finally:
                run.lease_owner = None
                run.lease_expires_at = None
                run.updated_at = utc_now()

        await session.commit()
        await self._publish_events(emitted_events)
        return processed

    async def process_pending_knowledge(
        self,
        session: AsyncSession,
        limit: int = 50,
        worker_id: str | None = None,
    ) -> tuple[int, int]:
        raw_items = await self._claim_raw_items(
            session,
            limit=limit,
            worker_id=worker_id or "knowledge-worker",
        )
        if not raw_items:
            return 0, 0

        emitted_events: list[EventEnvelope] = []
        run_summaries: dict[str, dict[str, int]] = {}
        touched_runs: dict[str, IngestRun] = {}

        for raw in raw_items:
            run = await session.get(IngestRun, raw.ingest_run_id)
            if run is None:
                continue
            touched_runs[run.id] = run
            summary = run_summaries.setdefault(run.id, dict(run.summary or self._empty_summary()))
            try:
                await self._materialize_knowledge_for_raw_item(
                    session=session,
                    run=run,
                    raw=raw,
                    summary=summary,
                    emitted_events=emitted_events,
                )
                raw.knowledge_status = "COMPLETED"
                raw.last_error = None
                raw.processed_at = utc_now()
            except Exception as exc:
                raw.last_error = f"{type(exc).__name__}: {normalize_text(str(exc))[:300]}"
                if raw.processing_attempts >= self.settings.worker_max_attempts:
                    raw.knowledge_status = "FAILED"
                    summary["failed_items"] = int(summary.get("failed_items", 0)) + 1
                else:
                    raw.knowledge_status = "PENDING"
            finally:
                raw.lease_owner = None
                raw.lease_expires_at = None
            run.summary = summary
            run.updated_at = utc_now()

        completed_runs = 0
        for run in touched_runs.values():
            if await self._finalize_queued_run(session, run):
                completed_runs += 1

        await session.commit()
        await self._publish_events(emitted_events)
        return len(raw_items), completed_runs

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
        review_item.lease_owner = None
        review_item.lease_expires_at = None
        review_item.last_error = None
        review_item.reviewer_id = payload.reviewer_id
        review_item.review_note = payload.note
        review_item.resolved_at = utc_now()
        review_item.updated_at = utc_now()
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
        review_item.lease_owner = None
        review_item.lease_expires_at = None
        review_item.last_error = None
        review_item.reviewer_id = payload.reviewer_id
        review_item.review_note = payload.note
        review_item.resolved_at = utc_now()
        review_item.updated_at = utc_now()
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
            "failed_items": 0,
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
            try:
                async with session.begin_nested():
                    raw = await self._persist_raw_item(
                        session=session,
                        run=run,
                        item=item,
                        emitted_events=emitted_events,
                    )
                    await self._materialize_knowledge_for_raw_item(
                        session=session,
                        run=run,
                        raw=raw,
                        summary=summary,
                        emitted_events=emitted_events,
                    )
                    raw.knowledge_status = "COMPLETED"
                    raw.last_error = None
                    raw.processed_at = utc_now()
            except IntegrityError:
                summary["duplicate_items"] += 1

        run.summary = summary
        run.status = IngestRunStatus.COMPLETED.value
        run.lease_owner = None
        run.lease_expires_at = None
        run.updated_at = utc_now()

    async def _stage_run_items(
        self,
        session: AsyncSession,
        run: IngestRun,
        items: list[SourceSeedInput],
        emitted_events: list[EventEnvelope],
    ) -> None:
        run.status = IngestRunStatus.PROCESSING.value
        summary = dict(run.summary or self._empty_summary())
        staged_items = 0

        for item in items:
            try:
                async with session.begin_nested():
                    await self._persist_raw_item(
                        session=session,
                        run=run,
                        item=item,
                        emitted_events=emitted_events,
                    )
                    staged_items += 1
            except IntegrityError:
                summary["duplicate_items"] += 1

        run.summary = summary
        run.lease_owner = None
        run.lease_expires_at = None
        run.updated_at = utc_now()
        if staged_items == 0:
            run.status = IngestRunStatus.COMPLETED.value

    async def _persist_raw_item(
        self,
        session: AsyncSession,
        run: IngestRun,
        item: SourceSeedInput,
        emitted_events: list[EventEnvelope],
    ) -> RawSourceItem:
        dedupe_key = build_dedupe_key(item)
        tenant_id = normalize_tenant_id(run.request_payload.get("tenant_id"))
        raw = RawSourceItem(
            ingest_run_id=run.id,
            tenant_id=tenant_id,
            preset_id=run.request_payload.get("preset_id"),
            source_type=item.source_type,
            source_url=normalize_url(item.source_url),
            title=normalize_text(item.title),
            content_text=normalize_text(item.content_text),
            published_at=item.published_at,
            source_metadata={
                **item.source_metadata,
                "tenant_id": tenant_id,
                "preset_id": run.request_payload.get("preset_id"),
            },
            dedupe_key=dedupe_key,
            knowledge_status="PENDING",
        )
        session.add(raw)
        await session.flush()
        await self._archive_source_snapshot(session, raw)
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
        return raw

    async def _archive_source_snapshot(self, session: AsyncSession, raw: RawSourceItem) -> None:
        content = {
            "source_type": raw.source_type,
            "source_url": raw.source_url,
            "title": raw.title,
            "content_text": raw.content_text,
            "published_at": raw.published_at.isoformat() if raw.published_at else None,
            "source_metadata": raw.source_metadata,
        }
        encoded = __import__("json").dumps(content, ensure_ascii=False, sort_keys=True).encode("utf-8")
        digest = hashlib.sha256(encoded).hexdigest()
        storage_backend = self.settings.source_snapshot_backend.lower()
        storage_uri = self._archive_snapshot_bytes(raw.id, encoded, storage_backend)
        session.add(
            SourceSnapshot(
                raw_source_item_id=raw.id,
                tenant_id=raw.tenant_id,
                preset_id=raw.preset_id,
                storage_backend=storage_backend if storage_backend == "minio" else "filesystem",
                storage_uri=storage_uri,
                content_sha256=digest,
                byte_size=len(encoded),
            )
        )

    def _archive_snapshot_bytes(self, raw_id: str, encoded: bytes, storage_backend: str) -> str:
        if storage_backend == "minio":
            uri = self._try_archive_snapshot_to_minio(raw_id, encoded)
            if uri:
                return uri
        snapshot_dir = Path(self.settings.source_snapshot_dir)
        if not snapshot_dir.is_absolute():
            snapshot_dir = Path.cwd() / snapshot_dir
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        snapshot_path = snapshot_dir / f"{raw_id}.json"
        snapshot_path.write_bytes(encoded)
        return str(snapshot_path)

    def _try_archive_snapshot_to_minio(self, raw_id: str, encoded: bytes) -> str | None:
        try:
            from io import BytesIO
            from minio import Minio
            from minio.error import S3Error
        except ImportError:
            return None

        bucket = self.settings.minio_bucket
        client = Minio(
            self.settings.minio_endpoint,
            access_key=self.settings.minio_access_key,
            secret_key=self.settings.minio_secret_key,
            secure=self.settings.minio_secure,
        )
        object_name = f"raw-source-items/{raw_id}.json"
        try:
            if not client.bucket_exists(bucket):
                client.make_bucket(bucket)
            client.put_object(
                bucket,
                object_name,
                BytesIO(encoded),
                length=len(encoded),
                content_type="application/json",
            )
        except S3Error:
            return None
        return f"minio://{bucket}/{object_name}"

    async def _materialize_knowledge_for_raw_item(
        self,
        session: AsyncSession,
        run: IngestRun,
        raw: RawSourceItem,
        summary: dict[str, int],
        emitted_events: list[EventEnvelope],
    ) -> None:
        existing_normalized = (
            await session.scalars(
                select(NormalizedItem).where(NormalizedItem.raw_source_item_id == raw.id).limit(1)
            )
        ).first()
        if existing_normalized is not None:
            raw.knowledge_status = "COMPLETED"
            raw.last_error = None
            raw.processed_at = utc_now()
            return

        item = SourceSeedInput(
            source_type=raw.source_type,
            source_url=raw.source_url,
            title=raw.title,
            content_text=raw.content_text,
            published_at=raw.published_at,
            source_metadata=raw.source_metadata,
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
            tenant_id=raw.tenant_id,
            preset_id=raw.preset_id,
            evidence_type="article",
            title=normalized.title,
            summary=summarize_text(normalized.body_text),
            body_text=normalized.body_text,
            source_url=normalized.canonical_url,
            confidence=evidence_confidence,
            provenance={
                "raw_source_item_id": raw.id,
                "ingest_run_id": run.id,
                "tenant_id": normalize_tenant_id(run.request_payload.get("tenant_id")),
                "preset_id": run.request_payload.get("preset_id"),
            },
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

    async def _finalize_queued_run(self, session: AsyncSession, run: IngestRun) -> bool:
        total_requested = len(run.request_payload.get("items", []))
        duplicate_items = int((run.summary or {}).get("duplicate_items", 0))
        raw_count = int(
            (
                await session.scalar(
                    select(func.count())
                    .select_from(RawSourceItem)
                    .where(RawSourceItem.ingest_run_id == run.id)
                )
            )
            or 0
        )
        pending_raw_count = int(
            (
                await session.scalar(
                    select(func.count())
                    .select_from(RawSourceItem)
                    .where(
                        RawSourceItem.ingest_run_id == run.id,
                        RawSourceItem.knowledge_status.in_(["PENDING", "PROCESSING"]),
                    )
                )
            )
            or 0
        )
        failed_raw_count = int(
            (
                await session.scalar(
                    select(func.count())
                    .select_from(RawSourceItem)
                    .where(
                        RawSourceItem.ingest_run_id == run.id,
                        RawSourceItem.knowledge_status == "FAILED",
                    )
                )
            )
            or 0
        )
        if raw_count + duplicate_items < total_requested:
            run.status = IngestRunStatus.PROCESSING.value
            run.updated_at = utc_now()
            return False
        if pending_raw_count > 0:
            run.status = IngestRunStatus.PROCESSING.value
            run.updated_at = utc_now()
            return False
        if failed_raw_count > 0:
            run.summary = {**(run.summary or {}), "failed_items": failed_raw_count}
            run.status = IngestRunStatus.FAILED.value
            run.updated_at = utc_now()
            return True
        run.status = IngestRunStatus.COMPLETED.value
        run.updated_at = utc_now()
        return True

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
        confidence = await self.evidence_weighting.adjust_claim_confidence(
            session,
            confidence,
            evidence.source_url,
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
            tenant_id=evidence.tenant_id,
            preset_id=evidence.preset_id,
            subject=evidence.title[:255],
            predicate="states",
            object_text=candidate.statement,
            statement=candidate.statement,
            kind=candidate.kind or classify_claim(candidate.statement)[0] or "unclassified",
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
                tenant_id=claim.tenant_id,
                preset_id=claim.preset_id,
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
            session.add(
                Signal(
                    claim_id=claim.id,
                    tenant_id=claim.tenant_id,
                    preset_id=claim.preset_id,
                    signal_type=artifact_type,
                    title=title,
                    confidence=claim.confidence,
                )
            )
        elif artifact_kind == "event":
            session.add(
                EventRecord(
                    claim_id=claim.id,
                    tenant_id=claim.tenant_id,
                    preset_id=claim.preset_id,
                    event_type=artifact_type,
                    title=title,
                    confidence=claim.confidence,
                )
            )
        elif artifact_kind == "trend":
            session.add(
                Trend(
                    claim_id=claim.id,
                    tenant_id=claim.tenant_id,
                    preset_id=claim.preset_id,
                    trend_type=artifact_type,
                    title=title,
                    confidence=claim.confidence,
                )
            )

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
        extraction_target = select_extraction_target(item.source_type)
        if self.openai_service is not None and self.openai_service.is_configured(extraction_target):
            extraction = await self.openai_service.extract_evidence(
                item.title,
                item.content_text,
                target=extraction_target,
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

    async def _claim_ingest_runs(
        self,
        session: AsyncSession,
        limit: int,
        worker_id: str,
    ) -> list[IngestRun]:
        now = utc_now()
        lease_expires_at = now + timedelta(seconds=self.settings.worker_lease_seconds)
        candidate_ids = list(
            (
                await session.scalars(
                    select(IngestRun.id)
                    .where(
                        or_(
                            IngestRun.status == IngestRunStatus.PENDING.value,
                            and_(
                                IngestRun.status == IngestRunStatus.PROCESSING.value,
                                or_(IngestRun.lease_expires_at.is_(None), IngestRun.lease_expires_at < now),
                            ),
                        )
                    )
                    .order_by(IngestRun.created_at.asc())
                    .limit(limit * 3)
                )
            ).all()
        )
        claimed: list[IngestRun] = []
        for run_id in candidate_ids:
            result = await session.execute(
                update(IngestRun)
                .where(
                    IngestRun.id == run_id,
                    or_(
                        IngestRun.status == IngestRunStatus.PENDING.value,
                        and_(
                            IngestRun.status == IngestRunStatus.PROCESSING.value,
                            or_(IngestRun.lease_expires_at.is_(None), IngestRun.lease_expires_at < now),
                        ),
                    ),
                )
                .values(
                    status=IngestRunStatus.PROCESSING.value,
                    lease_owner=worker_id,
                    lease_expires_at=lease_expires_at,
                    processing_attempts=IngestRun.processing_attempts + 1,
                    updated_at=now,
                )
            )
            if result.rowcount:
                run = await session.get(IngestRun, run_id)
                if run is not None:
                    claimed.append(run)
            if len(claimed) >= limit:
                break
        return claimed

    async def _claim_raw_items(
        self,
        session: AsyncSession,
        limit: int,
        worker_id: str,
    ) -> list[RawSourceItem]:
        now = utc_now()
        lease_expires_at = now + timedelta(seconds=self.settings.worker_lease_seconds)
        candidate_ids = list(
            (
                await session.scalars(
                    select(RawSourceItem.id)
                    .join(IngestRun, IngestRun.id == RawSourceItem.ingest_run_id)
                    .where(
                        IngestRun.status == IngestRunStatus.PROCESSING.value,
                        or_(
                            RawSourceItem.knowledge_status == "PENDING",
                            and_(
                                RawSourceItem.knowledge_status == "PROCESSING",
                                or_(RawSourceItem.lease_expires_at.is_(None), RawSourceItem.lease_expires_at < now),
                            ),
                        ),
                    )
                    .order_by(RawSourceItem.created_at.asc())
                    .limit(limit * 3)
                )
            ).all()
        )
        claimed: list[RawSourceItem] = []
        for raw_id in candidate_ids:
            result = await session.execute(
                update(RawSourceItem)
                .where(
                    RawSourceItem.id == raw_id,
                    or_(
                        RawSourceItem.knowledge_status == "PENDING",
                        and_(
                            RawSourceItem.knowledge_status == "PROCESSING",
                            or_(RawSourceItem.lease_expires_at.is_(None), RawSourceItem.lease_expires_at < now),
                        ),
                    ),
                )
                .values(
                    knowledge_status="PROCESSING",
                    lease_owner=worker_id,
                    lease_expires_at=lease_expires_at,
                    processing_attempts=RawSourceItem.processing_attempts + 1,
                )
            )
            if result.rowcount:
                raw = await session.get(RawSourceItem, raw_id)
                if raw is not None:
                    claimed.append(raw)
            if len(claimed) >= limit:
                break
        return claimed
