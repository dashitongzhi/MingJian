from __future__ import annotations

from abc import ABC, abstractmethod
import importlib
import os
import pkgutil
from pathlib import Path

from planagent.simulation.specs import (
    ActionSpec,
    ActorTemplate,
    EntityTypeSpec,
    EventTypeSpec,
    StateFieldSpec,
)


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
        self._loaded_modules: set[str] = set()

    def register(self, pack: DomainPack) -> None:
        self._packs[pack.domain_id] = pack

    def get(self, domain_id: str) -> DomainPack:
        return self._packs[domain_id]

    def all(self) -> list[DomainPack]:
        return list(self._packs.values())

    def discover(self, package_name: str = "planagent.simulation.domain_packs") -> list[str]:
        """Import domain pack modules so they can self-register.

        Built-in packs keep their existing registration side effect, while Cloud and
        Enterprise can add private packages through PLANAGENT_DOMAIN_PACK_MODULES.
        """
        loaded: list[str] = []
        package = importlib.import_module(package_name)
        package_paths = getattr(package, "__path__", None)
        if package_paths is not None:
            for module_info in pkgutil.iter_modules(package_paths):
                if module_info.name.startswith("_"):
                    continue
                module_name = f"{package_name}.{module_info.name}.pack"
                if self._import_once(module_name):
                    loaded.append(module_name)

        for module_name in _configured_domain_pack_modules():
            if self._import_once(module_name):
                loaded.append(module_name)
        return loaded

    def _import_once(self, module_name: str) -> bool:
        if module_name in self._loaded_modules:
            return False
        importlib.import_module(module_name)
        self._loaded_modules.add(module_name)
        return True


registry = DomainPackRegistry()


def _configured_domain_pack_modules() -> list[str]:
    raw = os.getenv("PLANAGENT_DOMAIN_PACK_MODULES", "")
    return [item.strip() for item in raw.split(",") if item.strip()]
