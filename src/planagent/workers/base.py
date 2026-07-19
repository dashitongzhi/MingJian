from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass

WORKER_PUBLIC_ERROR = "Worker execution failed"


def public_worker_error(record_type: str, record_id: object) -> str:
    """Build a stable worker result without exposing exception details."""
    return f"{record_type}:{record_id}:{WORKER_PUBLIC_ERROR}"


@dataclass(frozen=True)
class WorkerDescription:
    worker_id: str
    summary: str
    consumes: tuple[str, ...]
    produces: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class Worker(ABC):
    description: WorkerDescription

    @abstractmethod
    async def run_once(self) -> dict[str, object]:
        raise NotImplementedError
