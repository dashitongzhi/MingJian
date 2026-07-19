from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from planagent.config import Settings
from planagent.domain.models import WatchRule, utc_now
from planagent.services.source_state import SourceStateService

COMMUNITY_MONITORING_MODE = "community_24h"
COMMUNITY_MONITORING_WINDOW = timedelta(hours=24)


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def monitoring_expires_at(created_at: datetime) -> datetime:
    return as_utc(created_at) + COMMUNITY_MONITORING_WINDOW


def monitoring_window_expired(created_at: datetime, *, now: datetime | None = None) -> bool:
    current = as_utc(now or utc_now())
    return current >= monitoring_expires_at(created_at)


def next_poll_within_window(
    created_at: datetime,
    poll_interval_minutes: int,
    *,
    now: datetime | None = None,
) -> datetime | None:
    return next_schedule_within_window(
        created_at,
        timedelta(minutes=poll_interval_minutes),
        now=now,
    )


def next_schedule_within_window(
    created_at: datetime,
    delay: timedelta,
    *,
    now: datetime | None = None,
) -> datetime | None:
    current = as_utc(now or utc_now())
    candidate = current + delay
    expires_at = monitoring_expires_at(created_at)
    return candidate if candidate < expires_at else None


def watch_rule_monitoring_payload(
    watch_rule: WatchRule | None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    if watch_rule is None:
        return {"status": "inactive", "mode": COMMUNITY_MONITORING_MODE}

    current = as_utc(now or utc_now())
    expires_at = monitoring_expires_at(watch_rule.created_at)
    return {
        "status": "active" if watch_rule.enabled and current < expires_at else "expired",
        "mode": COMMUNITY_MONITORING_MODE,
        "watch_rule_id": watch_rule.id,
        "poll_interval_minutes": watch_rule.poll_interval_minutes,
        "next_poll_at": watch_rule.next_poll_at.isoformat()
        if watch_rule.next_poll_at is not None
        else None,
        "expires_at": expires_at.isoformat(),
        "scheduled_updates": True,
        "burst_updates": watch_rule.auto_trigger_debate,
    }


class CommunityMonitoringService:
    def __init__(self, settings: Settings) -> None:
        self.source_state_service = SourceStateService(settings)

    async def ensure_watch_rule(
        self,
        session: AsyncSession,
        topic: str,
        domain_id: str,
        tick_count: int | None,
        *,
        session_id: str | None = None,
        tenant_id: str | None = None,
        preset_id: str | None = None,
        monitoring_started_at: datetime | None = None,
    ) -> WatchRule:
        if session_id is not None:
            existing_query = (
                select(WatchRule)
                .where(WatchRule.session_id == session_id)
                .order_by(WatchRule.created_at.asc(), WatchRule.id.asc())
            )
        else:
            existing_query = (
                select(WatchRule)
                .where(
                    WatchRule.query == topic,
                    WatchRule.domain_id == domain_id,
                    WatchRule.tenant_id == tenant_id,
                    WatchRule.preset_id == preset_id,
                    WatchRule.session_id.is_(None),
                )
                .order_by(WatchRule.created_at.asc(), WatchRule.id.asc())
            )
        existing = (await session.scalars(existing_query.limit(1))).first()
        if existing is not None:
            self._apply_monitoring_start(existing, monitoring_started_at)
            await self._seed_sources(session, existing)
            return existing

        started_at = as_utc(monitoring_started_at or utc_now())
        expired = monitoring_window_expired(started_at)
        rule = WatchRule(
            session_id=session_id,
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
            enabled=not expired,
            tick_count=tick_count or 0,
            tenant_id=tenant_id,
            preset_id=preset_id,
            created_at=started_at,
            next_poll_at=None if expired else utc_now(),
        )
        session.add(rule)
        await session.flush()
        await self._seed_sources(session, rule)
        return rule

    async def _seed_sources(self, session: AsyncSession, rule: WatchRule) -> None:
        await self.source_state_service.seed_watch_rule_sources(
            session,
            watch_rule_id=rule.id,
            query=rule.query,
            source_types=rule.source_types or [],
            tenant_id=rule.tenant_id,
            preset_id=rule.preset_id,
        )

    def _apply_monitoring_start(
        self,
        rule: WatchRule,
        monitoring_started_at: datetime | None,
    ) -> None:
        if monitoring_started_at is None:
            return
        started_at = as_utc(monitoring_started_at)
        if started_at < as_utc(rule.created_at):
            rule.created_at = started_at
        if monitoring_window_expired(rule.created_at):
            rule.enabled = False
            rule.next_poll_at = None
