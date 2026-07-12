from __future__ import annotations

from planagent.config import Settings
from planagent.db import get_database
from planagent.domain.enums import EventTopic
from planagent.events.bus import EventBus
from planagent.services.openai_client import OpenAIService
from planagent.services.pipeline import PhaseOnePipelineService
from planagent.services.runtime import RuntimeMonitorService
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
        active_getter = getattr(self.event_bus, "is_backpressure_active", None)
        if active_getter is not None and await active_getter():
            return {
                "processed_runs": 0,
                "backpressure_active": True,
                "reason": "event_bus_backpressure_signal",
                "threshold": self.settings.backpressure_pending_threshold,
            }

        database = get_database()
        async with database.session() as session:
            queue_health = await RuntimeMonitorService(
                self.settings.backpressure_pending_threshold,
                self.settings.runtime_recent_error_window_hours,
            ).collect_queue_health(session)
            if queue_health.backpressure_active:
                setter = getattr(self.event_bus, "set_backpressure_signal", None)
                if setter is not None:
                    await setter(
                        True,
                        "queue pending or reclaimable work exceeded backpressure threshold",
                    )
                return {
                    "processed_runs": 0,
                    "backpressure_active": True,
                    "threshold": self.settings.backpressure_pending_threshold,
                }
            setter = getattr(self.event_bus, "set_backpressure_signal", None)
            if setter is not None:
                await setter(False, "queue pressure normalized")
            processed_runs = await self.service.process_queued_runs(
                session,
                worker_id=self.worker_instance_id,
            )
        return {"processed_runs": processed_runs, "backpressure_active": False}
