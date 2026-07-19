from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from planagent.config import Settings
from planagent.domain.models import WatchRule
from planagent.services.community_monitoring import (
    CommunityMonitoringService,
    monitoring_expires_at,
    monitoring_window_expired,
    next_poll_within_window,
    next_schedule_within_window,
    watch_rule_monitoring_payload,
)


def test_monitoring_window_normalizes_naive_created_at_to_utc() -> None:
    created_at = datetime(2026, 7, 20, 8, 0)

    assert monitoring_expires_at(created_at) == datetime(2026, 7, 21, 8, 0, tzinfo=timezone.utc)
    assert not monitoring_window_expired(
        created_at,
        now=datetime(2026, 7, 21, 7, 59, tzinfo=timezone.utc),
    )
    assert monitoring_window_expired(
        created_at,
        now=datetime(2026, 7, 21, 8, 0, tzinfo=timezone.utc),
    )


def test_next_poll_never_crosses_community_window() -> None:
    created_at = datetime(2026, 7, 20, 8, 0, tzinfo=timezone.utc)

    assert next_poll_within_window(
        created_at,
        30,
        now=datetime(2026, 7, 21, 7, 0, tzinfo=timezone.utc),
    ) == datetime(2026, 7, 21, 7, 30, tzinfo=timezone.utc)
    assert (
        next_poll_within_window(
            created_at,
            30,
            now=datetime(2026, 7, 21, 7, 30, tzinfo=timezone.utc),
        )
        is None
    )

    assert (
        next_schedule_within_window(
            created_at,
            timedelta(hours=1),
            now=datetime(2026, 7, 21, 7, 0, tzinfo=timezone.utc),
        )
        is None
    )


def test_watch_rule_payload_keeps_fixed_community_expiry() -> None:
    created_at = datetime(2026, 7, 20, 8, 0, tzinfo=timezone.utc)
    rule = WatchRule(
        id="watch-1",
        name="AI market",
        domain_id="corporate",
        query="AI market",
        source_types=[],
        poll_interval_minutes=60,
        auto_trigger_debate=True,
        enabled=True,
        created_at=created_at,
        next_poll_at=created_at + timedelta(hours=1),
    )

    active = watch_rule_monitoring_payload(
        rule,
        now=datetime(2026, 7, 21, 7, 59, tzinfo=timezone.utc),
    )
    expired = watch_rule_monitoring_payload(
        rule,
        now=datetime(2026, 7, 21, 8, 0, tzinfo=timezone.utc),
    )

    assert active["status"] == "active"
    assert active["mode"] == "community_24h"
    assert active["expires_at"] == "2026-07-21T08:00:00+00:00"
    assert expired["status"] == "expired"


@pytest.mark.asyncio
async def test_session_monitoring_start_caps_late_watch_rule() -> None:
    class EmptyScalars:
        def first(self) -> None:
            return None

    session = SimpleNamespace(
        scalars=AsyncMock(return_value=EmptyScalars()),
        add=MagicMock(),
        flush=AsyncMock(),
    )
    service = CommunityMonitoringService(Settings(_env_file=None))
    service.source_state_service.seed_watch_rule_sources = AsyncMock()
    started_at = datetime.now(timezone.utc) - timedelta(hours=25)

    rule = await service.ensure_watch_rule(
        session,
        "Delayed monitoring",
        "corporate",
        1,
        session_id="session-1",
        monitoring_started_at=started_at,
    )

    assert rule.created_at == started_at
    assert rule.enabled is False
    assert rule.next_poll_at is None
