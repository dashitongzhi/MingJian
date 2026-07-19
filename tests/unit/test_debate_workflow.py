from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from planagent.domain.api import DebateDetailRead, DebateTriggerRequest
from planagent.services.debate import (
    DebateAssessment,
    DebateCommand,
    DebateFinished,
    DebateInterruptInjected,
    DebateRoundCompleted,
    DebateRoundStarted,
    DebateTarget,
    DebateWorkflow,
)
from planagent.domain.models import DebateSessionRecord, SimulationRun
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


class _UnavailableLLMAdapter:
    async def prepare(self, *_args, **_kwargs):
        return None

    def is_available(self) -> bool:
        return False


class _FakeEventBus:
    async def publish(self, *_args, **_kwargs) -> None:
        return None


class _CancellationPort:
    llm_adapter = _UnavailableLLMAdapter()
    event_bus = _FakeEventBus()

    async def _resolve_trigger_payload(self, _session, payload):
        return payload

    async def _assess_debate(self, _session, _payload) -> DebateAssessment:
        return DebateAssessment(
            support_confidence=0.7,
            challenge_confidence=0.3,
            verdict="ACCEPTED",
            winning_arguments=["Supported"],
            decisive_evidence=[],
            conditions=None,
            minority_opinion=None,
            context_payload={},
            rounds=[
                {
                    "round_number": 1,
                    "role": "advocate",
                    "position": "SUPPORT",
                    "confidence": 0.7,
                    "arguments": [],
                    "rebuttals": [],
                    "concessions": [],
                }
            ],
            recommendations=[],
            risk_factors=[],
            alternative_scenarios=[],
            conclusion_summary="Supported",
        )

    async def _persist_stream_round(self, *_args, **_kwargs) -> None:
        return None

    def _round_complete_payload(self, round_payload):
        return {
            "round_number": round_payload["round_number"],
            "role": round_payload["role"],
            "position": round_payload["position"],
            "confidence": round_payload["confidence"],
            "key_arguments": [],
        }

    async def _complete_debate(self, **_kwargs):
        raise AssertionError("cancelled stream must not complete")


class _CancellationSession:
    def __init__(self) -> None:
        self.debate: DebateSessionRecord | None = None
        self.commit_count = 0
        self.rollback_count = 0

    @asynccontextmanager
    async def begin_nested(self):
        yield self

    def add(self, record) -> None:
        if isinstance(record, DebateSessionRecord):
            record.id = record.id or "debate-cancelled"
            self.debate = record

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        self.commit_count += 1

    async def rollback(self) -> None:
        self.rollback_count += 1

    async def get(self, model, record_id):
        if model is SimulationRun:
            return SimpleNamespace(id=record_id, tenant_id=None, preset_id=None)
        if model is DebateSessionRecord and self.debate is not None:
            return self.debate if self.debate.id == record_id else None
        return None


@pytest.mark.anyio
async def test_closing_observation_stream_marks_debate_failed() -> None:
    session = _CancellationSession()
    workflow = DebateWorkflow(_CancellationPort())  # type: ignore[arg-type]
    stream = workflow.observe(
        session,  # type: ignore[arg-type]
        DebateCommand(target=DebateTarget.run("run-1"), topic="Should we proceed?"),
    )

    first = await anext(stream)
    assert isinstance(first, DebateRoundStarted)

    await stream.aclose()

    assert session.debate is not None
    assert session.debate.status == "FAILED"
    assert session.rollback_count == 1
    assert session.commit_count == 2
