from __future__ import annotations

from planagent.config import Settings
from planagent.db import get_database
from planagent.domain.enums import EventTopic
from planagent.events.bus import EventBus
from planagent.services.openai_client import OpenAIService
from planagent.services.simulation import SimulationService
from planagent.simulation.rules import RuleRegistry
from planagent.workers.base import Worker, WorkerDescription


class ReportWorker(Worker):
    description = WorkerDescription(
        worker_id="report-worker",
        summary="Generates reports for completed simulation runs missing a persisted report.",
        consumes=(EventTopic.SIMULATION_COMPLETED.value, EventTopic.SCENARIO_COMPLETED.value),
        produces=(EventTopic.REPORT_GENERATED.value,),
    )

    def __init__(
        self,
        settings: Settings,
        event_bus: EventBus,
        rule_registry: RuleRegistry,
        openai_service: OpenAIService | None = None,
    ) -> None:
        self.settings = settings
        self.event_bus = event_bus
        self.openai_service = openai_service
        self.worker_instance_id = self.description.worker_id
        self.service = SimulationService(settings, event_bus, rule_registry, openai_service)

    async def run_once(self) -> dict[str, object]:
        database = get_database()
        async with database.session() as session:
            generated_reports = await self.service.generate_pending_reports(
                session,
                worker_id=self.worker_instance_id,
            )
        return {"generated_reports": generated_reports}
