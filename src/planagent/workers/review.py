from __future__ import annotations

from planagent.domain.enums import EventTopic
from planagent.workers.base import Worker, WorkerDescription


class ReviewWorker(Worker):
    description = WorkerDescription(
        worker_id="review-worker",
        summary="Reserved for analyst-assist review automation and escalation workflows.",
        consumes=(EventTopic.CLAIM_REVIEW_REQUESTED.value,),
        produces=(EventTopic.EVIDENCE_CREATED.value,),
    )

    async def run_once(self) -> dict[str, object]:
        return {"status": "placeholder", "message": "Human-in-the-loop review remains manual in Phase 1."}
