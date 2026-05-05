from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import re
from typing import Any
from zoneinfo import ZoneInfo
from zoneinfo import ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from planagent.domain.api import (
    AnalysisRequest,
    AnalysisResponse,
    DebateTriggerRequest,
    IngestRunCreate,
    PanelDiscussionMessageRead,
    SimulationRunCreate,
    StrategicBriefRecordRead,
    StrategicAssistantRequest,
    StrategicAssistantResponse,
    StrategicRunSnapshotRead,
    StrategicSessionDetailRead,
    StrategicSessionRead,
    RunWorkbenchRead,
)
from planagent.domain.models import (
    Claim,
    EvidenceItem,
    GeneratedReport,
    Hypothesis,
    NormalizedItem,
    PredictionVersion,
    RawSourceItem,
    StrategicBriefRecord,
    StrategicRunSnapshot,
    StrategicSession,
    WatchRule,
    utc_now,
)
from planagent.domain.types import GeneratedReportModel
from planagent.services.analysis import AutomatedAnalysisService
from planagent.services.debate import DebateService
from planagent.services.pipeline import PhaseOnePipelineService
from planagent.services.simulation import SimulationService
from planagent.services.workbench import WorkbenchService

_WHITESPACE_RE = re.compile(r"\s+")
_SLUG_TOKEN_RE = re.compile(r"[a-z0-9]+")
_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AssistantEvent:
    event: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class DebateSuggestion:
    """Result of conflict detection over an analysis response."""
    warranted: bool
    confidence: float
    reasons: list[str]
    suggested_topic: str
    conflicting_signals: list[str]
    risk_score: float = 0.0
    opportunity_score: float = 0.0


 # Heuristic keywords used to detect tension in findings / recommendations.
_RISK_KEYWORDS = {
    "risk", "risks", "risky", "threat", "threats", "danger", "dangerous",
    "loss", "losses", "decline", "declining", "drop", "fall", "fell",
    "delay", "delayed", "cancel", "canceled", "disrupt", "disrupted",
    "downside", "volatile", "volatility", "uncertain", "uncertainty",
    "concern", "concerns", "warning", "caution", "cautionary",
    "challenge", "challenges", "headwind", "headwinds",
}
_OPPORTUNITY_KEYWORDS = {
    "opportunity", "opportunities", "growth", "growing", "grow",
    "increase", "increased", "improve", "improved", "gain", "gains",
    "upside", "bullish", "optimistic", "positive", "strength", "strong",
    "launch", "launched", "expand", "expanding", "momentum",
    "catalyst", "catalysts", "tailwind", "tailwinds",
}
_UNCERTAINTY_KEYWORDS = {
    "uncertain", "uncertainty", "unclear", "ambiguous", "mixed",
    "conflicting", "conflict", "diverge", "divergent", "contested",
    "debate", "debated", "disputed", "controversial",
    "however", "although", "despite", "nevertheless", "on the other hand",
    "could go either", "high risk high reward", "volatile",
}


