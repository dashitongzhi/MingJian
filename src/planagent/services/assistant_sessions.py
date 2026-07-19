from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from planagent.domain.api import (
    AnalysisResponse,
    RecommendationVersionRead,
    StrategicAssistantRequest,
    StrategicAssistantResponse,
    StrategicBriefRecordRead,
    StrategicRunSnapshotRead,
    StrategicSessionDetailRead,
    StrategicSessionRead,
)
from planagent.domain.models import (
    Hypothesis,
    PredictionVersion,
    StrategicBriefRecord,
    StrategicRunSnapshot,
    StrategicSession,
)
from planagent.services.recommendations import RecommendationVersionService

_WHITESPACE_RE = re.compile(r"\s+")


class StrategicSessionPersistence:
    def __init__(self, recommendation_service: RecommendationVersionService) -> None:
        self.recommendation_service = recommendation_service

    async def create_session(
        self,
        session: AsyncSession,
        payload: StrategicAssistantRequest,
    ) -> StrategicSessionRead:
        session_record = await self.ensure_session(
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
        recommendation_rows = await self.recommendation_service.list_versions(
            session,
            session_id=session_id,
            limit=run_limit,
        )
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
            recommendation_versions=[
                RecommendationVersionRead.model_validate(item) for item in recommendation_rows
            ],
        )

    async def list_recommendation_versions(
        self,
        session: AsyncSession,
        *,
        session_id: str,
        limit: int = 50,
    ) -> list[RecommendationVersionRead] | None:
        session_record = await session.get(StrategicSession, session_id)
        if session_record is None:
            return None
        rows = await self.recommendation_service.list_versions(
            session,
            session_id=session_id,
            limit=limit,
        )
        return [RecommendationVersionRead.model_validate(row) for row in rows]

    async def load_request(
        self,
        session: AsyncSession,
        session_id: str,
    ) -> StrategicAssistantRequest | None:
        session_record = await session.get(StrategicSession, session_id)
        if session_record is None:
            return None
        return self._build_request_from_session(session_record)

    async def ensure_session(
        self,
        session: AsyncSession,
        payload: StrategicAssistantRequest,
        domain_id: str,
        subject_id: str | None,
        subject_name: str | None,
        *,
        force_create: bool = False,
    ) -> StrategicSession | None:
        should_persist = (
            force_create
            or payload.auto_refresh_enabled
            or payload.session_id is not None
            or payload.session_name is not None
        )
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

    async def store_daily_brief(
        self,
        session: AsyncSession,
        session_record: StrategicSession,
        analysis: AnalysisResponse,
        *,
        store_recommendation_version: bool = True,
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
        if store_recommendation_version:
            await self.recommendation_service.create_version(
                session,
                session_id=session_record.id,
                tenant_id=session_record.tenant_id,
                preset_id=session_record.preset_id,
                trigger_type="daily_brief",
                significance="none",
                recommendation_summary=self.brief_recommendation_summary(analysis),
                result_payload={
                    "kind": "daily_brief",
                    "analysis": analysis.model_dump(mode="json"),
                },
            )
        await session.commit()
        return self._brief_record_read(record)

    async def store_run_snapshot(
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
            result.latest_report.summary
            if result.latest_report is not None
            else result.analysis.summary
        )
        session_record.latest_debate_verdict = (
            result.debate.verdict.verdict
            if result.debate is not None and result.debate.verdict is not None
            else None
        )
        session_record.latest_run_at = result.generated_at
        session.add(snapshot)
        await session.commit()
        return self._run_snapshot_read(snapshot)

    def assistant_recommendation_summary(self, result: StrategicAssistantResponse) -> str:
        if result.debate is not None and result.debate.verdict is not None:
            verdict = result.debate.verdict
            titles = []
            for item in verdict.recommendations[:3]:
                title = self._clean_text(item.title or item.rationale or "")
                if title:
                    titles.append(title)
            if titles:
                return "；".join(titles)
            if verdict.conclusion_summary:
                return self._clean_text(verdict.conclusion_summary)[:500]
        if result.latest_report is not None and result.latest_report.summary:
            return self._clean_text(result.latest_report.summary)[:500]
        return self._clean_text(result.analysis.summary)[:500]

    def brief_recommendation_summary(self, analysis: AnalysisResponse) -> str:
        recommendations = [self._clean_text(item) for item in analysis.recommendations if item]
        if recommendations:
            return "；".join(recommendations[:3])
        return self._clean_text(analysis.summary) or "本次固定刷新未发现足以改变建议的明确信号。"

    async def _recent_hypotheses(
        self,
        session: AsyncSession,
        session_record: StrategicSession,
        statuses: set[str],
    ) -> list[Hypothesis]:
        session_run_ids = select(StrategicRunSnapshot.simulation_run_id).where(
            StrategicRunSnapshot.session_id == session_record.id,
            StrategicRunSnapshot.simulation_run_id.is_not(None),
        )
        query = select(Hypothesis).where(
            Hypothesis.verification_status.in_(statuses),
            Hypothesis.run_id.in_(session_run_ids),
        )
        if session_record.tenant_id is not None:
            query = query.where(Hypothesis.tenant_id == session_record.tenant_id)
        if session_record.preset_id is not None:
            query = query.where(Hypothesis.preset_id == session_record.preset_id)
        return list(
            (await session.scalars(query.order_by(Hypothesis.updated_at.desc()).limit(10))).all()
        )

    def _build_request_from_session(
        self,
        session_record: StrategicSession,
    ) -> StrategicAssistantRequest:
        preferences = session_record.source_preferences or {}
        return StrategicAssistantRequest(
            session_id=session_record.id,
            session_name=session_record.name,
            topic=session_record.topic,
            context=preferences.get("decision_context", {}),
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
            "decision_context": payload.context,
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

    def _clean_text(self, value: str) -> str:
        return _WHITESPACE_RE.sub(" ", value or "").strip()
