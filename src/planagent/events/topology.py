from __future__ import annotations

from dataclasses import asdict, dataclass

from planagent.domain.enums import EventTopic
from planagent.workers.base import WorkerDescription
from planagent.workers.graph import GraphWorker
from planagent.workers.ingest import IngestWorker
from planagent.workers.knowledge import KnowledgeWorker
from planagent.workers.report import ReportWorker
from planagent.workers.review import ReviewWorker
from planagent.workers.simulation import SimulationWorker


@dataclass(frozen=True)
class StreamTopologySpec:
    topic: str
    stream: str
    consumer_group: str | None
    consumer_groups: tuple[str, ...]
    producers: tuple[str, ...]
    consumers: tuple[str, ...]
    dead_letter_stream: str
    backpressure_scope: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


WORKER_DESCRIPTIONS: tuple[WorkerDescription, ...] = (
    IngestWorker.description,
    KnowledgeWorker.description,
    GraphWorker.description,
    ReviewWorker.description,
    SimulationWorker.description,
    ReportWorker.description,
)


def stream_name(topic: str) -> str:
    return f"stream:{topic}"


def dead_letter_stream_name(topic: str) -> str:
    return f"stream:{topic}.dlq"


def build_stream_topology() -> list[StreamTopologySpec]:
    topics = {
        EventTopic.RAW_INGESTED.value,
        EventTopic.EVIDENCE_CREATED.value,
        EventTopic.CLAIM_REVIEW_REQUESTED.value,
        EventTopic.KNOWLEDGE_EXTRACTED.value,
        EventTopic.EVIDENCE_UPDATED.value,
        EventTopic.SIMULATION_COMPLETED.value,
        EventTopic.SCENARIO_COMPLETED.value,
        EventTopic.REPORT_GENERATED.value,
        EventTopic.VERIFICATION_FAILED.value,
        EventTopic.JARVIS_REPAIR_REQUESTED.value,
    }
    for description in WORKER_DESCRIPTIONS:
        topics.update(description.consumes)
        topics.update(description.produces)

    topology: list[StreamTopologySpec] = []
    for topic in sorted(topics):
        consumers = tuple(
            description.worker_id
            for description in WORKER_DESCRIPTIONS
            if topic in description.consumes
        )
        producers = tuple(
            description.worker_id
            for description in WORKER_DESCRIPTIONS
            if topic in description.produces
        )
        topology.append(
            StreamTopologySpec(
                topic=topic,
                stream=stream_name(topic),
                consumer_group=consumers[0] if consumers else None,
                consumer_groups=consumers,
                producers=producers or ("control-api",),
                consumers=consumers,
                dead_letter_stream=dead_letter_stream_name(topic),
                backpressure_scope="worker" if consumers else "api",
            )
        )
    return topology


def topology_by_topic() -> dict[str, StreamTopologySpec]:
    return {item.topic: item for item in build_stream_topology()}


def validate_stream_topology() -> list[str]:
    errors: list[str] = []
    by_topic = topology_by_topic()
    for description in WORKER_DESCRIPTIONS:
        for topic in description.consumes:
            spec = by_topic.get(topic)
            if spec is None:
                errors.append(f"missing topology for consumed topic {topic}")
                continue
            if description.worker_id not in spec.consumers:
                errors.append(f"{description.worker_id} not registered as consumer for {topic}")
            if description.worker_id not in spec.consumer_groups:
                errors.append(f"{topic} missing consumer group {description.worker_id}")
        for topic in description.produces:
            spec = by_topic.get(topic)
            if spec is None:
                errors.append(f"missing topology for produced topic {topic}")
                continue
            if description.worker_id not in spec.producers:
                errors.append(f"{description.worker_id} not registered as producer for {topic}")
    for required in (
        EventTopic.VERIFICATION_FAILED.value,
        EventTopic.JARVIS_REPAIR_REQUESTED.value,
    ):
        if required not in by_topic:
            errors.append(f"missing Jarvis closure topic {required}")
    return errors
