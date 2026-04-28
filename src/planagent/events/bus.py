from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Protocol

import redis.asyncio as redis

from planagent.config import Settings


@dataclass(frozen=True)
class ConsumedEvent:
    topic: str
    message_id: str
    payload: dict[str, Any]


class EventBus(Protocol):
    async def publish(self, topic: str, payload: dict[str, Any]) -> None: ...

    async def consume(
        self,
        topics: list[str],
        group: str,
        consumer: str,
        count: int,
        block_ms: int,
    ) -> list[ConsumedEvent]: ...

    async def ack(self, topic: str, group: str, message_id: str) -> None: ...

    async def publish_dead_letter(self, topic: str, payload: dict[str, Any]) -> None: ...

    async def close(self) -> None: ...


class InMemoryEventBus:
    supports_stream_consumers = False

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def publish(self, topic: str, payload: dict[str, Any]) -> None:
        self.events.append({"topic": topic, "payload": payload})

    async def consume(
        self,
        topics: list[str],
        group: str,
        consumer: str,
        count: int,
        block_ms: int,
    ) -> list[ConsumedEvent]:
        return []

    async def ack(self, topic: str, group: str, message_id: str) -> None:
        return None

    async def publish_dead_letter(self, topic: str, payload: dict[str, Any]) -> None:
        self.events.append({"topic": f"{topic}.dlq", "payload": payload})

    async def close(self) -> None:
        return None


class RedisStreamEventBus:
    supports_stream_consumers = True

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

    async def consume(
        self,
        topics: list[str],
        group: str,
        consumer: str,
        count: int,
        block_ms: int,
    ) -> list[ConsumedEvent]:
        if not topics:
            return []

        streams = [self._stream_key(topic) for topic in topics]
        for stream_key in streams:
            try:
                await self.client.xgroup_create(
                    name=stream_key,
                    groupname=group,
                    id="0",
                    mkstream=True,
                )
            except redis.ResponseError as exc:
                if "BUSYGROUP" not in str(exc):
                    raise

        response = await self.client.xreadgroup(
            groupname=group,
            consumername=consumer,
            streams={stream_key: ">" for stream_key in streams},
            count=count,
            block=block_ms,
        )
        events: list[ConsumedEvent] = []
        for stream_key, messages in response:
            topic = stream_key.removeprefix("stream:")
            for message_id, fields in messages:
                raw_payload = fields.get("payload", "{}")
                payload = json.loads(raw_payload) if isinstance(raw_payload, str) else {}
                events.append(
                    ConsumedEvent(
                        topic=topic,
                        message_id=message_id,
                        payload=payload if isinstance(payload, dict) else {},
                    )
                )
        return events

    async def ack(self, topic: str, group: str, message_id: str) -> None:
        await self.client.xack(self._stream_key(topic), group, message_id)

    async def publish_dead_letter(self, topic: str, payload: dict[str, Any]) -> None:
        await self.publish(f"{topic}.dlq", payload)

    async def close(self) -> None:
        await self.client.aclose()

    def _stream_key(self, topic: str) -> str:
        return f"stream:{topic}"


def build_event_bus(settings: Settings) -> EventBus:
    if settings.event_bus_backend.lower() == "redis":
        return RedisStreamEventBus(settings.redis_url, settings.stream_maxlen)
    return InMemoryEventBus()
