from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from planagent.domain.api import (
    AnalysisResponse,
    StrategicAssistantRequest,
    StrategicAssistantResponse,
)
from planagent.domain.models import RecommendationVersion
from planagent.services.assistant_conflicts import DebateSuggestion
from planagent.services.assistant_sessions import StrategicSessionPersistence
from planagent.services.community_monitoring import (
    CommunityMonitoringService,
    watch_rule_monitoring_payload,
)
from planagent.services.recommendations import RecommendationVersionService


@dataclass(frozen=True)
class RecommendationTrigger:
    trigger_type: str | None = None
    significance: str = "none"
    watch_rule_id: str | None = None
    trigger_source_change_id: str | None = None
    source_change_ids: tuple[str, ...] = ()
    change_summary: str | None = None


class StrategicWorkflowPersistence:
    def __init__(
        self,
        session_persistence: StrategicSessionPersistence,
        monitoring_service: CommunityMonitoringService,
        recommendation_service: RecommendationVersionService,
    ) -> None:
        self.session_persistence = session_persistence
        self.monitoring_service = monitoring_service
        self.recommendation_service = recommendation_service

    async def persist(
        self,
        session: AsyncSession,
        payload: StrategicAssistantRequest,
        result: StrategicAssistantResponse,
        *,
        subject_id: str | None,
        subject_name: str,
        debate_suggestion: DebateSuggestion,
        trigger: RecommendationTrigger,
    ) -> None:
        session_record = await self.session_persistence.ensure_session(
            session,
            payload,
            result.domain_id,
            subject_id,
            subject_name,
        )
        if session_record is None:
            return

        result.session_id = session_record.id
        watch_rule = await self.monitoring_service.ensure_watch_rule(
            session,
            payload.topic,
            result.domain_id,
            payload.tick_count,
            session_id=session_record.id,
            tenant_id=session_record.tenant_id,
            preset_id=session_record.preset_id,
            monitoring_started_at=session_record.created_at,
        )
        result.monitoring = watch_rule_monitoring_payload(watch_rule)
        result.workflow = self.metadata(
            analysis=result.analysis,
            debate=result.debate,
            debate_suggestion=debate_suggestion,
            monitoring=result.monitoring,
        )

        previous_count = await session.scalar(
            select(func.count())
            .select_from(RecommendationVersion)
            .where(RecommendationVersion.session_id == session_record.id)
        )
        timeline_watch_rule_id = trigger.watch_rule_id or watch_rule.id
        recommendation_version = await self.recommendation_service.create_version(
            session,
            session_id=session_record.id,
            watch_rule_id=timeline_watch_rule_id,
            tenant_id=session_record.tenant_id,
            preset_id=session_record.preset_id,
            trigger_type=trigger.trigger_type
            or ("initial_result" if int(previous_count or 0) == 0 else "manual_run"),
            trigger_source_change_id=trigger.trigger_source_change_id,
            source_change_ids=list(trigger.source_change_ids),
            significance=trigger.significance,
            change_summary=trigger.change_summary,
            recommendation_summary=self.session_persistence.assistant_recommendation_summary(
                result
            ),
            result_payload=result.model_dump(mode="json"),
            source_snapshot=await self.recommendation_service.source_snapshot(
                session,
                watch_rule_id=timeline_watch_rule_id,
            ),
            ingest_run_id=result.ingest_run.id,
            simulation_run_id=result.simulation_run.id,
            debate_id=result.debate.id if result.debate is not None else None,
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

    def metadata(
        self,
        *,
        analysis: AnalysisResponse,
        debate: Any,
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

    def _debate_consensus_payload(self, debate: Any) -> dict[str, Any]:
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
