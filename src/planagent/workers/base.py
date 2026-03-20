from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass


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
