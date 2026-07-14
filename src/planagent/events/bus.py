from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import uuid
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

    async def refresh_backpressure(
        self,
        *,
        topics: list[str],
        group: str,
        pending_threshold: int,
        ttl_seconds: int = 60,
    ) -> dict[str, object]: ...

    async def close(self) -> None: ...


def build_event_envelope(
    topic: str,
    payload: dict[str, Any],
    *,
    attempt: int | None = None,
) -> dict[str, Any]:
    """Attach the common stream contract without replacing caller payload fields."""
    enriched = dict(payload)
    now = datetime.now(timezone.utc).isoformat()
    raw_metadata = enriched.get("_worker")
    metadata: dict[str, Any] = raw_metadata if isinstance(raw_metadata, dict) else {}
    resolved_attempt = _resolve_attempt(enriched, metadata, attempt)
    session_id = _first_present(
        enriched,
        "session_id",
        "strategic_session_id",
        "run_id",
        "simulation_run_id",
    )
    tenant_id = _first_present(enriched, "tenant_id")
    workspace_id = _first_present(enriched, "workspace_id")
    provided_correlation_id = _first_present(enriched, "correlation_id", "request_id")
    correlation_id = provided_correlation_id or str(uuid.uuid4())
    idempotency_key = enriched.get("idempotency_key")
    if not isinstance(idempotency_key, str) or not idempotency_key.strip():
        idempotency_key = _build_idempotency_key(
            topic, enriched, session_id, provided_correlation_id
        )

    enriched.setdefault("event_id", str(uuid.uuid4()))
    enriched.setdefault("correlation_id", correlation_id)
    enriched.setdefault("session_id", session_id)
    enriched.setdefault("edition", _edition_from_payload(enriched))
    enriched.setdefault("tenant_id", tenant_id)
    enriched.setdefault("workspace_id", workspace_id)
    if attempt is not None or "attempts" in metadata or "attempts" in enriched:
        enriched["attempt"] = resolved_attempt
    else:
        enriched.setdefault("attempt", resolved_attempt)
    enriched.setdefault("created_at", now)
    enriched.setdefault("idempotency_key", idempotency_key)
    return enriched


class InMemoryEventBus:
    supports_stream_consumers = True

    def __init__(self) -> None:
        self._events: dict[str, list[ConsumedEvent]] = {}
        self._acked: set[str] = set()
        self._counter: int = 0
        self._backpressure_active: bool = False
        self._backpressure_reason: str | None = None

    async def publish(self, topic: str, payload: dict[str, Any]) -> None:
        self._counter += 1
        message_id = f"mem-{self._counter}"
        event = ConsumedEvent(
            topic=topic,
            message_id=message_id,
            payload=build_event_envelope(topic, payload),
        )
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

    async def pending_count(self, topics: list[str], group: str) -> int:
        total = 0
        for topic in topics:
            for event in self._events.get(topic, []):
                if f"{group}:{event.message_id}" not in self._acked:
                    total += 1
        return total

    async def refresh_backpressure(
        self,
        *,
        topics: list[str],
        group: str,
        pending_threshold: int,
        ttl_seconds: int = 60,
    ) -> dict[str, object]:
        pending = await self.pending_count(topics, group)
        active = pending > pending_threshold
        reason = (
            f"pending={pending} exceeded threshold={pending_threshold} for group={group}"
            if active
            else "pending work is below threshold"
        )
        await self.set_backpressure_signal(active, reason, ttl_seconds=ttl_seconds)
        return {"active": active, "reason": reason if active else None, "pending": pending}

    async def set_backpressure_signal(
        self,
        active: bool,
        reason: str,
        ttl_seconds: int = 60,
    ) -> None:
        self._backpressure_active = active
        self._backpressure_reason = reason if active else None

    async def is_backpressure_active(self) -> bool:
        return self._backpressure_active

    async def backpressure_status(self) -> dict[str, object]:
        return {
            "active": self._backpressure_active,
            "reason": self._backpressure_reason,
        }

    async def close(self) -> None:
        return None


