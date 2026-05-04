from __future__ import annotations

from datetime import timedelta
import logging

from sqlalchemy import or_, select, update

from planagent.config import Settings
from planagent.db import get_database
from planagent.domain.api import (
    AnalysisRequest,
    DebateTriggerRequest,
    IngestRunCreate,
    SimulationRunCreate,
)
from planagent.domain.enums import EventTopic
from planagent.domain.models import StrategicRunSnapshot, StrategicSession, WatchRule, utc_now
from planagent.events.bus import EventBus
from planagent.services.analysis import AutomatedAnalysisService
from planagent.services.change_detection import ChangeDetectionService
from planagent.services.debate import DebateService
from planagent.services.openai_client import OpenAIService
from planagent.services.pipeline import PhaseOnePipelineService
from planagent.services.simulation import SimulationService
from planagent.services.source_state import SourceStateService
from planagent.simulation.rules import RuleRegistry
from planagent.workers.base import Worker, WorkerDescription


logger = logging.getLogger(__name__)


class WatchIngestWorker(Worker):
    description = WorkerDescription(
        worker_id="watch-ingest-worker",
        summary="Polls WatchRules and fetches sources on schedule.",
        consumes=(),
        produces=(EventTopic.RAW_INGESTED.value,),
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
        self.openai_service = openai_service
        self.worker_instance_id = self.description.worker_id
        self.analysis_service = AutomatedAnalysisService(settings, openai_service)
        self.pipeline_service = PhaseOnePipelineService(settings, event_bus, openai_service)
        self.simulation_service = SimulationService(settings, event_bus, rule_registry, openai_service)
        self.debate_service = DebateService(settings, event_bus, openai_service)

    async def run_once(self) -> dict[str, object]:
        database = get_database(self.settings.database_url)
        async with database.session() as session:
            claimed_rules = await self._claim_due_rules(
                session,
                limit=10,
                worker_id=self.worker_instance_id,
            )
            polled = 0
            failed = 0
            ingest_runs = 0
            simulation_runs = 0
            debate_runs = 0

            for rule in claimed_rules:
                try:
                    result = await self._poll_rule(session, rule)
                    polled += 1
                    if result.get("ingest_run_id"):
                        ingest_runs += 1
                    if result.get("simulation_run_id"):
                        simulation_runs += 1
                    if result.get("debate_id"):
                        debate_runs += 1
                except Exception as exc:
                    await self._mark_failure(
                        session,
                        rule.id,
                        f"{type(exc).__name__}: {' '.join(str(exc).split())[:300]}",
                    )
                    failed += 1

        return {
            "claimed_rules": len(claimed_rules),
            "polled": polled,
            "failed": failed,
            "ingest_runs": ingest_runs,
            "simulation_runs": simulation_runs,
            "debate_runs": debate_runs,
        }

    async def _poll_rule(self, session, rule: WatchRule) -> dict:
        source_state_service = SourceStateService(self.settings)
        change_service = ChangeDetectionService(self.settings)
        state = await source_state_service.get_or_create_state(
            session,
            source_type=rule.source_types[0] if rule.source_types else "unknown",
            source_url_or_query=rule.query,
            watch_rule_id=rule.id,
            tenant_id=rule.tenant_id,
            preset_id=rule.preset_id,
        )
        if rule.incremental_enabled:
            should_fetch = await source_state_service.should_fetch(
                session,
                state,
                force_full_refresh_every_minutes=rule.force_full_refresh_every_minutes,
            )
            if not should_fetch:
                await self._mark_poll_success(session, rule)
                return {"skipped": True, "reason": "no_change"}

        analysis_request = AnalysisRequest(
            content=rule.query,
            domain_id=rule.domain_id,
            auto_fetch_news=True,
            include_google_news="google_news" in rule.source_types,
            include_reddit="reddit" in rule.source_types,
            include_hacker_news="hacker_news" in rule.source_types,
            include_github="github" in rule.source_types,
            include_rss_feeds="rss" in rule.source_types,
            include_gdelt="gdelt" in rule.source_types,
            include_weather="weather" in rule.source_types,
            include_aviation="aviation" in rule.source_types,
            include_x="x" in rule.source_types,
            source_types=rule.source_types,
        )
        analysis = await self.analysis_service.analyze(analysis_request)
        for step in analysis.reasoning_steps:
            if step.stage == "source_complete":
                await self.analysis_service.record_source_success(session, self._source_type_from_step(step.message))
            elif step.stage == "source_error":
                await self.analysis_service.record_source_failure(
                    session,
                    self._source_type_from_step(step.message),
                    step.detail or step.message,
                )

        items = [
            {
                "source_type": "analyst_note",
                "source_url": f"https://local.planagent/watch/{rule.id}",
                "title": rule.name,
                "content_text": rule.query,
                "source_metadata": {"origin": "watch_rule", "rule_id": rule.id},
            }
        ]
        qualified_sources = self._qualified_sources(rule, analysis.sources)
        for source in qualified_sources:
            items.append(
                {
                    "source_type": source.source_type,
                    "source_url": source.url,
                    "title": source.title,
                    "content_text": source.summary,
                    "source_metadata": {
                        "origin": "watch_rule_source",
                        "importance_score": self._source_score(rule, source),
                        **source.metadata,
                    },
                }
            )

        content_text = self._change_detection_text(rule, analysis.sources)
        content_hash = change_service.compute_content_hash(
            content_text,
            sources=analysis.sources,
        )
        change_record = await change_service.detect_change(
            session,
            state,
            new_hash=content_hash,
            new_content_text=content_text,
            new_title=rule.name,
            new_raw_source_item_id=None,
        )
        await source_state_service.update_after_fetch(
            session,
            state.id,
            success=True,
            content_hash=content_hash,
            raw_source_item_id=None,
        )
        if rule.incremental_enabled:
            threshold = rule.change_significance_threshold
            significance_order = {"none": 0, "low": 1, "medium": 2, "high": 3}
            if significance_order.get(change_record.significance, 0) < significance_order.get(
                threshold, 2
            ):
                await self._mark_poll_success(session, rule)
                return {
                    "skipped": True,
                    "reason": "below_threshold",
                    "significance": change_record.significance,
                }

        if change_record.change_type != "unchanged":
            await self.event_bus.publish(
                EventTopic.SOURCE_CHANGED.value,
                {
                    "change_id": change_record.id,
                    "source_type": state.source_type,
                    "significance": change_record.significance,
                },
            )

        ingest_run = await self.pipeline_service.create_ingest_run(
            session,
            IngestRunCreate(
                requested_by=f"watch-rule:{rule.id}",
                tenant_id=rule.tenant_id,
                preset_id=rule.preset_id,
                items=items,
            ),
        )

        simulation_run_id = None
        debate_id = await self._maybe_trigger_re_debate(
            rule,
            session,
            change_record.diff_summary,
            change_record.significance,
        )

        threshold_met = self._threshold_met(rule, qualified_sources)
        if rule.auto_trigger_simulation and threshold_met:
            if rule.domain_id == "military":
                force_name = rule.query[:60]
                force_id = rule.query[:40].lower().replace(" ", "-")
                sim_payload = SimulationRunCreate(
                    domain_id="military",
                    force_id=force_id,
                    force_name=force_name,
                    theater="contested-theater",
                    tick_count=rule.tick_count or None,
                    tenant_id=rule.tenant_id,
                    preset_id=rule.preset_id,
                )
            else:
                company_name = rule.query[:60]
                company_id = rule.query[:40].lower().replace(" ", "-")
                sim_payload = SimulationRunCreate(
                    domain_id="corporate",
                    company_id=company_id,
                    company_name=company_name,
                    market="ai",
                    tick_count=rule.tick_count or None,
                    tenant_id=rule.tenant_id,
                    preset_id=rule.preset_id,
                )
            sim_run = await self.simulation_service.create_simulation_run(session, sim_payload)
            simulation_run_id = sim_run.id

            if rule.auto_trigger_debate and simulation_run_id is not None:
                debate = await self.debate_service.trigger_debate(
                    session,
                    DebateTriggerRequest(
                        run_id=simulation_run_id,
                        topic=f"Should the posture for {rule.query} be adjusted?",
                        trigger_type="pivot_decision",
                        target_type="run",
                    ),
                )
                debate_id = debate.id

        await self._mark_poll_success(session, rule)

        return {
            "ingest_run_id": ingest_run.id,
            "sources_fetched": len(analysis.sources),
            "sources_qualified": len(qualified_sources),
            "threshold_met": threshold_met,
            "simulation_run_id": simulation_run_id,
            "debate_id": debate_id,
        }

    async def _maybe_trigger_re_debate(
        self,
        rule: WatchRule,
        session,
        change_summary: str | None,
        significance: str,
    ) -> str | None:
        if significance != "high" or not rule.auto_trigger_debate:
            return None

        try:
            strategic_session = (
                await session.scalars(
                    select(StrategicSession)
                    .where(
                        StrategicSession.topic == rule.query,
                        StrategicSession.domain_id == rule.domain_id,
                        StrategicSession.tenant_id == rule.tenant_id,
                        StrategicSession.preset_id == rule.preset_id,
                    )
                    .order_by(StrategicSession.updated_at.desc(), StrategicSession.created_at.desc())
                    .limit(1)
                )
            ).first()
            if strategic_session is None:
                return None

            latest_snapshot = (
                await session.scalars(
                    select(StrategicRunSnapshot)
                    .where(
                        StrategicRunSnapshot.session_id == strategic_session.id,
                        StrategicRunSnapshot.simulation_run_id.is_not(None),
                    )
                    .order_by(StrategicRunSnapshot.generated_at.desc())
                    .limit(1)
                )
            ).first()
            if latest_snapshot is None or latest_snapshot.simulation_run_id is None:
                return None

            summary = change_summary or "High-significance source change detected."
            debate = await self.debate_service.trigger_debate(
                session,
                DebateTriggerRequest(
                    run_id=latest_snapshot.simulation_run_id,
                    topic=f"Should the strategy for {strategic_session.topic} be revised?",
                    trigger_type="pivot_decision",
                    target_type="run",
                    context_lines=[
                        "Auto-triggered by watch-ingest-worker after a high-significance source change.",
                        f"Strategic session id: {strategic_session.id}",
                        f"Domain id: {strategic_session.domain_id or rule.domain_id}",
                        f"Change summary: {summary}",
                    ],
                ),
            )
            return debate.id
        except Exception as exc:
            await session.rollback()
            logger.warning(
                "Failed to auto-trigger re-debate for watch rule %s: %s",
                rule.id,
                f"{type(exc).__name__}: {' '.join(str(exc).split())[:300]}",
            )
            return None

    def _source_type_from_step(self, message: str) -> str:
        lowered = message.lower()
        if "google" in lowered:
            return "google_news"
        if "reddit" in lowered:
            return "reddit"
        if "hacker" in lowered:
            return "hacker_news"
        if "github" in lowered:
            return "github"
        if "gdelt" in lowered:
            return "gdelt"
        if "weather" in lowered:
            return "weather"
        if "aviation" in lowered or "opensky" in lowered:
            return "aviation"
        if "rss" in lowered:
            return "rss"
        if "linux.do" in lowered or "linux" in lowered:
            return "linux_do"
        if "xiaohongshu" in lowered:
            return "xiaohongshu"
        if "douyin" in lowered:
            return "douyin"
        if lowered.strip() == "x" or " x." in lowered or " x " in lowered:
            return "x"
        return "unknown"

    def _qualified_sources(self, rule: WatchRule, sources) -> list:
        return [
            source
            for source in sources
            if self._source_score(rule, source) >= float(rule.importance_threshold or 0.0)
        ]

    def _threshold_met(self, rule: WatchRule, sources: list) -> bool:
        if len(sources) < int(rule.min_new_evidence_count or 0):
            return False
        if not sources:
            return float(rule.trigger_threshold or 0.0) <= 0.0
        return max(self._source_score(rule, source) for source in sources) >= float(rule.trigger_threshold or 0.0)

    def _source_score(self, rule: WatchRule, source) -> float:
        haystack = f"{source.title} {source.summary}".lower()
        if any(term.lower() in haystack for term in (rule.exclude_keywords or []) if term):
            return 0.0
        keywords = [term.lower() for term in (rule.keywords or []) if term]
        entity_tags = [term.lower() for term in (rule.entity_tags or []) if term]
        terms = keywords or entity_tags or [token.lower() for token in rule.query.split()[:6] if token]
        matched = sum(1 for term in terms if term and term in haystack)
        score = 0.35 + min(matched * 0.18, 0.45)
        engagement = source.metadata.get("engagement", {}) if isinstance(source.metadata, dict) else {}
        if isinstance(engagement, dict) and any(value for value in engagement.values() if isinstance(value, (int, float))):
            score += 0.1
        if source.published_at:
            score += 0.1
        return round(max(0.0, min(score, 1.0)), 4)

    def _change_detection_text(self, rule: WatchRule, sources) -> str:
        parts = [f"watch:{rule.id}", f"name:{rule.name}", f"query:{rule.query}"]
        for source in sources:
            parts.append(
                "\n".join(
                    [
                        f"source_type:{source.source_type}",
                        f"url:{source.url}",
                        f"title:{source.title}",
                        f"summary:{source.summary}",
                    ]
                )
            )
        return "\n\n".join(parts)

    async def _mark_poll_success(self, session, rule: WatchRule) -> None:
        now = utc_now()
        rule.last_poll_at = now
        rule.last_poll_error = None
        rule.lease_owner = None
        rule.lease_expires_at = None
        rule.next_poll_at = now + timedelta(minutes=rule.poll_interval_minutes)
        await session.commit()

    async def _claim_due_rules(
        self,
        session,
        limit: int,
        worker_id: str,
    ) -> list[WatchRule]:
        now = utc_now()
        lease_expires_at = now + timedelta(seconds=self.settings.worker_lease_seconds)
        candidate_ids = list(
            (
                await session.scalars(
                    select(WatchRule.id)
                    .where(
                        WatchRule.enabled.is_(True),
                        WatchRule.next_poll_at.is_not(None),
                        WatchRule.next_poll_at <= now,
                        or_(
                            WatchRule.lease_expires_at.is_(None),
                            WatchRule.lease_expires_at < now,
                        ),
                    )
                    .order_by(WatchRule.next_poll_at.asc())
                    .limit(limit * 3)
                )
            ).all()
        )
        claimed: list[WatchRule] = []
        for rule_id in candidate_ids:
            result = await session.execute(
                update(WatchRule)
                .where(
                    WatchRule.id == rule_id,
                    WatchRule.enabled.is_(True),
                    WatchRule.next_poll_at.is_not(None),
                    WatchRule.next_poll_at <= now,
                    or_(
                        WatchRule.lease_expires_at.is_(None),
                        WatchRule.lease_expires_at < now,
                    ),
                )
                .values(
                    lease_owner=worker_id,
                    lease_expires_at=lease_expires_at,
                    poll_attempts=WatchRule.poll_attempts + 1,
                    last_poll_error=None,
                    updated_at=now,
                )
            )
            if result.rowcount:
                rule = await session.get(WatchRule, rule_id)
                if rule is not None:
                    claimed.append(rule)
            if len(claimed) >= limit:
                break
        return claimed

    async def _mark_failure(self, session, rule_id: str, error: str) -> None:
        now = utc_now()
        retry_at = now + timedelta(hours=1)
        await session.execute(
            update(WatchRule)
            .where(WatchRule.id == rule_id)
            .values(
                lease_owner=None,
                lease_expires_at=None,
                last_poll_error=error,
                next_poll_at=retry_at,
                updated_at=now,
            )
        )
        await session.commit()
