from dataclasses import FrozenInstanceError

import pytest

from planagent.services.debate import (
    ClaimRelationContext as ExportedClaimRelationContext,
    DebateAssessment as ExportedDebateAssessment,
    DebateCommand,
    DebateExecutionFailed,
    DebateStreamEvent as ExportedDebateStreamEvent,
    DebateStreamPreparation as ExportedDebateStreamPreparation,
    DebateTarget,
    InvalidDebateCommand,
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


@pytest.mark.parametrize(
    ("target", "kind", "target_id"),
    [
        (DebateTarget.run("run-1"), "run", "run-1"),
        (DebateTarget.claim("claim-1"), "claim", "claim-1"),
        (DebateTarget.branch("branch-1"), "branch", "branch-1"),
        (DebateTarget.report("report-1", "run-1"), "report", "report-1"),
    ],
)
def test_debate_target_constructors_create_one_canonical_target(
    target: DebateTarget,
    kind: str,
    target_id: str,
) -> None:
    assert target.kind == kind
    assert target.id == target_id


def test_report_target_requires_its_owning_run() -> None:
    with pytest.raises(InvalidDebateCommand, match="owning run"):
        DebateTarget(kind="report", id="report-1")


def test_non_report_target_rejects_a_second_run_identifier() -> None:
    with pytest.raises(InvalidDebateCommand, match="Only report"):
        DebateTarget(kind="claim", id="claim-1", run_id="run-1")


def test_debate_command_normalizes_topic_and_context() -> None:
    command = DebateCommand(
        target=DebateTarget.run("run-1"),
        topic="  Should the plan change?  ",
        context=["new evidence"],
    )

    assert command.topic == "Should the plan change?"
    assert command.context == ("new evidence",)


def test_debate_command_rejects_an_empty_topic() -> None:
    with pytest.raises(InvalidDebateCommand, match="topic"):
        DebateCommand(target=DebateTarget.run("run-1"), topic="   ")


def test_execution_failure_exposes_phase_without_losing_the_cause() -> None:
    cause = TimeoutError("provider timed out")

    with pytest.raises(DebateExecutionFailed) as raised:
        raise DebateExecutionFailed(
            "Debate execution failed.", phase="rounds", debate_id="debate-1"
        ) from cause

    assert raised.value.phase == "rounds"
    assert raised.value.debate_id == "debate-1"
    assert raised.value.__cause__ is cause
