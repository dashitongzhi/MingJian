from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


class PredictionHooks(Protocol):
    def before_reforecast(self, payload: dict[str, Any]) -> dict[str, Any]:
        ...

    def after_reforecast(self, payload: dict[str, Any], result: dict[str, Any]) -> None:
        ...


class NotificationBackend(Protocol):
    def send(self, channel: str, payload: dict[str, Any]) -> None:
        ...


class NoopPredictionHooks:
    def before_reforecast(self, payload: dict[str, Any]) -> dict[str, Any]:
        return payload

    def after_reforecast(self, payload: dict[str, Any], result: dict[str, Any]) -> None:
        return None


class NoopNotificationBackend:
    def send(self, channel: str, payload: dict[str, Any]) -> None:
        return None


@dataclass
class SourceExtensionRegistry:
    _extensions: dict[str, Any] = field(default_factory=dict)

    def register(self, key: str, extension: Any) -> None:
        self._extensions[key] = extension

    def get(self, key: str) -> Any:
        return self._extensions[key]

    def all(self) -> dict[str, Any]:
        return dict(self._extensions)


@dataclass
class AgentExtensionRegistry:
    _extensions: dict[str, Any] = field(default_factory=dict)

    def register(self, key: str, extension: Any) -> None:
        self._extensions[key] = extension

    def get(self, key: str) -> Any:
        return self._extensions[key]

    def all(self) -> dict[str, Any]:
        return dict(self._extensions)


prediction_hooks: PredictionHooks = NoopPredictionHooks()
notification_backend: NotificationBackend = NoopNotificationBackend()
source_extensions = SourceExtensionRegistry()
agent_extensions = AgentExtensionRegistry()
