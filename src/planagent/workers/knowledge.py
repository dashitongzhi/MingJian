from __future__ import annotations

from planagent.domain.enums import EventTopic
from planagent.workers.base import Worker, WorkerDescription


class KnowledgeWorker(Worker):
    description = WorkerDescription(
        worker_id="knowledge-worker",
        summary="Reserved for richer extraction, claim conflict analysis, and provenance scoring.",
        consumes=(EventTopic.RAW_INGESTED.value,),
        produces=(
            EventTopic.EVIDENCE_CREATED.value,
            EventTopic.CLAIM_REVIEW_REQUESTED.value,
            EventTopic.KNOWLEDGE_EXTRACTED.value,
        ),
    )

    async def run_once(self) -> dict[str, object]:
        return {"status": "placeholder", "message": "Phase 2 extraction worker not implemented yet."}
