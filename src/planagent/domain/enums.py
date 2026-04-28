from enum import StrEnum


class ExecutionMode(StrEnum):
    INLINE = "INLINE"
    QUEUED = "QUEUED"


class IngestRunStatus(StrEnum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class SimulationRunStatus(StrEnum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ClaimStatus(StrEnum):
    ACCEPTED = "ACCEPTED"
    PENDING_REVIEW = "PENDING_REVIEW"
    REJECTED = "REJECTED"
    ARCHIVED = "ARCHIVED"


class ReviewItemStatus(StrEnum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class EventTopic(StrEnum):
    RAW_INGESTED = "raw.ingested"
    EVIDENCE_CREATED = "evidence.created"
    CLAIM_REVIEW_REQUESTED = "claim.review_requested"
    KNOWLEDGE_EXTRACTED = "knowledge.extracted"
    SIMULATION_COMPLETED = "simulation.completed"
    SCENARIO_COMPLETED = "scenario.completed"
    REPORT_GENERATED = "report.generated"
    VERIFICATION_FAILED = "verification.failed"
    DEBATE_TRIGGERED = "debate.triggered"
    DEBATE_COMPLETED = "debate.completed"
    EVIDENCE_UPDATED = "evidence.updated"
    WATCH_RULE_TRIGGERED = "watch.rule_triggered"
