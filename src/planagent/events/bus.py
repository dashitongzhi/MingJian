from __future__ import annotations

import json
from typing import Any, Protocol

import redis.asyncio as redis

from planagent.config import Settings


class EventBus(Protocol):
    async def publish(self, topic: str, payload: dict[str, Any]) -> None: ...

    async def close(self) -> None: ...


class InMemoryEventBus:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def publish(self, topic: str, payload: dict[str, Any]) -> None:
        self.events.append({"topic": topic, "payload": payload})

    async def close(self) -> None:
        return None


class RedisStreamEventBus:
    def __init__(self, redis_url: str, maxlen: int) -> None:
        self.client = redis.from_url(redis_url, decode_responses=True)
        self.maxlen = maxlen

    async def publish(self, topic: str, payload: dict[str, Any]) -> None:
        await self.client.xadd(
            f"stream:{topic}",
            {"payload": json.dumps(payload, ensure_ascii=True)},
            maxlen=self.maxlen,
            approximate=True,
        )

    async def close(self) -> None:
        await self.client.aclose()


def build_event_bus(settings: Settings) -> EventBus:
    if settings.event_bus_backend.lower() == "redis":
        return RedisStreamEventBus(settings.redis_url, settings.stream_maxlen)
    return InMemoryEventBus()
