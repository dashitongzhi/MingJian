from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import re
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from planagent.config import get_settings
from planagent.domain.api import (
    AnalysisRequest,
    AnalysisResponse,
    IngestRunCreate,
    PanelDiscussionMessageRead,
    RecommendationVersionRead,
    SimulationRunCreate,
    StrategicAssistantRequest,
    StrategicAssistantResponse,
    StrategicSessionDetailRead,
    StrategicSessionRead,
    RunWorkbenchRead,
)
from planagent.domain.models import (
    Claim,
    EvidenceItem,
    GeneratedReport,
    NormalizedItem,
    RecommendationVersion,
    RawSourceItem,
    StrategicRunSnapshot,
    WatchRule,
)
from planagent.domain.types import GeneratedReportModel
from planagent.services.analysis import AutomatedAnalysisService
from planagent.services.assistant_conflicts import (
    AssistantConflictDetector,
    DebateSuggestion,
)
from planagent.services.assistant_sessions import StrategicSessionPersistence
from planagent.services.community_monitoring import (
    CommunityMonitoringService,
    watch_rule_monitoring_payload,
)
from planagent.services.debate import (
    DebateCommand,
    DebateFinished,
    DebateTarget,
    DebateWorkflow,
)
from planagent.services.debate._legacy import _legacy_event_from_observation
from planagent.services.pipeline import PhaseOnePipelineService
from planagent.services.recommendations import RecommendationVersionService
from planagent.services.simulation import SimulationService
from planagent.services.workbench import WorkbenchService

_WHITESPACE_RE = re.compile(r"\s+")
_SLUG_TOKEN_RE = re.compile(r"[a-z0-9]+")
_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AssistantEvent:
    event: str
    payload: dict[str, Any]


_POST_DEBATE_PUBLIC_ERRORS = {
    "workbench": "Workbench generation failed",
    "report": "Report generation failed",
    "panel_discussion": "Panel discussion failed",
    "session_persist": "Session persistence failed",
}


