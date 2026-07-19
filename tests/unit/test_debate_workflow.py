from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from planagent.domain.api import DebateDetailRead, DebateTriggerRequest
from planagent.services.debate import (
    DebateCommand,
    DebateFinished,
    DebateInterruptInjected,
    DebateRoundCompleted,
    DebateRoundStarted,
    DebateTarget,
)
from planagent.services.debate._legacy import (
    _command_from_legacy_request,
    _legacy_event_from_observation,
)


def _detail() -> DebateDetailRead:
    now = datetime.now(timezone.utc)
    return DebateDetailRead(
        id="debate-1",
        run_id="run-1",
        topic="Should the plan change?",
        trigger_type="manual",
        status="COMPLETED",
        target_type="run",
        target_id="run-1",
        rounds=[],
        verdict=None,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.anyio
async def test_legacy_request_is_normalized_to_one_canonical_command() -> None:
    command = await _command_from_legacy_request(
        SimpleNamespace(),  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
        DebateTriggerRequest(
            claim_id="claim-1",
            target_type="claim",
            target_id="claim-1",
            topic="  Should this claim be accepted?  ",
            context_lines=["accepted conflicting evidence"],
        ),
    )

    assert command == DebateCommand(
        target=DebateTarget.claim("claim-1"),
        topic="Should this claim be accepted?",
        context=("accepted conflicting evidence",),
    )


@pytest.fixture()
def anyio_backend() -> str:
    return "asyncio"


def test_typed_observations_project_to_the_legacy_sse_contract() -> None:
    detail = _detail()
    observations = [
        DebateInterruptInjected(
            debate_id="debate-1",
            round_number=1,
            role="advocate",
            count=1,
            interrupt_ids=("interrupt-1",),
        ),
        DebateRoundStarted(debate_id="debate-1", round_number=1, role="advocate"),
        DebateRoundCompleted(
            debate_id="debate-1",
            round_number=1,
            role="advocate",
            position="SUPPORT",
            confidence=0.8,
            key_arguments=("Keep the plan.",),
        ),
        DebateFinished(debate_id="debate-1", debate=detail),
    ]

    events = [_legacy_event_from_observation(item) for item in observations]

    assert [item.event for item in events] == [
        "debate_interrupt_injected",
        "debate_round_start",
        "debate_round_complete",
        "debate_verdict",
    ]
    assert events[0].payload["interrupt_ids"] == ["interrupt-1"]
    assert events[2].payload["key_arguments"] == ["Keep the plan."]
    assert events[3].payload == {
        "debate_id": "debate-1",
        "verdict": None,
        "confidence": None,
        "winning_arguments": [],
        "decisive_evidence": [],
    }
