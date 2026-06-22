from __future__ import annotations

import pytest

from planagent.config import Settings
from planagent.domain.models import SourceCursorState
from planagent.services.change_detection import ChangeDetectionService


class RecordingSession:
    def __init__(self) -> None:
        self.added = []
        self.flush_count = 0

    def add(self, item) -> None:
        self.added.append(item)

    async def flush(self) -> None:
        self.flush_count += 1


@pytest.mark.asyncio
async def test_unchanged_source_change_is_not_persisted() -> None:
    service = ChangeDetectionService(Settings(_env_file=None))
    session = RecordingSession()
    state = SourceCursorState(
        id="source-state-1",
        source_type="gdelt",
        source_url_or_query="market risk",
        last_seen_hash="same-hash",
    )

    record = await service.detect_change(
        session,
        state,
        new_hash="same-hash",
        new_content_text="same content",
        new_title="Market risk",
        new_raw_source_item_id=None,
    )

    assert record.change_type == "unchanged"
    assert record.significance == "none"
    assert session.added == []
    assert session.flush_count == 0
    assert state.last_change_at is None


@pytest.mark.asyncio
async def test_updated_source_change_is_persisted() -> None:
    service = ChangeDetectionService(Settings(_env_file=None))
    session = RecordingSession()
    state = SourceCursorState(
        id="source-state-1",
        source_type="gdelt",
        source_url_or_query="market risk",
        last_seen_hash="old-hash",
    )

    record = await service.detect_change(
        session,
        state,
        new_hash="new-hash",
        new_content_text="new market risk content",
        new_title="Market risk",
        new_raw_source_item_id=None,
    )

    assert record.change_type == "updated"
    assert session.added == [record]
    assert session.flush_count == 1
    assert state.health_status == "changed"
    assert state.last_change_at is not None