class StrategicAssistantService:
    def __init__(
        self,
        analysis_service: AutomatedAnalysisService,
        pipeline_service: PhaseOnePipelineService,
        simulation_service: SimulationService,
        debate_workflow: DebateWorkflow,
        workbench_service: WorkbenchService,
    ) -> None:
        self.analysis_service = analysis_service
        self.pipeline_service = pipeline_service
        self.simulation_service = simulation_service
        self.debate_workflow = debate_workflow
        self.workbench_service = workbench_service
        self.recommendation_service = RecommendationVersionService()
        self.monitoring_service = CommunityMonitoringService(get_settings())
        self.session_persistence = StrategicSessionPersistence(self.recommendation_service)
        self.conflict_detector = AssistantConflictDetector()

    async def run(
        self,
        session: AsyncSession,
        payload: StrategicAssistantRequest,
        recommendation_trigger_type: str | None = None,
        recommendation_significance: str | None = None,
        recommendation_watch_rule_id: str | None = None,
        recommendation_trigger_source_change_id: str | None = None,
        recommendation_source_change_ids: list[str] | None = None,
        recommendation_change_summary: str | None = None,
    ) -> StrategicAssistantResponse:
        final_result: StrategicAssistantResponse | None = None
        async for event in self.stream(
            session,
            payload,
            recommendation_trigger_type=recommendation_trigger_type,
            recommendation_significance=recommendation_significance,
            recommendation_watch_rule_id=recommendation_watch_rule_id,
            recommendation_trigger_source_change_id=recommendation_trigger_source_change_id,
            recommendation_source_change_ids=recommendation_source_change_ids,
            recommendation_change_summary=recommendation_change_summary,
        ):
            if event.event == "assistant_result":
                final_result = StrategicAssistantResponse.model_validate(event.payload)
        if final_result is None:
            raise RuntimeError("Strategic assistant finished without a result payload.")
        return final_result

    async def stream(
        self,
        session: AsyncSession,
        payload: StrategicAssistantRequest,
        recommendation_trigger_type: str | None = None,
        recommendation_significance: str | None = None,
        recommendation_watch_rule_id: str | None = None,
        recommendation_trigger_source_change_id: str | None = None,
        recommendation_source_change_ids: list[str] | None = None,
        recommendation_change_summary: str | None = None,
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
        debate_suggestion = self.conflict_detector.detect(
            analysis=analysis_result,
            domain_id=domain_id,
            subject_name=subject_name,
        )
        yield self._event(
            "debate_suggested",
            {
                "warranted": debate_suggestion.warranted,
                "confidence": round(debate_suggestion.confidence, 4),
                "reasons": debate_suggestion.reasons,
                "suggested_topic": debate_suggestion.suggested_topic,
                "conflicting_signals": debate_suggestion.conflicting_signals,
                "risk_score": round(debate_suggestion.risk_score, 4),
                "opportunity_score": round(debate_suggestion.opportunity_score, 4),
            },
        )

        ingest_payload = self._build_ingest_payload(payload, analysis_result, subject_name)
        ingest_run = await self.pipeline_service.create_ingest_run(session, ingest_payload)
        yield self._event("ingest_run", {"ingest_run": ingest_run.id, "status": ingest_run.status})

        simulation_payload = self._build_simulation_payload(
            payload, domain_id, subject_id, subject_name
        )
        simulation_run = await self.simulation_service.create_simulation_run(
            session, simulation_payload
        )
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
            trigger_type = "conflict_resolution"
        else:
            debate_topic = self._debate_topic(domain_id, subject_name)
            trigger_type = "pivot_decision"

        debate = None
        async for observation in self.debate_workflow.observe(
            session,
            DebateCommand(
                target=DebateTarget.run(simulation_run.id),
                topic=debate_topic,
                trigger_type=trigger_type,
                context=tuple(debate_context_lines),
            ),
        ):
            debate_event = _legacy_event_from_observation(observation)
            yield self._event(debate_event.event, debate_event.payload)
            if isinstance(observation, DebateFinished):
                debate = observation.debate

        result = None
        try_errors: list[str] = []
        try:
            workbench = await self.workbench_service.build_run_workbench(session, simulation_run.id)
        except Exception:
            _logger.warning("workbench build failed", exc_info=True)
            try_errors.append(f"workbench: {_POST_DEBATE_PUBLIC_ERRORS['workbench']}")
            workbench = RunWorkbenchRead.model_construct(
                run_id=simulation_run.id,
                domain_id=domain_id,
            )

        try:
            latest_report = await self._latest_report(
                session, domain_id, subject_id, simulation_run.id, payload.tenant_id
            )
        except Exception:
            _logger.warning("report generation failed", exc_info=True)
            try_errors.append(f"report: {_POST_DEBATE_PUBLIC_ERRORS['report']}")
            latest_report = None

        try:
            panel_discussion = await self._build_panel_discussion(
                payload, domain_id, subject_name, analysis_result, latest_report
            )
        except Exception:
            _logger.warning("panel discussion failed", exc_info=True)
            try_errors.append(f"panel_discussion: {_POST_DEBATE_PUBLIC_ERRORS['panel_discussion']}")
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
            latest_report=GeneratedReportModel.model_validate(latest_report)
            if latest_report is not None
            else None,
            debate=debate,
            workbench=workbench,
            panel_discussion=panel_discussion,
            workflow=self._workflow_metadata(
                analysis=analysis_result,
                debate=debate,
                debate_suggestion=debate_suggestion,
                monitoring={"status": "not_persisted", "mode": "community_24h"},
            ),
            monitoring={"status": "not_persisted", "mode": "community_24h"},
            generated_at=datetime.now(timezone.utc),
        )

        watch_rule: WatchRule | None = None
        recommendation_version: RecommendationVersion | None = None
        try:
            session_record = await self.session_persistence.ensure_session(
                session,
                payload,
                domain_id,
                subject_id,
                subject_name,
            )
            if session_record is not None:
                result.session_id = session_record.id
                watch_rule = await self.monitoring_service.ensure_watch_rule(
                    session,
                    payload.topic,
                    domain_id,
                    payload.tick_count,
                    session_id=session_record.id,
                    tenant_id=session_record.tenant_id,
                    preset_id=session_record.preset_id,
                    monitoring_started_at=session_record.created_at,
                )
                result.monitoring = watch_rule_monitoring_payload(watch_rule)
                result.workflow = self._workflow_metadata(
                    analysis=analysis_result,
                    debate=debate,
                    debate_suggestion=debate_suggestion,
                    monitoring=result.monitoring,
                )
                previous_count = await session.scalar(
                    select(func.count())
                    .select_from(RecommendationVersion)
                    .where(RecommendationVersion.session_id == session_record.id)
                )
                timeline_watch_rule_id = recommendation_watch_rule_id or (
                    watch_rule.id if watch_rule is not None else None
                )
                recommendation_version = await self.recommendation_service.create_version(
                    session,
                    session_id=session_record.id,
                    watch_rule_id=timeline_watch_rule_id,
                    tenant_id=session_record.tenant_id,
                    preset_id=session_record.preset_id,
                    trigger_type=recommendation_trigger_type
                    or ("initial_result" if int(previous_count or 0) == 0 else "manual_run"),
                    trigger_source_change_id=recommendation_trigger_source_change_id,
                    source_change_ids=recommendation_source_change_ids,
                    significance=recommendation_significance or "none",
                    change_summary=recommendation_change_summary,
                    recommendation_summary=self.session_persistence.assistant_recommendation_summary(
                        result
                    ),
                    result_payload=result.model_dump(mode="json"),
                    source_snapshot=await self.recommendation_service.source_snapshot(
                        session,
                        watch_rule_id=timeline_watch_rule_id,
                    ),
                    ingest_run_id=ingest_run.id,
                    simulation_run_id=simulation_run.id,
                    debate_id=debate.id if debate is not None else None,
                )
                result.workflow["recommendation_version"] = {
                    "id": recommendation_version.id,
                    "version_number": recommendation_version.version_number,
                    "trigger_type": recommendation_version.trigger_type,
                    "significance": recommendation_version.significance,
                }
                await self.session_persistence.store_run_snapshot(
                    session,
                    session_record,
                    result,
                )
        except Exception:
            _logger.warning("session persist failed", exc_info=True)
            try_errors.append(f"session_persist: {_POST_DEBATE_PUBLIC_ERRORS['session_persist']}")
            try:
                await session.rollback()
            except Exception:
                _logger.warning("session rollback failed after persist error", exc_info=True)

        if try_errors:
            yield self._event(
                "step",
                {
                    "phase": "post_debate_errors",
                    "message": "; ".join(try_errors),
                    "status": "warning",
                },
            )

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

        context_lines = [
            f"User topic: {payload.topic}",
            f"Analysis summary: {analysis_result.summary}",
            self._format_evidence_context(evidence_items),
            self._format_claim_context(claims),
        ]
        formatted_context = self._format_request_context(payload.context)
        if formatted_context:
            context_lines.insert(1, f"User decision context:\n{formatted_context}")
        return context_lines

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
        store_recommendation_version: bool = True,
    ) -> AnalysisResponse:
        analysis_payload = self._build_analysis_request(payload)
        analysis = await self.analysis_service.analyze(analysis_payload)
        subject_id, subject_name = self._resolve_subject(payload, analysis)
        session_record = await self.session_persistence.ensure_session(
            session,
            payload,
            analysis.domain_id,
            subject_id,
            subject_name,
        )
        if session_record is not None:
            await self.session_persistence.store_daily_brief(
                session,
                session_record,
                analysis,
                store_recommendation_version=store_recommendation_version,
            )
        return analysis

    async def create_session(
        self,
        session: AsyncSession,
        payload: StrategicAssistantRequest,
    ) -> StrategicSessionRead:
        return await self.session_persistence.create_session(session, payload)

    async def list_sessions(
        self,
        session: AsyncSession,
        tenant_id: str | None = None,
        preset_id: str | None = None,
        limit: int = 12,
    ) -> list[StrategicSessionRead]:
        return await self.session_persistence.list_sessions(
            session,
            tenant_id=tenant_id,
            preset_id=preset_id,
            limit=limit,
        )

    async def get_session_detail(
        self,
        session: AsyncSession,
        session_id: str,
        brief_limit: int = 10,
        run_limit: int = 10,
    ) -> StrategicSessionDetailRead | None:
        return await self.session_persistence.get_session_detail(
            session,
            session_id=session_id,
            brief_limit=brief_limit,
            run_limit=run_limit,
        )

    async def list_recommendation_versions(
        self,
        session: AsyncSession,
        *,
        session_id: str,
        limit: int = 50,
    ) -> list[RecommendationVersionRead] | None:
        return await self.session_persistence.list_recommendation_versions(
            session,
            session_id=session_id,
            limit=limit,
        )

    async def load_session_payload(
        self,
        session: AsyncSession,
        session_id: str,
    ) -> StrategicAssistantRequest | None:
        return await self.session_persistence.load_request(session, session_id)

    def _workflow_metadata(
        self,
        *,
        analysis: AnalysisResponse,
        debate,
        debate_suggestion: DebateSuggestion,
        monitoring: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        source_types = sorted({source.source_type for source in analysis.sources})
        consensus = self._debate_consensus_payload(debate)
        monitoring = monitoring or {"status": "unknown"}
        debate_id = debate.id if debate is not None else None
        return {
            "version": "complete_decision_workflow_v1",
            "mode": "complete_initial_result",
            "status": "first_result_ready",
            "user_can_decide": True,
            "first_result_ready": True,
            "stages": [
                {"id": "research_agents", "status": "completed"},
                {"id": "evidence_ingest", "status": "completed"},
                {"id": "simulation", "status": "completed"},
                {"id": "debate_center", "status": "completed" if debate else "skipped"},
                {"id": "consensus", "status": consensus["status"]},
                {"id": "monitoring", "status": monitoring.get("status", "unknown")},
            ],
            "research_agents": {
                "agent_count": len(source_types),
                "source_types": source_types,
                "sources_collected": len(analysis.sources),
            },
            "debate_suggestion": {
                "warranted": debate_suggestion.warranted,
                "confidence": round(debate_suggestion.confidence, 4),
                "reasons": debate_suggestion.reasons,
            },
            "consensus": consensus,
            "phases": [
                {
                    "key": "evidence_collection",
                    "label": "多源信息采集",
                    "status": "complete",
                    "count": len(analysis.sources),
                },
                {
                    "key": "multi_agent_debate",
                    "label": "多智能体辩论",
                    "status": "complete" if debate_id else "skipped",
                    "debate_id": debate_id,
                },
                {
                    "key": "first_recommendation",
                    "label": "首次建议",
                    "status": "complete",
                },
                {
                    "key": "local_monitoring",
                    "label": "24 小时监控",
                    "status": monitoring.get("status", "unknown"),
                    "watch_rule_id": monitoring.get("watch_rule_id"),
                    "next_poll_at": monitoring.get("next_poll_at"),
                },
            ],
        }

    def _debate_consensus_payload(self, debate) -> dict[str, Any]:
        if debate is None or debate.verdict is None:
            return {
                "status": "skipped",
                "agreement_score": 0.0,
                "roles_considered": 0,
                "minority_opinion": None,
            }
        roles = {round_item.role for round_item in debate.rounds}
        support = sum(
            1
            for round_item in debate.rounds
            if str(round_item.position).upper() in {"SUPPORT", "ACCEPT", "ACCEPTED"}
        )
        challenge = sum(
            1
            for round_item in debate.rounds
            if str(round_item.position).upper() in {"CHALLENGE", "REJECT", "REJECTED"}
        )
        verdict_score = {
            "ACCEPTED": 0.92,
            "CONDITIONAL": 0.78,
            "REJECTED": 0.72,
        }.get(str(debate.verdict.verdict).upper(), 0.65)
        if support or challenge:
            balance = support / max(support + challenge, 1)
            role_score = 0.55 + abs(balance - 0.5) * 0.5
        else:
            role_score = 0.7
        agreement_score = round(min(max((verdict_score + role_score) / 2, 0.0), 0.98), 4)
        status = "broadly_accepted" if agreement_score >= 0.78 else "contested"
        return {
            "status": status,
            "agreement_score": agreement_score,
            "roles_considered": len(roles),
            "rounds_completed": len(debate.rounds),
            "verdict": debate.verdict.verdict,
            "confidence": debate.verdict.confidence,
            "minority_opinion": debate.verdict.minority_opinion,
        }

    def _build_analysis_request(self, payload: StrategicAssistantRequest) -> AnalysisRequest:
        return AnalysisRequest(
            content=payload.topic,
            decision_context=payload.context,
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
        items: list[dict[str, Any]] = [
            {
                "source_type": "analyst_note",
                "source_url": f"https://local.planagent/assistant/{self._slugify(subject_name)}",
                "title": subject_name,
                "content_text": self._topic_with_context(payload),
                "source_metadata": {
                    "origin": "strategic_assistant",
                    "role": "user_prompt",
                    "decision_context": payload.context,
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

    def _topic_with_context(self, payload: StrategicAssistantRequest) -> str:
        formatted_context = self._format_request_context(payload.context)
        if not formatted_context:
            return payload.topic
        return f"{payload.topic}\n\nDecision context:\n{formatted_context}"

    def _format_request_context(self, context: dict[str, str]) -> str:
        lines: list[str] = []
        for key, value in sorted(context.items()):
            clean_key = self._clean_text(key)
            clean_value = self._clean_text(value)
            if clean_key and clean_value:
                lines.append(f"- {clean_key}: {clean_value}")
        return "\n".join(lines)

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
            actor_template=payload.actor_template
            or self._default_actor_template(payload.market or ""),
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
