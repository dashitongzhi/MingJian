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

    async def reclaim_pending(
        self,
        topics: list[str],
        group: str,
        consumer: str,
        min_idle_ms: int = 60_000,
        count: int = 50,
    ) -> list[ConsumedEvent]: ...

    async def publish_dead_letter(self, topic: str, payload: dict[str, Any]) -> None: ...

    async def close(self) -> None: ...


class InMemoryEventBus:
    supports_stream_consumers = True

    def __init__(self) -> None:
        self._events: dict[str, list[ConsumedEvent]] = {}
        self._acked: set[str] = set()
        self._counter: int = 0

    async def publish(self, topic: str, payload: dict[str, Any]) -> None:
        self._counter += 1
        message_id = f"mem-{self._counter}"
        event = ConsumedEvent(topic=topic, message_id=message_id, payload=payload)
        self._events.setdefault(topic, []).append(event)

    async def consume(
        self,
        topics: list[str],
        group: str,
        consumer: str,
        count: int,
        block_ms: int,
    ) -> list[ConsumedEvent]:
        results: list[ConsumedEvent] = []
        for topic in topics:
            for event in self._events.get(topic, []):
                ack_key = f"{group}:{event.message_id}"
                if ack_key not in self._acked and len(results) < count:
                    results.append(event)
        return results

    async def ack(self, topic: str, group: str, message_id: str) -> None:
        self._acked.add(f"{group}:{message_id}")

    async def reclaim_pending(
        self,
        topics: list[str],
        group: str,
        consumer: str,
        min_idle_ms: int = 60_000,
        count: int = 50,
    ) -> list[ConsumedEvent]:
        return []

    async def publish_dead_letter(self, topic: str, payload: dict[str, Any]) -> None:
        await self.publish(f"{topic}.dlq", payload)

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

    async def reclaim_pending(
        self,
        topics: list[str],
        group: str,
        consumer: str,
        min_idle_ms: int = 60_000,
        count: int = 50,
    ) -> list[ConsumedEvent]:
        """Reclaim pending messages that have been idle too long."""
        if not topics:
            return []

        streams = [self._stream_key(topic) for topic in topics]
        events: list[ConsumedEvent] = []
        for stream_key in streams:
            try:
                response = await self.client.xautoclaim(
                    name=stream_key,
                    groupname=group,
                    consumername=consumer,
                    min_idle_time=min_idle_ms,
                    start_id="0-0",
                    count=count,
                )
                if response and len(response) >= 2:
                    events.extend(self._decode_messages(stream_key, response[1]))
            except redis.ResponseError:
                try:
                    start_id = "-"
                    idle_ids: list[str] = []
                    while len(idle_ids) < count:
                        pending = await self.client.xpending_range(
                            name=stream_key,
                            groupname=group,
                            min=start_id,
                            max="+",
                            count=count,
                        )
                        if not pending:
                            break
                        idle_ids.extend(
                            message_id
                            for item in pending
                            if self._pending_idle_ms(item) >= min_idle_ms
                            if (message_id := self._pending_message_id(item)) is not None
                        )
                        last_seen_id = self._pending_message_id(pending[-1])
                        if last_seen_id is None:
                            break
                        start_id = f"({last_seen_id}"
                    if not idle_ids:
                        continue
                    claimed = await self.client.xclaim(
                        name=stream_key,
                        groupname=group,
                        consumername=consumer,
                        min_idle_time=min_idle_ms,
                        message_ids=idle_ids[:count],
                    )
                    events.extend(self._decode_messages(stream_key, claimed))
                except Exception:
                    pass
        return events

    async def ack(self, topic: str, group: str, message_id: str) -> None:
        await self.client.xack(self._stream_key(topic), group, message_id)

    async def publish_dead_letter(self, topic: str, payload: dict[str, Any]) -> None:
        await self.publish(f"{topic}.dlq", payload)

    async def close(self) -> None:
        await self.client.aclose()

    def _stream_key(self, topic: str) -> str:
        return f"stream:{topic}"

    def _decode_messages(
        self,
        stream_key: str,
        messages: list[tuple[str, dict[str, str]]],
    ) -> list[ConsumedEvent]:
        topic = stream_key.removeprefix("stream:")
        events: list[ConsumedEvent] = []
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

    def _pending_message_id(self, item: object) -> str | None:
        if isinstance(item, dict):
            message_id = item.get("message_id")
            return message_id if isinstance(message_id, str) else None
        if isinstance(item, (list, tuple)) and item:
            message_id = item[0]
            return message_id if isinstance(message_id, str) else None
        return None

    def _pending_idle_ms(self, item: object) -> int:
        if isinstance(item, dict):
            value = item.get("time_since_delivered", item.get("idle_time", 0))
            return int(value or 0)
        if isinstance(item, (list, tuple)) and len(item) >= 3:
            return int(item[2] or 0)
        return 0


def build_event_bus(settings: Settings) -> EventBus:
    if settings.event_bus_backend.lower() == "redis":
        return RedisStreamEventBus(settings.redis_url, settings.stream_maxlen)
    return InMemoryEventBus()
