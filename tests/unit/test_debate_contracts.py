from dataclasses import FrozenInstanceError

import pytest

from planagent.services.debate import (
    ClaimRelationContext as ExportedClaimRelationContext,
    DebateAssessment as ExportedDebateAssessment,
    DebateStreamEvent as ExportedDebateStreamEvent,
    DebateStreamPreparation as ExportedDebateStreamPreparation,
)
from planagent.services.debate.contracts import (
    ClaimRelationContext,
    DebateAssessment,
    DebateStreamEvent,
    DebateStreamPreparation,
)


def test_debate_contracts_keep_the_package_export_interface() -> None:
    assert ExportedDebateAssessment is DebateAssessment
    assert ExportedDebateStreamEvent is DebateStreamEvent
    assert ExportedDebateStreamPreparation is DebateStreamPreparation
    assert ExportedClaimRelationContext is ClaimRelationContext


def test_debate_contracts_are_immutable_observable_results() -> None:
    event = DebateStreamEvent(event="debate_started", payload={"debate_id": "debate-1"})

    with pytest.raises(FrozenInstanceError):
        event.event = "debate_completed"


def test_stream_preparation_preserves_execution_inputs() -> None:
    preparation = DebateStreamPreparation(
        context="Decision context",
        llm_evidence_ids=["evidence-1"],
        assessment_evidence_ids=["evidence-1", "evidence-2"],
        assessment_kwargs={"run_id": "run-1"},
    )

    assert preparation.context == "Decision context"
    assert preparation.llm_evidence_ids == ["evidence-1"]
    assert preparation.assessment_evidence_ids == ["evidence-1", "evidence-2"]
    assert preparation.assessment_kwargs == {"run_id": "run-1"}
