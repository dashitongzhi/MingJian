from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Self, TypeAlias

from planagent.domain.api import DebateDetailRead
from planagent.domain.models import Claim

DebateTargetKind: TypeAlias = Literal["run", "claim", "branch", "report"]
DebateTriggerType: TypeAlias = Literal[
    "manual",
    "evidence_assessment",
    "conflict_resolution",
    "pivot_decision",
    "branch_evaluation",
    "report_challenge",
]
DebateMode: TypeAlias = Literal["full", "fast"]
DebateExecutionPhase: TypeAlias = Literal["prepare", "rounds", "adjudicate", "persist", "publish"]


class InvalidDebateCommand(ValueError):
    """Raised when a debate command cannot represent one canonical target."""


class DebateTargetNotFound(LookupError):
    """Raised when the canonical debate target does not exist."""


class DebateExecutionFailed(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        phase: DebateExecutionPhase,
        debate_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.phase = phase
        self.debate_id = debate_id


@dataclass(frozen=True)
class DebateTarget:
    kind: DebateTargetKind
    id: str
    run_id: str | None = None

    def __post_init__(self) -> None:
        target_id = self.id.strip()
        if not target_id:
            raise InvalidDebateCommand("Debate target id cannot be empty.")
        if self.kind == "report":
            if self.run_id is None or not self.run_id.strip():
                raise InvalidDebateCommand("Report debates require their owning run id.")
        elif self.run_id is not None:
            raise InvalidDebateCommand("Only report targets may carry a separate run id.")
        object.__setattr__(self, "id", target_id)
        if self.run_id is not None:
            object.__setattr__(self, "run_id", self.run_id.strip())

    @classmethod
    def run(cls, run_id: str) -> Self:
        return cls(kind="run", id=run_id)

    @classmethod
    def claim(cls, claim_id: str) -> Self:
        return cls(kind="claim", id=claim_id)

    @classmethod
    def branch(cls, branch_id: str) -> Self:
        return cls(kind="branch", id=branch_id)

    @classmethod
    def report(cls, report_id: str, run_id: str) -> Self:
        return cls(kind="report", id=report_id, run_id=run_id)


@dataclass(frozen=True)
class DebateCommand:
    target: DebateTarget
    topic: str
    trigger_type: DebateTriggerType = "manual"
    context: tuple[str, ...] = ()
    mode: DebateMode = "full"
    domain_id: str | None = None

    def __post_init__(self) -> None:
        topic = self.topic.strip()
        if not topic:
            raise InvalidDebateCommand("Debate topic cannot be empty.")
        object.__setattr__(self, "topic", topic)
        object.__setattr__(self, "context", tuple(self.context))


@dataclass(frozen=True)
class DebateAssessment:
    support_confidence: float
    challenge_confidence: float
    verdict: str
    winning_arguments: list[str]
    decisive_evidence: list[str]
    conditions: list[str] | None
    minority_opinion: str | None
    context_payload: dict[str, Any]
    rounds: list[dict[str, Any]]
    recommendations: list[dict[str, Any]]
    risk_factors: list[str]
    alternative_scenarios: list[dict[str, Any]]
    conclusion_summary: str


@dataclass(frozen=True)
class DebateStreamEvent:
    event: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class DebateInterruptInjected:
    debate_id: str
    round_number: int
    role: str
    count: int
    interrupt_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class DebateRoundStarted:
    debate_id: str
    round_number: int
    role: str


@dataclass(frozen=True)
class DebateRoundCompleted:
    debate_id: str
    round_number: int
    role: str
    position: str
    confidence: float
    key_arguments: tuple[str, ...] = ()


@dataclass(frozen=True)
class DebateFinished:
    debate_id: str
    debate: DebateDetailRead


DebateObservation: TypeAlias = (
    DebateInterruptInjected | DebateRoundStarted | DebateRoundCompleted | DebateFinished
)


@dataclass(frozen=True)
class DebateStreamPreparation:
    context: str
    llm_evidence_ids: list[str]
    assessment_evidence_ids: list[str]
    assessment_kwargs: dict[str, Any]


@dataclass(frozen=True)
class ClaimRelationContext:
    supportive_claims: list[Claim]
    conflicting_claims: list[Claim]
