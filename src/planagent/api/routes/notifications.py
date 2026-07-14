"""Notification API routes — WebSocket and REST notification endpoints."""

from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import APIRouter, Query, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field

from planagent.services.notification import (
    NotificationChannel,
    NotificationConfig,
    NotificationPriority,
    NotificationService,
)

router = APIRouter(prefix="/notifications", tags=["Notifications"])


# ── Request Models ────────────────────────────────────────────


class SendNotificationRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    user_id: str
    title: str
    body: str
    channel: Literal["websocket", "email", "webhook"] = "websocket"
    priority: Literal["low", "normal", "high", "critical"] = "normal"
    metadata: dict[str, Any] = Field(default_factory=dict)


class BroadcastRequest(BaseModel):
    title: str
    body: str
    priority: Literal["low", "normal", "high", "critical"] = "normal"


# ── Dependency ────────────────────────────────────────────────


def _get_notification_service(request: Request) -> NotificationService:
    if not hasattr(request.app.state, "notification_service"):
        from planagent.config import get_settings

        settings = get_settings()
        config = NotificationConfig(
            smtp_host=getattr(settings, "smtp_host", None),
            smtp_port=getattr(settings, "smtp_port", 587),
            smtp_user=getattr(settings, "smtp_user", None),
            smtp_password=getattr(settings, "smtp_password", None),
            smtp_from=getattr(settings, "smtp_from", "planagent@localhost"),
            webhook_urls=getattr(settings, "webhook_urls", []),
        )
        request.app.state.notification_service = NotificationService(config)
    return request.app.state.notification_service  # type: ignore[no-any-return]  # app.state 动态属性


# ── REST Endpoints ────────────────────────────────────────────


@router.post("/send")
async def send_notification(
    body: SendNotificationRequest,
    request: Request,
) -> dict[str, Any]:
    """Send a notification to a specific user."""
    service = _get_notification_service(request)
    notif = await service.notify(
        user_id=body.user_id,
        title=body.title,
        body=body.body,
        channel=NotificationChannel(body.channel),
        priority=NotificationPriority(body.priority),
        metadata=body.metadata,
    )
    return {
        "id": notif.id,
        "delivered": notif.delivered,
        "error": notif.error,
    }


@router.post("/broadcast")
async def broadcast_notification(
    body: BroadcastRequest,
    request: Request,
) -> dict[str, Any]:
    """Broadcast a notification to all connected WebSocket users."""
    service = _get_notification_service(request)
    count = await service.broadcast(
        title=body.title,
        body=body.body,
        priority=NotificationPriority(body.priority),
    )
    return {"broadcast_to": count}


@router.get("/history/{user_id}")
async def get_notification_history(
    user_id: str,
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[dict[str, Any]]:
    """Get notification history for a user."""
    service = _get_notification_service(request)
    notifications = service.get_notifications(user_id, limit=limit)
    return [
        {
            "id": n.id,
            "title": n.title,
            "body": n.body,
            "channel": n.channel.value,
            "priority": n.priority.value,
            "delivered": n.delivered,
            "delivered_at": n.delivered_at.isoformat() if n.delivered_at else None,
            "error": n.error,
            "created_at": n.created_at.isoformat(),
            "metadata": n.metadata,
        }
        for n in notifications
    ]


@router.get("/stats")
async def get_notification_stats(request: Request) -> dict[str, Any]:
    """Get notification system statistics."""
    service = _get_notification_service(request)
    return service.get_stats()


# ── WebSocket Endpoint ────────────────────────────────────────


@router.websocket("/ws/{user_id}")
async def notification_websocket(
    websocket: WebSocket,
    user_id: str,
) -> None:
    """WebSocket endpoint for real-time notifications.

    Connect to ws://host:port/notifications/ws/{user_id}
    to receive real-time push notifications.
    """
    if not websocket.scope.get("state", {}).get("community_access_payload"):
        await websocket.close(code=1008)
        return
    await websocket.accept()

    # Get notification service from app state
    app = websocket.scope.get("app")
    if app and hasattr(app.state, "notification_service"):
        service = app.state.notification_service
    else:
        service = NotificationService(NotificationConfig())

    service.register_ws(user_id, websocket)

    try:
        while True:
            # Keep connection alive, handle incoming messages
            data = await websocket.receive_text()
            # Client can send ack or ping
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        service.unregister_ws(user_id, websocket)
    except Exception:
        service.unregister_ws(user_id, websocket)
