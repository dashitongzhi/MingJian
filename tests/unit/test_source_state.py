from __future__ import annotations

from datetime import timedelta

import pytest

from planagent.config import Settings
from planagent.domain.models import SourceCursorState, utc_now
from planagent.services.source_state import SourceStateService


@pytest.mark.asyncio
async def test_should_fetch_applies_failure_backoff_after_circuit_breaker() -> None:
    service = SourceStateService(
        Settings(
            _env_file=None,
            source_failure_circuit_breaker_threshold=10,
            source_failure_backoff_base_minutes=5,
            source_failure_backoff_max_minutes=60,
        )
    )
    state = SourceCursorState(
        source_type="gdelt",
        source_url_or_query="ai market risk",
        consecutive_failures=10,
        last_failure_at=utc_now() - timedelta(minutes=3),
    )

    assert await service.should_fetch(None, state) is False

    state.last_failure_at = utc_now() - timedelta(minutes=6)
    assert await service.should_fetch(None, state) is True


@pytest.mark.asyncio
async def test_should_fetch_keeps_short_failure_streaks_probeable() -> None:
    service = SourceStateService(
        Settings(_env_file=None, source_failure_circuit_breaker_threshold=10)
    )
    state = SourceCursorState(
        source_type="reddit",
        source_url_or_query="ai market risk",
        consecutive_failures=3,
        last_failure_at=utc_now(),
    )

    assert await service.should_fetch(None, state) is True
