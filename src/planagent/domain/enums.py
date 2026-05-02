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
    PREDICTION_VERSION_CREATED = "prediction.version_created"
    PREDICTION_REVISION_REQUESTED = "prediction.revision_requested"
    PREDICTION_REVISION_COMPLETED = "prediction.revision_completed"
    PREDICTION_REVISION_FAILED = "prediction.revision_failed"


class PredictionSeriesStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class PredictionVersionStatus(StrEnum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    FAILED = "FAILED"


class RevisionJobStatus(StrEnum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class TriggerType(StrEnum):
    INITIAL = "initial"
    EVIDENCE_UPDATE = "evidence_update"
    MANUAL = "manual"
    BACKTEST = "backtest"


class LinkType(StrEnum):
    SUPPORTING = "supporting"
    CONFLICTING = "conflicting"
    SHOCK = "shock"
    DECISION_BASIS = "decision_basis"
    REVISION_TRIGGER = "revision_trigger"


class ImpactDirection(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    UNKNOWN = "unknown"
