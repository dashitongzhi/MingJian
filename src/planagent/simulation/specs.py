from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class EntityTypeSpec:
    entity_type: str
    description: str


@dataclass(frozen=True)
class StateFieldSpec:
    name: str
    description: str
    default: Any


@dataclass(frozen=True)
class ActionSpec:
    action_id: str
    description: str


@dataclass(frozen=True)
class EventTypeSpec:
    event_type: str
    description: str


@dataclass(frozen=True)
class ActorTemplate:
    actor_type: str
    default_state: dict[str, Any] = field(default_factory=dict)