class RedisStreamEventBus:
    supports_stream_consumers = True

    def __init__(self, redis_url: str, maxlen: int) -> None:
        self.client = redis.from_url(redis_url, decode_responses=True)
        self.maxlen = maxlen

    async def publish(self, topic: str, payload: dict[str, Any]) -> None:
        enriched = build_event_envelope(topic, payload)
        await self.client.xadd(
            f"stream:{topic}",
            {"payload": json.dumps(enriched, ensure_ascii=True)},
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

    async def pending_count(self, topics: list[str], group: str) -> int:
        total = 0
        for topic in topics:
            stream_key = self._stream_key(topic)
            pending = 0
            try:
                summary = await self.client.xpending(stream_key, group)
            except redis.ResponseError as exc:
                if "NOGROUP" in str(exc):
                    total += int(await self.client.xlen(stream_key) or 0)
                    continue
                raise
            if isinstance(summary, dict):
                pending = int(summary.get("pending", 0) or 0)
            elif isinstance(summary, (list, tuple)) and summary:
                pending = int(summary[0] or 0)
            total += pending + await self._group_lag(stream_key, group)
        return total

    async def _group_lag(self, stream_key: str, group: str) -> int:
        try:
            groups = await self.client.xinfo_groups(stream_key)
        except redis.ResponseError:
            return 0
        for item in groups:
            name = item.get("name") if isinstance(item, dict) else None
            if name != group:
                continue
            try:
                return max(0, int(item.get("lag") or 0))
            except (TypeError, ValueError):
                return 0
        return 0

    async def refresh_backpressure(
        self,
        *,
        topics: list[str],
        group: str,
        pending_threshold: int,
        ttl_seconds: int = 60,
    ) -> dict[str, object]:
        pending = await self.pending_count(topics, group)
        active = pending > pending_threshold
        reason = (
            f"pending={pending} exceeded threshold={pending_threshold} for group={group}"
            if active
            else "pending work is below threshold"
        )
        await self.set_backpressure_signal(active, reason, ttl_seconds=ttl_seconds)
        return {"active": active, "reason": reason if active else None, "pending": pending}

    async def set_backpressure_signal(
        self,
        active: bool,
        reason: str,
        ttl_seconds: int = 60,
    ) -> None:
        key = "signal:backpressure"
        if active:
            await self.client.set(
                key,
                json.dumps({"active": True, "reason": reason}, ensure_ascii=True),
                ex=max(1, ttl_seconds),
            )
            return
        await self.client.delete(key)

    async def is_backpressure_active(self) -> bool:
        raw = await self.client.get("signal:backpressure")
        if not raw:
            return False
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return True
        return bool(payload.get("active", True)) if isinstance(payload, dict) else True

    async def backpressure_status(self) -> dict[str, object]:
        raw = await self.client.get("signal:backpressure")
        if not raw:
            return {"active": False, "reason": None}
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return {"active": True, "reason": "unparseable backpressure signal"}
        if not isinstance(payload, dict):
            return {"active": True, "reason": "invalid backpressure signal"}
        return {
            "active": bool(payload.get("active", True)),
            "reason": payload.get("reason"),
        }

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


def _first_present(payload: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _edition_from_payload(payload: dict[str, Any]) -> str:
    edition = payload.get("edition")
    if isinstance(edition, str) and edition.strip():
        return edition.strip().lower()
    if payload.get("license_id") or payload.get("policy_id"):
        return "enterprise"
    if payload.get("workspace_id") or payload.get("subscription_id"):
        return "cloud"
    return "community"


def _build_idempotency_key(
    topic: str,
    payload: dict[str, Any],
    session_id: str | None,
    correlation_id: str | None,
) -> str:
    explicit_source = _first_present(payload, "source_id", "provider", "source")
    explicit_item = _first_present(payload, "item_hash", "raw_item_id", "evidence_id", "claim_id")
    if explicit_source and explicit_item:
        return f"{explicit_source}:{explicit_item}"
    stable_payload = {
        key: value
        for key, value in payload.items()
        if key not in {"event_id", "created_at", "attempt", "_worker"}
    }
    raw = json.dumps(stable_payload, sort_keys=True, default=str, ensure_ascii=True)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    scope = session_id or correlation_id or "global"
    return f"{topic}:{scope}:{digest}"


def _resolve_attempt(
    payload: dict[str, Any],
    metadata: dict[str, Any],
    explicit_attempt: int | None,
) -> int:
    for candidate in (explicit_attempt, metadata.get("attempts"), payload.get("attempts"), 1):
        if candidate is None or candidate == "":
            continue
        try:
            return max(1, int(candidate))
        except (TypeError, ValueError):
            continue
    return 1
