from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from planagent.db import get_database
from planagent.domain.enums import EventTopic
from planagent.domain.models import StrategicRunSnapshot
from planagent.events.bus import ConsumedEvent, EventBus


router = APIRouter()

NOTIFICATION_TOPICS = [
    EventTopic.SOURCE_CHANGED.value,
    EventTopic.DEBATE_COMPLETED.value,
    EventTopic.PREDICTION_VERSION_CREATED.value,
    EventTopic.SIMULATION_COMPLETED.value,
    "session.updated",
]


def _string_value(value: object) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    return str(value)


def _event_significance(event: ConsumedEvent) -> str:
    significance = event.payload.get("significance") or event.payload.get("severity")
    if isinstance(significance, str):
        return significance.lower()
    return "high"


async def _session_id_from_payload(payload: dict[str, Any]) -> str:
    session_id = _string_value(payload.get("session_id"))
    if session_id:
        return session_id

    debate_id = _string_value(payload.get("debate_id"))
    run_id = _string_value(payload.get("run_id"))
    if not debate_id and not run_id:
        return ""

    try:
        async with get_database().session() as session:
            query = select(StrategicRunSnapshot.session_id).order_by(
                StrategicRunSnapshot.generated_at.desc()
            )
            if debate_id:
                query = query.where(StrategicRunSnapshot.debate_id == debate_id)
            else:
                query = query.where(StrategicRunSnapshot.simulation_run_id == run_id)
            resolved = await session.scalar(query.limit(1))
            return resolved or ""
    except Exception:
        return ""


async def _notification_for_event(event: ConsumedEvent) -> dict[str, str] | None:
    severity = _event_significance(event)
    if severity != "high":
        return None

    payload = event.payload
    session_id = await _session_id_from_payload(payload)

    action_url = ""

    if event.topic == EventTopic.SOURCE_CHANGED.value:
        source_type = _string_value(payload.get("source_type")) or "source"
        title = "High-significance source change"
        body = f"{source_type} source changed and may require review."
        if session_id:
            action_url = f"/assistant?session={session_id}"
    elif event.topic == EventTopic.DEBATE_COMPLETED.value:
        debate_id = _string_value(payload.get("debate_id"))
        verdict = _string_value(payload.get("verdict")) or "completed"
        confidence = payload.get("confidence")
        confidence_text = (
            f" with {round(float(confidence) * 100)}% confidence"
            if isinstance(confidence, (int, float))
            else ""
        )
        title = "Debate completed"
        body = f"Debate verdict: {verdict}{confidence_text}."
        if debate_id:
            action_url = f"/debate?id={debate_id}"
        elif session_id:
            action_url = f"/assistant?session={session_id}"
    elif event.topic == EventTopic.PREDICTION_VERSION_CREATED.value:
        version_number = _string_value(payload.get("version_number"))
        title = "Prediction updated"
        body = (
            f"Prediction version {version_number} was created."
            if version_number
            else "A new prediction version was created."
        )
        if session_id:
            action_url = f"/assistant?session={session_id}"
    elif event.topic == EventTopic.SIMULATION_COMPLETED.value:
        run_id = _string_value(payload.get("simulation_run_id"))
        scenario = _string_value(payload.get("scenario_name"))
        title = "Simulation completed"
        body = f"Simulation {scenario + ' ' if scenario else ''}has completed." if run_id else "A simulation has completed."
        if session_id:
            action_url = f"/assistant?session={session_id}"
    elif event.topic == "session.updated":
        title = "Session updated"
        body = _string_value(payload.get("message")) or "Your session has been updated."
        if session_id:
            action_url = f"/assistant?session={session_id}"
    else:
        return None

    return {
        "type": "notification",
        "title": title,
        "body": body,
        "severity": severity,
        "session_id": session_id,
        "action_url": action_url,
    }


class NotificationManager:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._listen_task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, event_bus: EventBus) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)
            if self._listen_task is None or self._listen_task.done():
                self._listen_task = asyncio.create_task(self._listen(event_bus))

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(websocket)
            if not self._connections and self._listen_task is not None:
                self._listen_task.cancel()
                with suppress(asyncio.CancelledError):
                    await self._listen_task
                self._listen_task = None

    async def broadcast(self, message: dict[str, str]) -> None:
        async with self._lock:
            connections = list(self._connections)

        disconnected: list[WebSocket] = []
        for websocket in connections:
            try:
                await websocket.send_json(message)
            except Exception:
                disconnected.append(websocket)

        if disconnected:
            async with self._lock:
                for websocket in disconnected:
                    self._connections.discard(websocket)

    async def _listen(self, event_bus: EventBus) -> None:
        group = "notification-push"
        consumer = "websocket-notifications"
        while True:
            events = await event_bus.consume(
                NOTIFICATION_TOPICS,
                group=group,
                consumer=consumer,
                count=25,
                block_ms=5_000,
            )
            if not events:
                await asyncio.sleep(0.2)
                continue

            for event in events:
                notification = await _notification_for_event(event)
                if notification is not None:
                    await self.broadcast(notification)
                await event_bus.ack(event.topic, group, event.message_id)


notification_manager = NotificationManager()


@router.websocket("/ws/notifications")
async def notifications_websocket(websocket: WebSocket) -> None:
    await notification_manager.connect(websocket, websocket.app.state.event_bus)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await notification_manager.disconnect(websocket)
