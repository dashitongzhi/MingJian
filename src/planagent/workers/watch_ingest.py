from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

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
from planagent.domain.models import (
    RawSourceItem,
    RecommendationVersion,
    SourceCursorState,
    StrategicRunSnapshot,
    StrategicSession,
    WatchRule,
    utc_now,
)
from planagent.events.bus import EventBus
from planagent.services.analysis import AutomatedAnalysisService
from planagent.services.assistant import StrategicAssistantService
from planagent.services.change_detection import ChangeDetectionService
from planagent.services.debate import DebateService
from planagent.services.notification import NotificationService, NotificationPriority
from planagent.services.openai_client import OpenAIService
from planagent.services.pipeline import PhaseOnePipelineService
from planagent.services.recommendations import RecommendationVersionService
from planagent.services.simulation import SimulationService
from planagent.services.source_state import SourceStateService
from planagent.services.workbench import WorkbenchService
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
        notification_service: NotificationService | None = None,
    ) -> None:
        self.settings = settings
        self.event_bus = event_bus
        self.openai_service = openai_service
        self.notification_service = notification_service
        self.worker_instance_id = self.description.worker_id
        self.analysis_service = AutomatedAnalysisService(settings, openai_service)
        self.pipeline_service = PhaseOnePipelineService(settings, event_bus, openai_service)
        self.simulation_service = SimulationService(
            settings, event_bus, rule_registry, openai_service
        )
        self.debate_service = DebateService(settings, event_bus, openai_service)
        self.assistant_service = StrategicAssistantService(
            analysis_service=self.analysis_service,
            pipeline_service=self.pipeline_service,
            simulation_service=self.simulation_service,
            debate_service=self.debate_service,
            workbench_service=WorkbenchService(),
        )
        self.recommendation_service = RecommendationVersionService()

    async def run_once(self) -> dict[str, object]:
        active_getter = getattr(self.event_bus, "is_backpressure_active", None)
        if active_getter is not None and await active_getter():
            return {
                "claimed_rules": 0,
                "polled": 0,
                "failed": 0,
                "ingest_runs": 0,
                "simulation_runs": 0,
                "debate_runs": 0,
                "recommendation_updates": 0,
                "backpressure_active": True,
                "reason": "event_bus_backpressure_signal",
                "threshold": self.settings.backpressure_pending_threshold,
            }

        database = get_database()
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
            recommendation_updates = 0

            for rule in claimed_rules:
                rule_id = rule.id
                try:
                    result = await self._poll_rule(session, rule)
                    polled += 1
                    if result.get("ingest_run_id"):
                        ingest_runs += 1
                    if result.get("simulation_run_id"):
                        simulation_runs += 1
                    if result.get("debate_id"):
                        debate_runs += 1
                    if result.get("recommendation_version_id"):
                        recommendation_updates += 1
                except Exception as exc:
                    await session.rollback()
                    await self._mark_failure(
                        session,
                        rule_id,
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
            "recommendation_updates": recommendation_updates,
        }

    async def _poll_rule(self, session, rule: WatchRule) -> dict:
        if self._community_window_expired(rule):
            rule.enabled = False
            rule.lease_owner = None
            rule.lease_expires_at = None
            rule.last_poll_error = None
            rule.next_poll_at = None
            rule.updated_at = utc_now()
            await session.commit()
            return {
                "skipped": True,
                "reason": "community_24h_window_expired",
                "watch_rule_id": rule.id,
            }

        source_state_service = SourceStateService(self.settings)
        change_service = ChangeDetectionService(self.settings)
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
                await self.analysis_service.record_source_success(
                    session, self._source_type_from_step(step.message)
                )
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

        change_records = await self._detect_source_changes(
            session,
            rule,
            source_state_service,
            change_service,
            analysis.sources,
        )
        significance = self._max_significance(change_records)
        change_summary = self._change_summary(change_records)
        evidence_impact = self._evidence_impact_assessment(
            rule=rule,
            change_records=change_records,
            qualified_sources=qualified_sources,
            change_summary=change_summary,
        )
        if rule.incremental_enabled:
            threshold = rule.change_significance_threshold
            significance_order = {"none": 0, "low": 1, "medium": 2, "high": 3}
            if (
                significance_order.get(significance, 0) < significance_order.get(threshold, 2)
                and not evidence_impact["should_refresh"]
            ):
                recommendation_version_id = await self._store_recommendation_version(
                    session=session,
                    rule=rule,
                    analysis=analysis,
                    change_records=change_records,
                    change_summary=change_summary,
                    significance=significance,
                    evidence_impact=evidence_impact,
                    threshold_met=False,
                    ingest_run_id=None,
                    simulation_run_id=None,
                    debate_id=None,
                    trigger_type="scheduled_refresh",
                )
                await self._mark_poll_success(session, rule)
                return {
                    "skipped": True,
                    "reason": "below_threshold",
                    "significance": significance,
                    "evidence_impact": evidence_impact,
                    "recommendation_version_id": recommendation_version_id,
                }

        for change_record in change_records:
            if change_record.change_type == "unchanged":
                continue
            state = await session.get(SourceCursorState, change_record.source_state_id)
            await self.event_bus.publish(
                EventTopic.SOURCE_CHANGED.value,
                {
                    "change_id": change_record.id,
                    "source_type": state.source_type if state is not None else "unknown",
                    "significance": change_record.significance,
                    "impact_score": evidence_impact["score"],
                    "impact_level": evidence_impact["level"],
                },
            )
            # Push notification for significant changes
            if self.notification_service and change_record.significance in ("medium", "high"):
                try:
                    await self.notification_service.broadcast(
                        title=f"📡 源变化检测 [{change_record.significance.upper()}]",
                        body=(
                            f"监控规则「{rule.name}」检测到{change_record.significance}级变化："
                            f"{change_record.diff_summary or (state.source_type if state is not None else 'source')}"
                        ),
                        priority=NotificationPriority.HIGH
                        if change_record.significance == "high"
                        else NotificationPriority.NORMAL,
                        metadata={
                            "rule_id": rule.id,
                            "change_id": change_record.id,
                            "significance": change_record.significance,
                            "impact_score": evidence_impact["score"],
                            "impact_level": evidence_impact["level"],
                        },
                    )
                except Exception:
                    logger.debug("Notification broadcast failed (non-critical)")

        ingest_run = await self.pipeline_service.create_ingest_run(
            session,
            IngestRunCreate(
                requested_by=f"watch-rule:{rule.id}",
                tenant_id=rule.tenant_id,
                preset_id=rule.preset_id,
                items=items,
            ),
        )
        await self._link_change_records_to_raw_items(session, ingest_run.id, change_records)

        simulation_run_id = None
        debate_id = None
        full_refresh = await self._maybe_refresh_strategic_session(
            rule,
            session,
            change_summary,
            significance,
            evidence_impact,
        )
        if full_refresh:
            simulation_run_id = full_refresh.get("simulation_run_id") or None
            debate_id = full_refresh.get("debate_id") or None

        threshold_met = (
            self._threshold_met(rule, qualified_sources)
            or significance == "high"
            or evidence_impact["should_refresh"]
        )
        if rule.auto_trigger_simulation and threshold_met and not full_refresh:
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
                        context_lines=self._evidence_impact_context_lines(evidence_impact),
                        domain_id=rule.domain_id,
                    ),
                )
                debate_id = debate.id

        recommendation_version_id = full_refresh.get("recommendation_version_id") or None
        if recommendation_version_id is None:
            recommendation_version_id = await self._store_recommendation_version(
                session=session,
                rule=rule,
                analysis=analysis,
                change_records=change_records,
                change_summary=change_summary,
                significance=significance,
                evidence_impact=evidence_impact,
                threshold_met=threshold_met,
                ingest_run_id=ingest_run.id,
                simulation_run_id=simulation_run_id,
                debate_id=debate_id,
            )

        await self._mark_poll_success(session, rule)

        # Push notification for re-analysis results
        if self.notification_service and (debate_id or simulation_run_id):
            try:
                parts = []
                if simulation_run_id:
                    parts.append("已触发新模拟推演")
                if debate_id:
                    parts.append("已触发重新辩论")
                await self.notification_service.broadcast(
                    title=f"🔄 监控更新：{rule.name}",
                    body=f"监控规则「{rule.name}」完成更新——{', '.join(parts)}。请查看最新建议。",
                    priority=NotificationPriority.HIGH,
                    metadata={
                        "rule_id": rule.id,
                        "debate_id": debate_id,
                        "simulation_run_id": simulation_run_id,
                        "impact_score": evidence_impact["score"],
                        "impact_level": evidence_impact["level"],
                    },
                )
            except Exception:
                logger.debug("Notification broadcast failed (non-critical)")

        return {
            "ingest_run_id": ingest_run.id,
            "sources_fetched": len(analysis.sources),
            "sources_qualified": len(qualified_sources),
            "threshold_met": threshold_met,
            "simulation_run_id": simulation_run_id,
            "debate_id": debate_id,
            "recommendation_version_id": recommendation_version_id,
            "strategic_session_id": full_refresh.get("session_id"),
            "run_snapshot_id": full_refresh.get("run_snapshot_id"),
            "change_records": len(change_records),
            "significance": significance,
            "evidence_impact": evidence_impact,
        }

    async def _maybe_refresh_strategic_session(
        self,
        rule: WatchRule,
        session,
        change_summary: str | None,
        significance: str,
        evidence_impact: dict[str, Any],
    ) -> dict[str, str]:
        if not rule.auto_trigger_debate or not evidence_impact["should_refresh"]:
            return {}

        try:
            strategic_session = await self._find_strategic_session(session, rule)
            if strategic_session is None:
                return {}

            payload = await self.assistant_service.load_session_payload(
                session,
                strategic_session.id,
            )
            if payload is None:
                return {}

            result = await self.assistant_service.run(
                session,
                payload,
                recommendation_trigger_type="source_change",
                recommendation_significance=significance,
            )
            latest_snapshot = (
                await session.scalars(
                    select(StrategicRunSnapshot)
                    .where(StrategicRunSnapshot.session_id == strategic_session.id)
                    .order_by(StrategicRunSnapshot.generated_at.desc())
                    .limit(1)
                )
            ).first()
            latest_recommendation = (
                await session.scalars(
                    select(RecommendationVersion)
                    .where(RecommendationVersion.session_id == strategic_session.id)
                    .order_by(RecommendationVersion.generated_at.desc())
                    .limit(1)
                )
            ).first()
            return {
                "session_id": strategic_session.id,
                "simulation_run_id": result.simulation_run.id,
                "debate_id": result.debate.id if result.debate is not None else "",
                "run_snapshot_id": latest_snapshot.id if latest_snapshot is not None else "",
                "recommendation_version_id": latest_recommendation.id
                if latest_recommendation is not None
                else "",
            }
        except Exception as exc:
            await session.rollback()
            logger.warning(
                "Failed to refresh strategic session for watch rule %s: %s",
                rule.id,
                f"{type(exc).__name__}: {' '.join(str(exc).split())[:300]}",
            )
            return {}

    async def _find_strategic_session(self, session, rule: WatchRule) -> StrategicSession | None:
        if rule.session_id is not None:
            record = await session.get(StrategicSession, rule.session_id)
            if record is not None:
                return record
        return (
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

    async def _store_recommendation_version(
        self,
        *,
        session,
        rule: WatchRule,
        analysis,
        change_records: list,
        change_summary: str | None,
        significance: str,
        evidence_impact: dict[str, Any],
        threshold_met: bool,
        ingest_run_id: str | None,
        simulation_run_id: str | None,
        debate_id: str | None,
        trigger_type: str | None = None,
    ) -> str | None:
        strategic_session = await self._find_strategic_session(session, rule)
        session_id = rule.session_id or (strategic_session.id if strategic_session else None)
        if session_id is None:
            return None

        changed_records = [record for record in change_records if record.change_type != "unchanged"]
        source_change_ids = [record.id for record in changed_records]
        trigger_source_change_id = source_change_ids[0] if source_change_ids else None
        resolved_trigger_type = trigger_type or (
            "source_change"
            if significance in {"medium", "high"} or changed_records
            else "scheduled_refresh"
        )
        recommendation = await self.recommendation_service.create_version(
            session,
            session_id=session_id,
            watch_rule_id=rule.id,
            tenant_id=rule.tenant_id,
            preset_id=rule.preset_id,
            trigger_type=resolved_trigger_type,
            trigger_source_change_id=trigger_source_change_id,
            source_change_ids=source_change_ids,
            significance=significance,
            change_summary=change_summary,
            recommendation_summary=self._recommendation_summary(
                analysis=analysis,
                significance=significance,
                change_summary=change_summary,
                threshold_met=threshold_met,
                simulation_run_id=simulation_run_id,
                debate_id=debate_id,
            ),
            result_payload={
                "kind": "watch_update",
                "analysis": analysis.model_dump(mode="json"),
                "threshold_met": threshold_met,
                "evidence_impact": evidence_impact,
                "change_records": len(change_records),
                "changed_records": len(changed_records),
            },
            source_snapshot=await self.recommendation_service.source_snapshot(
                session,
                watch_rule_id=rule.id,
            ),
            ingest_run_id=ingest_run_id,
            simulation_run_id=simulation_run_id,
            debate_id=debate_id,
        )
        return recommendation.id

    def _recommendation_summary(
        self,
        *,
        analysis,
        significance: str,
        change_summary: str | None,
        threshold_met: bool,
        simulation_run_id: str | None,
        debate_id: str | None,
    ) -> str:
        recommendations = [" ".join(item.split()) for item in analysis.recommendations if item]
        if recommendations:
            base = "；".join(recommendations[:3])
        elif change_summary:
            base = change_summary
        else:
            base = " ".join(str(analysis.summary or "").split())
        if significance == "high":
            prefix = "检测到高重要度突发变化"
        elif significance == "medium":
            prefix = "检测到中等重要度变化"
        elif threshold_met:
            prefix = "监控条件已满足"
        else:
            prefix = "固定监控刷新完成"
        actions = []
        if simulation_run_id is not None:
            actions.append("已生成新推演")
        if debate_id is not None:
            actions.append("已完成重新辩论")
        suffix = f"（{', '.join(actions)}）" if actions else ""
        return f"{prefix}: {base[:500]}{suffix}"

    async def _detect_source_changes(
        self,
        session,
        rule: WatchRule,
        source_state_service: SourceStateService,
        change_service: ChangeDetectionService,
        sources: list[Any],
    ) -> list:
        records = []
        for source_type, source_items in self._group_sources_for_change_detection(sources).items():
            state = await source_state_service.get_or_create_state(
                session,
                source_type=source_type,
                source_url_or_query=rule.query,
                watch_rule_id=rule.id,
                tenant_id=rule.tenant_id,
                preset_id=rule.preset_id,
            )
            if not await source_state_service.should_fetch(
                session,
                state,
                force_full_refresh_every_minutes=rule.force_full_refresh_every_minutes,
            ):
                continue
            content_text = self._change_detection_text(rule, source_items)
            content_hash = change_service.compute_content_hash(
                content_text,
                sources=source_items,
            )
            if state.last_seen_hash == content_hash:
                await source_state_service.update_after_fetch(
                    session,
                    state.id,
                    success=True,
                    content_hash=content_hash,
                    raw_source_item_id=None,
                )
                continue
            record = await change_service.detect_change(
                session,
                state,
                new_hash=content_hash,
                new_content_text=content_text,
                new_title=f"{rule.name} [{source_type}]",
                new_raw_source_item_id=None,
            )
            await source_state_service.update_after_fetch(
                session,
                state.id,
                success=True,
                content_hash=content_hash,
                raw_source_item_id=None,
                preserve_changed=record.change_type != "unchanged",
            )
            records.append(record)
        return records

    async def _link_change_records_to_raw_items(
        self,
        session,
        ingest_run_id: str,
        change_records: list,
    ) -> None:
        if not change_records:
            return
        raw_items = list(
            (
                await session.scalars(
                    select(RawSourceItem)
                    .where(RawSourceItem.ingest_run_id == ingest_run_id)
                    .order_by(RawSourceItem.created_at.desc())
                )
            ).all()
        )
        if not raw_items:
            return
        by_source_type: dict[str, str] = {}
        for raw in raw_items:
            by_source_type.setdefault(raw.source_type, raw.id)
        for record in change_records:
            if record.new_raw_source_item_id is not None:
                continue
            state = await session.get(SourceCursorState, record.source_state_id)
            if state is None:
                continue
            raw_id = by_source_type.get(state.source_type)
            if raw_id is not None:
                record.new_raw_source_item_id = raw_id

    def _group_sources_for_change_detection(
        self,
        sources: list[Any],
    ) -> dict[str, list[Any]]:
        grouped: dict[str, list[Any]] = {}
        for source in sources:
            source_type = str(getattr(source, "source_type", "") or "unknown")
            grouped.setdefault(source_type, []).append(source)
        if not grouped:
            grouped["watch_rule"] = []
        return dict(sorted(grouped.items()))

    def _max_significance(self, change_records: list) -> str:
        order = {"none": 0, "low": 1, "medium": 2, "high": 3}
        significance = "none"
        for record in change_records:
            if order.get(record.significance, 0) > order.get(significance, 0):
                significance = record.significance
        return significance

    def _change_summary(self, change_records: list) -> str | None:
        order = {"none": 0, "low": 1, "medium": 2, "high": 3}
        changed = [record for record in change_records if record.change_type != "unchanged"]
        if not changed:
            return None
        chosen = max(changed, key=lambda record: order.get(record.significance, 0))
        return chosen.diff_summary

    def _evidence_impact_assessment(
        self,
        *,
        rule: WatchRule,
        change_records: list,
        qualified_sources: list,
        change_summary: str | None,
    ) -> dict[str, Any]:
        changed_records = [record for record in change_records if record.change_type != "unchanged"]
        significance_order = {"none": 0.0, "low": 0.25, "medium": 0.5, "high": 0.72}
        max_significance = max(
            (significance_order.get(record.significance, 0.0) for record in changed_records),
            default=0.0,
        )
        source_scores = [self._source_score(rule, source) for source in qualified_sources]
        max_source_score = max(source_scores, default=0.0)
        score = max_significance
        score += min(len(changed_records) * 0.06, 0.18)
        score += min(len(qualified_sources) * 0.04, 0.16)
        score += max_source_score * 0.18

        text_parts = [change_summary or ""]
        text_parts.extend(str(record.diff_summary or "") for record in changed_records)
        text_parts.extend(
            f"{getattr(source, 'title', '')} {getattr(source, 'summary', '')}"
            for source in qualified_sources[:8]
        )
        haystack = " ".join(text_parts).lower()
        shock_terms = {
            "breakthrough",
            "collapse",
            "cancel",
            "blocked",
            "delay",
            "lawsuit",
            "sanction",
            "attack",
            "escalation",
            "bankruptcy",
            "outage",
            "breach",
            "短缺",
            "中断",
            "推迟",
            "取消",
            "制裁",
            "攻击",
            "升级",
            "破产",
            "泄露",
            "突发",
            "重大",
        }
        matched_terms = sorted(term for term in shock_terms if term in haystack)
        if matched_terms:
            score += min(0.08 + len(matched_terms) * 0.03, 0.2)
        if max_source_score >= max(float(rule.trigger_threshold or 0.0), 0.65):
            score += 0.08

        score = round(max(0.0, min(score, 1.0)), 4)
        if score >= 0.72:
            level = "high"
        elif score >= 0.48:
            level = "medium"
        elif score > 0.0:
            level = "low"
        else:
            level = "none"

        refresh_threshold = min(max(float(rule.trigger_threshold or 0.0), 0.55), 0.8)
        reasons = []
        if max_significance:
            reasons.append(f"source significance contributes {max_significance:.2f}")
        if changed_records:
            reasons.append(f"{len(changed_records)} changed source group(s)")
        if max_source_score:
            reasons.append(f"top source importance score is {max_source_score:.2f}")
        if matched_terms:
            reasons.append("shock terms: " + ", ".join(matched_terms[:5]))

        return {
            "score": score,
            "level": level,
            "should_refresh": score >= refresh_threshold,
            "refresh_threshold": refresh_threshold,
            "reasons": reasons,
            "changed_records": len(changed_records),
            "qualified_sources": len(qualified_sources),
            "top_source_score": round(max_source_score, 4),
        }

    def _evidence_impact_context_lines(self, evidence_impact: dict[str, Any]) -> list[str]:
        reasons = evidence_impact.get("reasons") or []
        return [
            "Auto-triggered because new evidence impact exceeded the refresh threshold.",
            f"Evidence impact score: {evidence_impact.get('score')} "
            f"({evidence_impact.get('level')}); "
            f"threshold: {evidence_impact.get('refresh_threshold')}.",
            "Impact reasons: " + ("; ".join(str(reason) for reason in reasons) or "none"),
        ]

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
        return max(self._source_score(rule, source) for source in sources) >= float(
            rule.trigger_threshold or 0.0
        )

    def _source_score(self, rule: WatchRule, source) -> float:
        haystack = f"{source.title} {source.summary}".lower()
        if any(term.lower() in haystack for term in (rule.exclude_keywords or []) if term):
            return 0.0
        keywords = [term.lower() for term in (rule.keywords or []) if term]
        entity_tags = [term.lower() for term in (rule.entity_tags or []) if term]
        terms = (
            keywords or entity_tags or [token.lower() for token in rule.query.split()[:6] if token]
        )
        matched = sum(1 for term in terms if term and term in haystack)
        score = 0.35 + min(matched * 0.18, 0.45)
        engagement = (
            source.metadata.get("engagement", {}) if isinstance(source.metadata, dict) else {}
        )
        if isinstance(engagement, dict) and any(
            value for value in engagement.values() if isinstance(value, (int, float))
        ):
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

    def _community_window_expired(self, rule: WatchRule) -> bool:
        created_at = rule.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=utc_now().tzinfo)
        return utc_now() - created_at >= timedelta(hours=24)

    async def _mark_poll_success(self, session, rule: WatchRule) -> None:
        now = utc_now()
        expires_at = rule.created_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=now.tzinfo)
        expires_at = expires_at + timedelta(hours=24)
        rule.last_poll_at = now
        rule.last_poll_error = None
        rule.lease_owner = None
        rule.lease_expires_at = None
        next_poll_at = now + timedelta(minutes=rule.poll_interval_minutes)
        rule.next_poll_at = next_poll_at if next_poll_at < expires_at else None
        if rule.next_poll_at is None:
            rule.enabled = False
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
