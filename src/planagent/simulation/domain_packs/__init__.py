from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from planagent.simulation.specs import ActionSpec, ActorTemplate, EntityTypeSpec, EventTypeSpec, StateFieldSpec


class DomainPack(ABC):
    @property
    @abstractmethod
    def domain_id(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def entity_types(self) -> list[EntityTypeSpec]:
        raise NotImplementedError

    @property
    @abstractmethod
    def state_fields(self) -> list[StateFieldSpec]:
        raise NotImplementedError

    @property
    @abstractmethod
    def action_library(self) -> list[ActionSpec]:
        raise NotImplementedError

    @property
    @abstractmethod
    def event_types(self) -> list[EventTypeSpec]:
        raise NotImplementedError

    @property
    @abstractmethod
    def actor_templates(self) -> list[ActorTemplate]:
        raise NotImplementedError

    def rules_dir(self) -> Path:
        return Path("rules") / self.domain_id


class DomainPackRegistry:
    def __init__(self) -> None:
        self._packs: dict[str, DomainPack] = {}

    def register(self, pack: DomainPack) -> None:
        self._packs[pack.domain_id] = pack

    def get(self, domain_id: str) -> DomainPack:
        return self._packs[domain_id]

    def all(self) -> list[DomainPack]:
        return list(self._packs.values())


registry = DomainPackRegistry()

