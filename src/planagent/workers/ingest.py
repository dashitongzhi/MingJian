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
        summary="Stages queued ingest runs into raw source items and emits raw ingestion events.",
        consumes=(),
        produces=(EventTopic.RAW_INGESTED.value,),
    )

    def __init__(
        self,
        settings: Settings,
        event_bus: EventBus,
        openai_service: OpenAIService | None = None,
    ) -> None:
        self.settings = settings
        self.event_bus = event_bus
        self.openai_service = openai_service
        self.worker_instance_id = self.description.worker_id
        self.service = PhaseOnePipelineService(settings, event_bus, openai_service)

    async def run_once(self) -> dict[str, object]:
        database = get_database(self.settings.database_url)
        async with database.session() as session:
            processed_runs = await self.service.process_queued_runs(
                session,
                worker_id=self.worker_instance_id,
            )
        return {"processed_runs": processed_runs}