class StrategicAssistantService:
    def __init__(
        self,
        analysis_service: AutomatedAnalysisService,
        pipeline_service: PhaseOnePipelineService,
        simulation_service: SimulationService,
        debate_service: DebateService,
        workbench_service: WorkbenchService,
    ) -> None:
        self.analysis_service = analysis_service
        self.pipeline_service = pipeline_service
        self.simulation_service = simulation_service
        self.debate_service = debate_service
        self.workbench_service = workbench_service

    async def run(
        self,
        session: AsyncSession,
        payload: StrategicAssistantRequest,
    ) -> StrategicAssistantResponse:
        final_result: StrategicAssistantResponse | None = None
        async for event in self.stream(session, payload):
            if event.event == "assistant_result":
                final_result = StrategicAssistantResponse.model_validate(event.payload)
        if final_result is None:
            raise RuntimeError("Strategic assistant finished without a result payload.")
        try:
            await self._auto_create_watch_rule(
                session,
                payload.topic,
                final_result.domain_id,
                payload.tick_count,
            )
        except Exception:
            await session.rollback()
        return final_result

    async def stream(
        self,
        session: AsyncSession,
        payload: StrategicAssistantRequest,
    ) -> AsyncIterator[AssistantEvent]:
        analysis_payload = self._build_analysis_request(payload)
        analysis_result: AnalysisResponse | None = None

        async for event in self.analysis_service.stream_analysis(analysis_payload):
            yield self._event(event.event, event.payload)
            if event.event == "result":
                analysis_result = AnalysisResponse.model_validate(event.payload)

        if analysis_result is None:
            raise RuntimeError("Analysis phase did not produce a final result.")

        domain_id = analysis_result.domain_id
        subject_id, subject_name = self._resolve_subject(payload, analysis_result)

        # ---- Auto-trigger debate: detect conflicting signals ----
        debate_suggestion = self._detect_conflicting_signals(
            analysis=analysis_result,
            domain_id=domain_id,
            subject_name=subject_name,
        )
        yield self._event("debate_suggested", {
            "warranted": debate_suggestion.warranted,
            "confidence": round(debate_suggestion.confidence, 4),
            "reasons": debate_suggestion.reasons,
            "suggested_topic": debate_suggestion.suggested_topic,
            "conflicting_signals": debate_suggestion.conflicting_signals,
            "risk_score": round(debate_suggestion.risk_score, 4),
            "opportunity_score": round(debate_suggestion.opportunity_score, 4),
        })

        ingest_payload = self._build_ingest_payload(payload, analysis_result, subject_name)
        ingest_run = await self.pipeline_service.create_ingest_run(session, ingest_payload)
        yield self._event("ingest_run", {"ingest_run": ingest_run.id, "status": ingest_run.status})

        simulation_payload = self._build_simulation_payload(payload, domain_id, subject_id, subject_name)
        simulation_run = await self.simulation_service.create_simulation_run(session, simulation_payload)
        yield self._event(
            "simulation_run",
            {
                "run_id": simulation_run.id,
                "status": simulation_run.status,
                "domain_id": simulation_run.domain_id,
            },
        )

        debate_context_lines = await self._build_debate_context_lines(
            session=session,
            payload=payload,
            analysis_result=analysis_result,
            ingest_run_id=ingest_run.id,
        )

        # Use the detected suggested topic when debate is warranted.
        if debate_suggestion.warranted:
            debate_topic = debate_suggestion.suggested_topic
            trigger_type = "auto_conflict_detection"
        else:
            debate_topic = self._debate_topic(domain_id, subject_name)
            trigger_type = "pivot_decision"

        debate_id: str | None = None
        async for debate_event in self.debate_service.stream_debate(
            session,
            DebateTriggerRequest(
                run_id=simulation_run.id,
                topic=debate_topic,
                trigger_type=trigger_type,
                target_type="run",
                context_lines=debate_context_lines,
            ),
        ):
            yield self._event(debate_event.event, debate_event.payload)
            if debate_event.event == "debate_verdict":
                debate_id = debate_event.payload.get("debate_id")
        debate = await self.debate_service.get_debate(session, debate_id) if debate_id is not None else None

        result = None
        try_errors: list[str] = []
        try:
            workbench = await self.workbench_service.build_run_workbench(session, simulation_run.id)
        except Exception as exc:
            _logger.warning("workbench build failed", exc_info=True)
            try_errors.append(f"workbench: {exc}")
            workbench = RunWorkbenchRead.model_construct(
                run_id=simulation_run.id,
                domain_id=domain_id,
            )

        try:
            latest_report = await self._latest_report(session, domain_id, subject_id, simulation_run.id, payload.tenant_id)
        except Exception as exc:
            _logger.warning("report generation failed", exc_info=True)
            try_errors.append(f"report: {exc}")
            latest_report = None

        try:
            panel_discussion = await self._build_panel_discussion(payload, domain_id, subject_name, analysis_result, latest_report)
        except Exception as exc:
            _logger.warning("panel discussion failed", exc_info=True)
            try_errors.append(f"panel_discussion: {exc}")
            panel_discussion = []

        for message in panel_discussion:
            yield self._event("discussion", message.model_dump(mode="json"))

        result = StrategicAssistantResponse(
            topic=payload.topic,
            domain_id=domain_id,
            subject_id=subject_id,
            subject_name=subject_name,
            analysis=analysis_result,
            ingest_run=ingest_run,
            simulation_run=simulation_run,
            latest_report=GeneratedReportModel.model_validate(latest_report) if latest_report is not None else None,
            debate=debate,
            workbench=workbench,
            panel_discussion=panel_discussion,
            generated_at=datetime.now(timezone.utc),
        )

        try:
            session_record = await self._ensure_session_record(
                session,
                payload,
                domain_id,
                subject_id,
                subject_name,
            )
            if session_record is not None:
                result.session_id = session_record.id
                await self._store_run_snapshot(session, session_record, result)
        except Exception as exc:
            _logger.warning("session persist failed", exc_info=True)
            try_errors.append(f"session_persist: {exc}")
            try:
                await session.rollback()
            except Exception:
                _logger.warning("session rollback failed after persist error", exc_info=True)

        try:
            await self._auto_create_watch_rule(session, payload.topic, domain_id, payload.tick_count)
        except Exception:
            _logger.warning("auto watch rule creation failed", exc_info=True)
            try:
                await session.rollback()
            except Exception:
                _logger.warning("session rollback failed after watch rule error", exc_info=True)

        if try_errors:
            yield self._event("step", {
                "phase": "post_debate_errors",
                "message": "; ".join(try_errors),
                "status": "warning",
            })

        yield self._event("assistant_result", result.model_dump(mode="json"))

    async def _build_debate_context_lines(
        self,
        session: AsyncSession,
        payload: StrategicAssistantRequest,
        analysis_result: AnalysisResponse,
        ingest_run_id: str,
    ) -> list[str]:
        evidence_items = await self._load_session_evidence_items(
            session=session,
            payload=payload,
            current_ingest_run_id=ingest_run_id,
        )
        claims = await self._load_session_claims(session, evidence_items)

        return [
            f"User topic: {payload.topic}",
            f"Analysis summary: {analysis_result.summary}",
            self._format_evidence_context(evidence_items),
            self._format_claim_context(claims),
        ]

    async def _load_session_evidence_items(
        self,
        session: AsyncSession,
        payload: StrategicAssistantRequest,
        current_ingest_run_id: str,
    ) -> list[EvidenceItem]:
        ingest_run_ids = [current_ingest_run_id]
        if payload.session_id is not None:
            snapshot_rows = list(
                (
                    await session.scalars(
                        select(StrategicRunSnapshot)
                        .where(
                            StrategicRunSnapshot.session_id == payload.session_id,
                            StrategicRunSnapshot.ingest_run_id.is_not(None),
                        )
                        .order_by(StrategicRunSnapshot.generated_at.desc())
                        .limit(5)
                    )
                ).all()
            )
            ingest_run_ids.extend(
                row.ingest_run_id for row in snapshot_rows if row.ingest_run_id is not None
            )
        ingest_run_ids = list(dict.fromkeys(ingest_run_ids))

        evidence_items = list(
            (
                await session.scalars(
                    select(EvidenceItem)
                    .join(NormalizedItem, EvidenceItem.normalized_item_id == NormalizedItem.id)
                    .join(RawSourceItem, NormalizedItem.raw_source_item_id == RawSourceItem.id)
                    .where(RawSourceItem.ingest_run_id.in_(ingest_run_ids))
                    .order_by(EvidenceItem.confidence.desc(), EvidenceItem.created_at.desc())
                    .limit(20)
                )
            ).all()
        )
        if evidence_items or (payload.tenant_id is None and payload.preset_id is None):
            return evidence_items

        query = select(EvidenceItem).order_by(EvidenceItem.created_at.desc()).limit(20)
        if payload.tenant_id is not None:
            query = query.where(EvidenceItem.tenant_id == payload.tenant_id)
        if payload.preset_id is not None:
            query = query.where(EvidenceItem.preset_id == payload.preset_id)
        return list((await session.scalars(query)).all())

    async def _load_session_claims(
        self,
        session: AsyncSession,
        evidence_items: list[EvidenceItem],
    ) -> list[Claim]:
        evidence_ids = [item.id for item in evidence_items]
        if not evidence_ids:
            return []
        return list(
            (
                await session.scalars(
                    select(Claim)
                    .where(Claim.evidence_item_id.in_(evidence_ids))
                    .order_by(Claim.confidence.desc(), Claim.created_at.desc())
                    .limit(10)
                )
            ).all()
        )

    def _format_evidence_context(self, evidence_items: list[EvidenceItem]) -> str:
        if not evidence_items:
            return "Evidence items: none found for this strategic session."
        lines = ["Evidence items (max 20):"]
        for index, item in enumerate(evidence_items, start=1):
            title = self._clean_text(item.title)[:240]
            summary = self._clean_text(item.summary)[:500]
            source_url = self._clean_text(item.source_url)[:240]
            lines.append(
                f"{index}. id={item.id}; type={item.evidence_type}; "
                f"confidence={item.confidence:.2f}; source={source_url}"
            )
            lines.append(f"   title: {title}")
            lines.append(f"   summary: {summary}")
        return "\n".join(lines)

    def _format_claim_context(self, claims: list[Claim]) -> str:
        if not claims:
            return "Claims (max 10): none found for this strategic session."
        lines = ["Claims (max 10):"]
        for index, claim in enumerate(claims, start=1):
            statement = self._clean_text(claim.statement)[:500]
            reasoning = self._clean_text(claim.reasoning or "")[:300]
            lines.append(
                f"{index}. id={claim.id}; evidence_id={claim.evidence_item_id}; "
                f"kind={claim.kind}; status={claim.status}; confidence={claim.confidence:.2f}"
            )
            lines.append(f"   statement: {statement}")
            if reasoning:
                lines.append(f"   reasoning: {reasoning}")
        return "\n".join(lines)

    async def daily_brief(
        self,
        session: AsyncSession,
        payload: StrategicAssistantRequest,
    ) -> AnalysisResponse:
        analysis_payload = self._build_analysis_request(payload)
        analysis = await self.analysis_service.analyze(analysis_payload)
        subject_id, subject_name = self._resolve_subject(payload, analysis)
        session_record = await self._ensure_session_record(
            session,
            payload,
            analysis.domain_id,
            subject_id,
            subject_name,
        )
        if session_record is not None:
            await self._store_daily_brief(session, session_record, analysis)
        return analysis

    async def _auto_create_watch_rule(
        self,
        session: AsyncSession,
        topic: str,
        domain_id: str,
        tick_count: int | None,
    ) -> None:
        existing = await session.scalar(
            select(WatchRule.id).where(WatchRule.query == topic).limit(1)
        )
        if existing is not None:
            return

        now = utc_now()
        rule = WatchRule(
            name=topic[:255],
            domain_id=domain_id,
            query=topic,
            source_types=[
                "google_news",
                "reddit",
                "hacker_news",
                "github",
                "rss",
                "gdelt",
                "aviation",
            ],
            poll_interval_minutes=60,
            auto_trigger_simulation=True,
            auto_trigger_debate=True,
            change_significance_threshold="medium",
            enabled=True,
            tick_count=tick_count or 0,
            next_poll_at=now,
        )
        session.add(rule)
        await session.commit()

    async def create_session(
        self,
        session: AsyncSession,
        payload: StrategicAssistantRequest,
    ) -> StrategicSessionRead:
        session_record = await self._ensure_session_record(
            session,
            payload,
            payload.domain_id,
            payload.subject_id,
            self._clean_text(payload.subject_name or "") or None,
            force_create=True,
        )
        if session_record is None:
            raise RuntimeError("Strategic session could not be created.")
        await session.commit()
        await session.refresh(session_record)
        return StrategicSessionRead.model_validate(session_record)

    async def list_sessions(
        self,
        session: AsyncSession,
        tenant_id: str | None = None,
        preset_id: str | None = None,
        limit: int = 12,
    ) -> list[StrategicSessionRead]:
        query = select(StrategicSession).order_by(StrategicSession.updated_at.desc())
        if tenant_id is not None:
            query = query.where(StrategicSession.tenant_id == tenant_id)
        if preset_id is not None:
            query = query.where(StrategicSession.preset_id == preset_id)
        sessions = list((await session.scalars(query.limit(limit))).all())
        return [StrategicSessionRead.model_validate(item) for item in sessions]

    async def get_session_detail(
        self,
        session: AsyncSession,
        session_id: str,
        brief_limit: int = 10,
        run_limit: int = 10,
    ) -> StrategicSessionDetailRead | None:
        session_record = await session.get(StrategicSession, session_id)
        if session_record is None:
            return None
        brief_rows = list(
            (
                await session.scalars(
                    select(StrategicBriefRecord)
                    .where(StrategicBriefRecord.session_id == session_id)
                    .order_by(StrategicBriefRecord.generated_at.desc())
                    .limit(brief_limit)
                )
            ).all()
        )
        run_rows = list(
            (
                await session.scalars(
                    select(StrategicRunSnapshot)
                    .where(StrategicRunSnapshot.session_id == session_id)
                    .order_by(StrategicRunSnapshot.generated_at.desc())
                    .limit(run_limit)
                )
            ).all()
        )
        latest_predictions = await self._latest_prediction_versions_by_run(session, run_rows)
        return StrategicSessionDetailRead(
            session=StrategicSessionRead.model_validate(session_record),
            daily_briefs=[self._brief_record_read(item) for item in brief_rows],
            recent_runs=[
                self._run_snapshot_read(
                    item,
                    latest_prediction_version=latest_predictions.get(item.simulation_run_id or ""),
                )
                for item in run_rows
            ],
        )

    async def load_session_payload(
        self,
        session: AsyncSession,
        session_id: str,
    ) -> StrategicAssistantRequest | None:
        session_record = await session.get(StrategicSession, session_id)
        if session_record is None:
            return None
        return self._build_request_from_session(session_record)

    async def _ensure_session_record(
        self,
        session: AsyncSession,
        payload: StrategicAssistantRequest,
        domain_id: str,
        subject_id: str | None,
        subject_name: str | None,
        *,
        force_create: bool = False,
    ) -> StrategicSession | None:
        should_persist = force_create or payload.session_id is not None or payload.session_name is not None
        if not should_persist:
            return None

        session_record: StrategicSession | None = None
        if payload.session_id:
            session_record = await session.get(StrategicSession, payload.session_id)

        if session_record is None:
            session_record = (
                StrategicSession(id=payload.session_id)
                if payload.session_id is not None
                else StrategicSession()
            )

        session_record.name = self._session_display_name(payload, subject_name, domain_id)
        session_record.topic = payload.topic
        session_record.domain_id = domain_id
        session_record.subject_id = subject_id
        session_record.subject_name = subject_name
        session_record.market = payload.market or None
        session_record.theater = payload.theater
        session_record.actor_template = payload.actor_template
        session_record.tick_count = payload.tick_count
        session_record.tenant_id = payload.tenant_id
        session_record.preset_id = payload.preset_id
        session_record.source_preferences = self._source_preferences(payload)
        session_record.auto_refresh_enabled = payload.auto_refresh_enabled
        session_record.refresh_timezone = self._normalize_timezone(payload.refresh_timezone)
        session_record.refresh_hour_local = payload.refresh_hour_local
        if session_record.auto_refresh_enabled:
            session_record.next_refresh_at = self._next_refresh_at(
                session_record.refresh_timezone,
                session_record.refresh_hour_local,
                reference=session_record.latest_briefed_at,
            )
        else:
            session_record.next_refresh_at = None
            session_record.refresh_lease_owner = None
            session_record.refresh_lease_expires_at = None

        session.add(session_record)
        await session.flush()
        return session_record

    async def _store_daily_brief(
        self,
        session: AsyncSession,
        session_record: StrategicSession,
        analysis: AnalysisResponse,
    ) -> StrategicBriefRecordRead:
        pending_hypotheses = await self._recent_hypotheses(
            session,
            session_record,
            statuses={"PENDING"},
        )
        verified_hypotheses = await self._recent_hypotheses(
            session,
            session_record,
            statuses={"CONFIRMED", "REFUTED", "PARTIAL"},
        )
        analysis_payload = analysis.model_dump(mode="json")
        analysis_payload["intelligence_brief"] = {
            "new_evidence_count": len(analysis.sources),
            "source_types": sorted({source.source_type for source in analysis.sources}),
            "trend_watch": analysis.findings[:5],
            "pending_hypotheses": [item.prediction for item in pending_hypotheses[:5]],
            "verified_hypotheses": [
                {
                    "prediction": item.prediction,
                    "status": item.verification_status,
                    "actual_outcome": item.actual_outcome,
                }
                for item in verified_hypotheses[:5]
            ],
            "judgment_update": (
                "Review the last posture because new sources or verified hypotheses changed."
                if analysis.sources or verified_hypotheses
                else "No material update detected in this refresh."
            ),
        }
        record = StrategicBriefRecord(
            session_id=session_record.id,
            tenant_id=session_record.tenant_id,
            preset_id=session_record.preset_id,
            domain_id=analysis.domain_id,
            summary=analysis.summary,
            source_count=len(analysis.sources),
            analysis_payload=analysis_payload,
            generated_at=analysis.generated_at,
        )
        session_record.latest_brief_summary = analysis.summary
        session_record.latest_briefed_at = analysis.generated_at
        session_record.refresh_lease_owner = None
        session_record.refresh_lease_expires_at = None
        session_record.last_refresh_error = None
        if session_record.auto_refresh_enabled:
            session_record.next_refresh_at = self._next_refresh_at(
                session_record.refresh_timezone,
                session_record.refresh_hour_local,
                reference=analysis.generated_at,
            )
        session.add(record)
        await session.commit()
        return self._brief_record_read(record)

    async def _recent_hypotheses(
        self,
        session: AsyncSession,
        session_record: StrategicSession,
        statuses: set[str],
    ) -> list[Hypothesis]:
        query = select(Hypothesis).where(Hypothesis.verification_status.in_(statuses))
        if session_record.tenant_id is not None:
            query = query.where(Hypothesis.tenant_id == session_record.tenant_id)
        if session_record.preset_id is not None:
            query = query.where(Hypothesis.preset_id == session_record.preset_id)
        return list((await session.scalars(query.order_by(Hypothesis.updated_at.desc()).limit(10))).all())

    async def _store_run_snapshot(
        self,
        session: AsyncSession,
        session_record: StrategicSession,
        result: StrategicAssistantResponse,
    ) -> StrategicRunSnapshotRead:
        latest_report_id = result.latest_report.id if result.latest_report is not None else None
        debate_id = result.debate.id if result.debate is not None else None
        snapshot = StrategicRunSnapshot(
            session_id=session_record.id,
            tenant_id=session_record.tenant_id,
            preset_id=session_record.preset_id,
            ingest_run_id=result.ingest_run.id,
            simulation_run_id=result.simulation_run.id,
            debate_id=debate_id,
            generated_report_id=latest_report_id,
            result_payload=result.model_dump(mode="json"),
            generated_at=result.generated_at,
        )
        session_record.latest_run_summary = (
            result.latest_report.summary if result.latest_report is not None else result.analysis.summary
        )
        session_record.latest_debate_verdict = (
            result.debate.verdict.verdict if result.debate is not None and result.debate.verdict is not None else None
        )
        session_record.latest_run_at = result.generated_at
        session.add(snapshot)
        await session.commit()
        return self._run_snapshot_read(snapshot)

    def _build_request_from_session(
        self,
        session_record: StrategicSession,
    ) -> StrategicAssistantRequest:
        preferences = session_record.source_preferences or {}
        return StrategicAssistantRequest(
            session_id=session_record.id,
            session_name=session_record.name,
            topic=session_record.topic,
            domain_id=session_record.domain_id,  # type: ignore[arg-type]
            subject_id=session_record.subject_id,
            subject_name=session_record.subject_name,
            market=session_record.market or "ai",
            theater=session_record.theater,
            actor_template=session_record.actor_template,
            tick_count=session_record.tick_count,
            tenant_id=session_record.tenant_id,
            preset_id=session_record.preset_id,
            auto_refresh_enabled=session_record.auto_refresh_enabled,
            refresh_timezone=session_record.refresh_timezone,
            refresh_hour_local=session_record.refresh_hour_local,
            auto_fetch_news=preferences.get("auto_fetch_news", True),
            include_google_news=preferences.get("include_google_news", True),
            include_reddit=preferences.get("include_reddit", True),
            include_hacker_news=preferences.get("include_hacker_news", True),
            include_github=preferences.get("include_github", True),
            include_rss_feeds=preferences.get("include_rss_feeds", True),
            include_gdelt=preferences.get("include_gdelt", True),
            include_weather=preferences.get("include_weather", False),
            include_aviation=preferences.get("include_aviation", False),
            include_x=preferences.get("include_x", True),
            source_types=preferences.get("source_types", []),
            max_source_items=preferences.get("max_source_items", {}),
            max_news_items=preferences.get("max_news_items", 5),
            max_tech_items=preferences.get("max_tech_items", 3),
            max_reddit_items=preferences.get("max_reddit_items", 3),
            max_github_items=preferences.get("max_github_items", 3),
            max_rss_items=preferences.get("max_rss_items", 3),
            max_gdelt_items=preferences.get("max_gdelt_items", 3),
            max_weather_items=preferences.get("max_weather_items", 1),
            max_aviation_items=preferences.get("max_aviation_items", 1),
            max_x_items=preferences.get("max_x_items", 3),
        )

    def _brief_record_read(self, row: StrategicBriefRecord) -> StrategicBriefRecordRead:
        return StrategicBriefRecordRead(
            id=row.id,
            session_id=row.session_id,
            tenant_id=row.tenant_id,
            preset_id=row.preset_id,
            domain_id=row.domain_id,
            summary=row.summary,
            source_count=row.source_count,
            analysis=AnalysisResponse.model_validate(row.analysis_payload),
            generated_at=row.generated_at,
        )

    async def _latest_prediction_versions_by_run(
        self,
        session: AsyncSession,
        rows: list[StrategicRunSnapshot],
    ) -> dict[str, dict[str, Any]]:
        run_ids = [row.simulation_run_id for row in rows if row.simulation_run_id is not None]
        if not run_ids:
            return {}
        versions = list(
            (
                await session.scalars(
                    select(PredictionVersion)
                    .where(PredictionVersion.run_id.in_(run_ids))
                    .order_by(
                        PredictionVersion.run_id.asc(),
                        PredictionVersion.version_number.desc(),
                    )
                )
            ).all()
        )
        latest: dict[str, dict[str, Any]] = {}
        for version in versions:
            if version.run_id is None or version.run_id in latest:
                continue
            latest[version.run_id] = self._prediction_version_payload(version)
        return latest

    def _run_snapshot_read(
        self,
        row: StrategicRunSnapshot,
        latest_prediction_version: dict[str, Any] | None = None,
    ) -> StrategicRunSnapshotRead:
        return StrategicRunSnapshotRead(
            id=row.id,
            session_id=row.session_id,
            tenant_id=row.tenant_id,
            preset_id=row.preset_id,
            ingest_run_id=row.ingest_run_id,
            simulation_run_id=row.simulation_run_id,
            debate_id=row.debate_id,
            generated_report_id=row.generated_report_id,
            latest_prediction_version=latest_prediction_version
            or self._latest_prediction_from_payload(row.result_payload),
            result=StrategicAssistantResponse.model_validate(row.result_payload),
            generated_at=row.generated_at,
        )

    def _latest_prediction_from_payload(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        workbench = (payload.get("workbench") if isinstance(payload, dict) else None) or {}
        versions = workbench.get("prediction_versions") or []
        if not versions:
            return None
        return max(versions, key=lambda item: int(item.get("version_number") or 0))

    def _prediction_version_payload(self, version: PredictionVersion) -> dict[str, Any]:
        return {
            "id": version.id,
            "series_id": version.series_id,
            "run_id": version.run_id,
            "base_version_id": version.base_version_id,
            "parent_version_id": version.parent_version_id,
            "hypothesis_id": version.hypothesis_id,
            "decision_option_id": version.decision_option_id,
            "version_number": version.version_number,
            "trigger_type": version.trigger_type,
            "trigger_ref_id": version.trigger_ref_id,
            "trigger_event_id": version.trigger_event_id,
            "prediction_text": version.prediction_text,
            "time_horizon": version.time_horizon,
            "probability": version.probability,
            "confidence": version.confidence,
            "status": version.status,
            "summary_delta": version.summary_delta,
            "version_metadata": version.version_metadata,
            "created_at": version.created_at,
            "updated_at": version.updated_at,
            "superseded_at": version.superseded_at,
        }

    def _session_display_name(
        self,
        payload: StrategicAssistantRequest,
        subject_name: str | None,
        domain_id: str,
    ) -> str:
        preferred = self._clean_text(payload.session_name or "")
        if preferred:
            return preferred
        if subject_name:
            return subject_name
        return self._derive_subject_name(payload.topic, domain_id)

    def _source_preferences(self, payload: StrategicAssistantRequest) -> dict[str, Any]:
        return {
            "auto_fetch_news": payload.auto_fetch_news,
            "include_google_news": payload.include_google_news,
            "include_reddit": payload.include_reddit,
            "include_hacker_news": payload.include_hacker_news,
            "include_github": payload.include_github,
            "include_rss_feeds": payload.include_rss_feeds,
            "include_gdelt": payload.include_gdelt,
            "include_weather": payload.include_weather,
            "include_aviation": payload.include_aviation,
            "include_x": payload.include_x,
            "source_types": payload.source_types,
            "max_source_items": payload.max_source_items,
            "max_news_items": payload.max_news_items,
            "max_tech_items": payload.max_tech_items,
            "max_reddit_items": payload.max_reddit_items,
            "max_github_items": payload.max_github_items,
            "max_rss_items": payload.max_rss_items,
            "max_gdelt_items": payload.max_gdelt_items,
            "max_weather_items": payload.max_weather_items,
            "max_aviation_items": payload.max_aviation_items,
            "max_x_items": payload.max_x_items,
        }

    def _normalize_timezone(self, value: str | None) -> str:
        candidate = self._clean_text(value or "") or "UTC"
        try:
            ZoneInfo(candidate)
        except ZoneInfoNotFoundError:
            return "UTC"
        return candidate

    def _next_refresh_at(
        self,
        refresh_timezone: str,
        refresh_hour_local: int,
        *,
        reference: datetime | None = None,
    ) -> datetime:
        tz = ZoneInfo(self._normalize_timezone(refresh_timezone))
        base = reference or datetime.now(timezone.utc)
        if base.tzinfo is None:
            base = base.replace(tzinfo=timezone.utc)
        local_base = base.astimezone(tz)
        scheduled_local = local_base.replace(
            hour=refresh_hour_local,
            minute=0,
            second=0,
            microsecond=0,
        )
        if scheduled_local <= local_base:
            scheduled_local = scheduled_local + timedelta(days=1)
        return scheduled_local.astimezone(timezone.utc)

    def _build_analysis_request(self, payload: StrategicAssistantRequest) -> AnalysisRequest:
        return AnalysisRequest(
            content=payload.topic,
            domain_id=payload.domain_id,
            auto_fetch_news=payload.auto_fetch_news,
            include_google_news=payload.include_google_news,
            include_reddit=payload.include_reddit,
            include_hacker_news=payload.include_hacker_news,
            include_github=payload.include_github,
            include_rss_feeds=payload.include_rss_feeds,
            include_gdelt=payload.include_gdelt,
            include_weather=payload.include_weather,
            include_aviation=payload.include_aviation,
            include_x=payload.include_x,
            source_types=payload.source_types,
            max_source_items=payload.max_source_items,
            max_news_items=payload.max_news_items,
            max_tech_items=payload.max_tech_items,
            max_reddit_items=payload.max_reddit_items,
            max_github_items=payload.max_github_items,
            max_rss_items=payload.max_rss_items,
            max_gdelt_items=payload.max_gdelt_items,
            max_weather_items=payload.max_weather_items,
            max_aviation_items=payload.max_aviation_items,
            max_x_items=payload.max_x_items,
        )

    def _build_ingest_payload(
        self,
        payload: StrategicAssistantRequest,
        analysis: AnalysisResponse,
        subject_name: str,
    ) -> IngestRunCreate:
        items = [
            {
                "source_type": "analyst_note",
                "source_url": f"https://local.planagent/assistant/{self._slugify(subject_name)}",
                "title": subject_name,
                "content_text": payload.topic,
                "source_metadata": {
                    "origin": "strategic_assistant",
                    "role": "user_prompt",
                },
            }
        ]
        for source in analysis.sources:
            items.append(
                {
                    "source_type": source.source_type,
                    "source_url": source.url,
                    "title": source.title,
                    "content_text": source.summary,
                    "published_at": self._parse_published_at(source.published_at),
                    "source_metadata": {
                        "origin": "analysis_source",
                        "published_at": source.published_at,
                    },
                }
            )
        return IngestRunCreate(
            requested_by="strategic-assistant",
            tenant_id=payload.tenant_id,
            preset_id=payload.preset_id,
            execution_mode="INLINE",
            items=items,
        )

    def _build_simulation_payload(
        self,
        payload: StrategicAssistantRequest,
        domain_id: str,
        subject_id: str,
        subject_name: str,
    ) -> SimulationRunCreate:
        tick_count = payload.tick_count or (4 if domain_id == "corporate" else 5)
        if domain_id == "military":
            return SimulationRunCreate(
                domain_id="military",
                force_id=subject_id,
                force_name=subject_name,
                theater=payload.theater or "contested-theater",
                tick_count=tick_count,
                actor_template=payload.actor_template or "brigade",
                tenant_id=payload.tenant_id,
                preset_id=payload.preset_id,
                execution_mode="INLINE",
            )
        return SimulationRunCreate(
            domain_id="corporate",
            company_id=subject_id,
            company_name=subject_name,
            market=payload.market or self._default_market(payload.topic),
            tick_count=tick_count,
            actor_template=payload.actor_template or self._default_actor_template(payload.market or ""),
            tenant_id=payload.tenant_id,
            preset_id=payload.preset_id,
            execution_mode="INLINE",
        )

    async def _latest_report(
        self,
        session: AsyncSession,
        domain_id: str,
        subject_id: str,
        run_id: str,
        tenant_id: str | None,
    ) -> Any | None:
        if domain_id == "corporate":
            return await self.simulation_service.latest_company_report(
                session,
                subject_id,
                tenant_id=tenant_id,
            )
        return (
            await session.scalars(
                select(GeneratedReport)
                .where(GeneratedReport.run_id == run_id)
                .order_by(GeneratedReport.created_at.desc())
                .limit(1)
            )
        ).first()

    async def _build_panel_discussion(
        self,
        payload: StrategicAssistantRequest,
        domain_id: str,
        subject_name: str,
        analysis: AnalysisResponse,
        latest_report: Any | None,
    ) -> list[PanelDiscussionMessageRead]:
        report_summary = getattr(latest_report, "summary", "") if latest_report is not None else ""
        openai_service = self.analysis_service.openai_service
        messages: list[PanelDiscussionMessageRead] = []
        role_map = [
            ("primary", "Lead Strategist", "support"),
            ("extraction", "Evidence Auditor", "monitor"),
            ("x_search", "Social Pulse", "challenge"),
            ("report", "Operations Planner", "support"),
        ]
        if openai_service is not None:
            for target, label, fallback_stance in role_map:
                if not openai_service.is_configured(target):
                    continue
                perspective = await openai_service.generate_panel_perspective(
                    target=target,
                    label=label,
                    topic=payload.topic,
                    domain_id=domain_id,
                    subject_name=subject_name,
                    analysis_summary=analysis.summary,
                    findings=analysis.findings,
                    report_summary=report_summary,
                )
                if perspective is None:
                    continue
                messages.append(
                    PanelDiscussionMessageRead(
                        participant_id=f"panel-{target}",
                        label=label,
                        model_target=target,
                        stance=perspective.stance or fallback_stance,
                        summary=perspective.summary,
                        key_points=perspective.key_points,
                        recommendation=perspective.recommendation,
                        confidence=perspective.confidence,
                    )
                )
        if messages:
            return messages

        summary_short = analysis.summary[:220]
        recs = analysis.recommendations or [
            "Continue collecting confirming evidence before making an irreversible move."
        ]
        return [
            PanelDiscussionMessageRead(
                participant_id="panel-primary",
                label="Lead Strategist",
                model_target="primary",
                stance="support",
                summary=summary_short,
                key_points=analysis.findings[:3],
                recommendation=recs[0],
                confidence=0.72,
            ),
            PanelDiscussionMessageRead(
                participant_id="panel-extraction",
                label="Evidence Auditor",
                model_target="extraction",
                stance="monitor",
                summary="The current recommendation is directionally useful, but it still depends on source quality and repeated confirmation.",
                key_points=[
                    f"Fetched {len(analysis.sources)} public source(s) across news, reports, and social channels.",
                    "Treat single-source or low-detail summaries as weak evidence until they recur.",
                    "Use the simulation as a stress test, not as proof that reality will follow the same path.",
                ],
                recommendation="Keep monitoring source convergence before escalating commitment.",
                confidence=0.66,
            ),
            PanelDiscussionMessageRead(
                participant_id="panel-report",
                label="Operations Planner",
                model_target="report",
                stance="challenge" if domain_id == "military" else "support",
                summary="The next move should stay practical: convert the assessment into one or two actions that can be measured within the next cycle.",
                key_points=[
                    "Focus on the highest-leverage move suggested by the current evidence.",
                    "Track whether the daily source flow strengthens or weakens the working hypothesis.",
                    "Update the posture when the evidence graph or debate verdict materially changes.",
                ],
                recommendation=recs[min(1, len(recs) - 1)],
                confidence=0.69,
            ),
        ]

    def _resolve_subject(
        self,
        payload: StrategicAssistantRequest,
        analysis: AnalysisResponse,
    ) -> tuple[str, str]:
        subject_name = self._clean_text(payload.subject_name or "")
        if not subject_name:
            subject_name = self._derive_subject_name(payload.topic, analysis.domain_id)
        subject_id = payload.subject_id or self._slugify(subject_name)
        return subject_id, subject_name

    def _derive_subject_name(self, topic: str, domain_id: str) -> str:
        cleaned = self._clean_text(topic)
        for prefix in ["分析", "研判", "推演", "评估", "帮我看", "请分析"]:
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix) :].strip(" ：:，,")
        if len(cleaned) > 42:
            cleaned = cleaned[:42].rstrip()
        if domain_id == "military" and not cleaned.endswith("Task Force"):
            return cleaned or "Field Task Force"
        return cleaned or ("Strategic Target" if domain_id == "military" else "Strategic Company")

    def _debate_topic(self, domain_id: str, subject_name: str) -> str:
        if domain_id == "military":
            return f"Should {subject_name} adjust its current operational posture?"
        return f"Should {subject_name} change its current business posture?"

    # ------------------------------------------------------------------
    # Auto-trigger debate: conflict / uncertainty detection
    # ------------------------------------------------------------------

    def _detect_conflicting_signals(
        self,
        analysis: AnalysisResponse,
        domain_id: str,
        subject_name: str,
        panel_messages: list[PanelDiscussionMessageRead] | None = None,
    ) -> DebateSuggestion:
        """Evaluate analysis results for conflicting signals or high uncertainty.

        Detection criteria (any one triggers a suggestion):
        1) Derived analysis confidence < 60%
        2) Multiple panel agents disagree on recommendation stance
        3) Both risk and opportunity scores are high (>= 0.4 each)
        """
        reasons: list[str] = []
        conflicting_signals: list[str] = []

        # --- Criterion 1: derived confidence ---
        confidence = self._derive_analysis_confidence(analysis)
        if confidence < 0.60:
            reasons.append(
                f"Analysis confidence is low ({confidence:.0%}), suggesting the evidence is thin or ambiguous."
            )
            conflicting_signals.append("low_confidence")

        # --- Criterion 2: panel disagreement ---
        if panel_messages:
            stances = {msg.stance for msg in panel_messages}
            if "support" in stances and "challenge" in stances:
                reasons.append(
                    "Panel agents disagree on stance: some support while others challenge the direction."
                )
                conflicting_signals.append("panel_disagreement")
            # Also check if average confidence across panels is low
            avg_panel_conf = sum(m.confidence for m in panel_messages) / len(panel_messages)
            if avg_panel_conf < 0.60:
                reasons.append(
                    f"Average panel confidence is low ({avg_panel_conf:.0%}), indicating broad uncertainty."
                )
                conflicting_signals.append("low_panel_confidence")

        # --- Criterion 3: high risk + high opportunity ---
        risk_score, opportunity_score = self._compute_risk_opportunity_scores(analysis)
        if risk_score >= 0.4 and opportunity_score >= 0.4:
            reasons.append(
                f"Both risk signals ({risk_score:.0%}) and opportunity signals ({opportunity_score:.0%}) are strong."
            )
            conflicting_signals.append("risk_opportunity_tension")

        warranted = len(reasons) > 0

        # Build a suggested debate topic that surfaces the specific tension.
        if warranted:
            tension_label = "conflicting signals"
            if conflicting_signals:
                tension_label = conflicting_signals[0].replace("_", " ")
            suggested_topic = (
                f"Given {tension_label} around {subject_name}, "
                f"should the current strategy be revised?"
            )
        else:
            suggested_topic = self._debate_topic(domain_id, subject_name)

        return DebateSuggestion(
            warranted=warranted,
            confidence=confidence,
            reasons=reasons,
            suggested_topic=suggested_topic,
            conflicting_signals=conflicting_signals,
            risk_score=risk_score,
            opportunity_score=opportunity_score,
        )

    def _derive_analysis_confidence(self, analysis: AnalysisResponse) -> float:
        """Heuristic confidence score (0.0–1.0) derived from analysis richness.

        Signals:
        - Number of sources consulted
        - Number of findings produced
        - Length / specificity of the summary
        - Presence of uncertainty language in the summary
        """
        score = 0.5  # baseline

        # Source count contribution (up to +0.2)
        source_count = len(analysis.sources)
        score += min(source_count / 15.0, 0.2)

        # Findings count contribution (up to +0.15)
        findings_count = len(analysis.findings)
        score += min(findings_count / 6.0, 0.15)

        # Recommendations count contribution (up to +0.1)
        recs_count = len(analysis.recommendations)
        score += min(recs_count / 5.0, 0.1)

        # Summary quality: longer, more specific summaries indicate confidence
        summary_len = len(analysis.summary)
        if summary_len > 200:
            score += 0.05
        elif summary_len < 50:
            score -= 0.1

        # Penalty: uncertainty language in summary
        summary_lower = analysis.summary.lower()
        uncertainty_hits = sum(1 for kw in _UNCERTAINTY_KEYWORDS if kw in summary_lower)
        score -= min(uncertainty_hits * 0.05, 0.2)

        # Penalty: very few sources
        if source_count == 0:
            score -= 0.15

        return max(0.0, min(1.0, score))

    def _compute_risk_opportunity_scores(
        self, analysis: AnalysisResponse
    ) -> tuple[float, float]:
        """Scan findings + recommendations for risk and opportunity keyword density.

        Returns (risk_score, opportunity_score), each in [0.0, 1.0].
        """
        text_pool = " ".join(
            [analysis.summary] + analysis.findings + analysis.recommendations
        ).lower()
        words = set(re.findall(r"[a-z]+", text_pool))
        if not words:
            return 0.0, 0.0

        risk_hits = len(words & _RISK_KEYWORDS)
        opp_hits = len(words & _OPPORTUNITY_KEYWORDS)
        # Normalize: 4+ distinct keyword hits → score 1.0
        risk_score = min(risk_hits / 4.0, 1.0)
        opp_score = min(opp_hits / 4.0, 1.0)
        return risk_score, opp_score

    def _default_actor_template(self, market: str) -> str:
        normalized = market.strip().lower()
        if normalized in {"enterprise-agents", "developer-tools", "developer-tools-saas", "saas"}:
            return "developer_tools_saas"
        return "ai_model_provider"

    def _default_market(self, topic: str) -> str:
        lowered = topic.lower()
        if "agent" in lowered or "智能体" in topic:
            return "enterprise-agents"
        return "ai"

    def _parse_published_at(self, value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            if value.endswith("Z"):
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            return datetime.fromisoformat(value)
        except ValueError:
            try:
                return parsedate_to_datetime(value)
            except (TypeError, ValueError, IndexError):
                return None

    def _slugify(self, value: str) -> str:
        ascii_value = value.lower()
        tokens = _SLUG_TOKEN_RE.findall(ascii_value)
        if tokens:
            return "-".join(tokens[:8])
        compact = _WHITESPACE_RE.sub("-", value.strip())
        return compact[:40] or "strategic-subject"

    def _clean_text(self, value: str) -> str:
        return _WHITESPACE_RE.sub(" ", value or "").strip()

    def _event(self, event: str, payload: dict[str, Any]) -> AssistantEvent:
        return AssistantEvent(event=event, payload=payload)
