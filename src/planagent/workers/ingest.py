from __future__ import annotations

from planagent.config import Settings
from planagent.db import get_database
from planagent.domain.enums import EventTopic
from planagent.events.bus import EventBus
from planagent.services.openai_client import OpenAIService
from planagent.services.pipeline import PhaseOnePipelineService
from planagent.workers.base import Worker, WorkerDescription


class IngestWorker(Worker):
    description = WorkerDescription(
        worker_id="ingest-worker",
        summary="Processes queued ingest runs and emits raw/evidence/knowledge events.",
        consumes=(),
        produces=(
            EventTopic.RAW_INGESTED.value,
            EventTopic.EVIDENCE_CREATED.value,
            EventTopic.CLAIM_REVIEW_REQUESTED.value,
            EventTopic.KNOWLEDGE_EXTRACTED.value,
        ),
    )

    def __init__(
        self,
        settings: Settings,
        event_bus: EventBus,
        openai_service: OpenAIService | None = None,
    ) -> None:
        self.settings = settings
        self.openai_service = openai_service
        self.service = PhaseOnePipelineService(settings, event_bus, openai_service)

    async def run_once(self) -> dict[str, object]:
        database = get_database(self.settings.database_url)
        async with database.session() as session:
            processed_runs = await self.service.process_queued_runs(session)
        return {"processed_runs": processed_runs}
