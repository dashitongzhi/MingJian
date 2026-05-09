"""Notification service — push updates to users via WebSocket / Email / Webhook.

Addresses the audit gap: WatchRule detects changes but cannot notify users.
This service provides a unified notification dispatch layer.
"""

from __future__ import annotations

import asyncio
import json
import logging
import smtplib
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from enum import StrEnum
from html import escape as html_escape
from typing import Any

import httpx

from planagent.domain.models import utc_now

_logger = logging.getLogger(__name__)


class NotificationChannel(StrEnum):
    WEBSOCKET = "websocket"
    EMAIL = "email"
    WEBHOOK = "webhook"


class NotificationPriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Notification:
    id: str
    user_id: str
    title: str
    body: str
    channel: NotificationChannel
    priority: NotificationPriority = NotificationPriority.NORMAL
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)
    delivered: bool = False
    delivered_at: datetime | None = None
    error: str | None = None


@dataclass
class NotificationConfig:
    """Configuration for notification dispatch."""

    # Email (SMTP)
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str = "planagent@localhost"
    smtp_tls: bool = True

    # Webhook
    webhook_urls: list[str] = field(default_factory=list)
    webhook_timeout: int = 10

    # WebSocket
    ws_enabled: bool = True


class NotificationService:
    """Dispatches notifications to users via multiple channels.

    Used by WatchIngestWorker when significant changes are detected,
    and by the debate system when verdicts are reached.
    """

    def __init__(self, config: NotificationConfig | None = None) -> None:
        self.config = config or NotificationConfig()
        self._ws_connections: dict[str, list[Any]] = {}  # user_id -> [websocket connections]
        self._notification_log: deque[Notification] = deque(maxlen=10000)  # Bounded log
        self._http_client: httpx.AsyncClient | None = None

    async def _get_http_client(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=self.config.webhook_timeout)
        return self._http_client

    async def close(self) -> None:
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()

    # ── Registration ──────────────────────────────────────────

    def register_ws(self, user_id: str, websocket: Any) -> None:
        """Register a WebSocket connection for a user."""
        if user_id not in self._ws_connections:
            self._ws_connections[user_id] = []
        self._ws_connections[user_id].append(websocket)
        _logger.info(
            "WebSocket registered for user %s (total: %d)",
            user_id,
            len(self._ws_connections[user_id]),
        )

    def unregister_ws(self, user_id: str, websocket: Any) -> None:
        """Unregister a WebSocket connection."""
        if user_id in self._ws_connections:
            self._ws_connections[user_id] = [
                ws for ws in self._ws_connections[user_id] if ws is not websocket
            ]
            if not self._ws_connections[user_id]:
                del self._ws_connections[user_id]

    # ── Dispatch ──────────────────────────────────────────────

    async def notify(
        self,
        user_id: str,
        title: str,
        body: str,
        channel: NotificationChannel = NotificationChannel.WEBSOCKET,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        metadata: dict[str, Any] | None = None,
    ) -> Notification:
        """Send a notification to a user via the specified channel."""
        import uuid

        notif = Notification(
            id=str(uuid.uuid4()),
            user_id=user_id,
            title=title,
            body=body,
            channel=channel,
            priority=priority,
            metadata=metadata or {},
        )

        try:
            if channel == NotificationChannel.WEBSOCKET:
                await self._send_websocket(notif)
            elif channel == NotificationChannel.EMAIL:
                await self._send_email(notif)
            elif channel == NotificationChannel.WEBHOOK:
                await self._send_webhook(notif)
            notif.delivered = True
            notif.delivered_at = utc_now()
        except Exception as exc:
            notif.error = str(exc)
            _logger.exception("Failed to deliver notification %s via %s", notif.id, channel)

        self._notification_log.append(notif)
        return notif

    async def notify_all_channels(
        self,
        user_id: str,
        title: str,
        body: str,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        metadata: dict[str, Any] | None = None,
    ) -> list[Notification]:
        """Send notification via all configured channels."""
        results = []
        if self.config.ws_enabled:
            results.append(
                await self.notify(
                    user_id, title, body, NotificationChannel.WEBSOCKET, priority, metadata
                )
            )
        if self.config.smtp_host:
            results.append(
                await self.notify(
                    user_id, title, body, NotificationChannel.EMAIL, priority, metadata
                )
            )
        if self.config.webhook_urls:
            results.append(
                await self.notify(
                    user_id, title, body, NotificationChannel.WEBHOOK, priority, metadata
                )
            )
        return results

    async def broadcast(
        self,
        title: str,
        body: str,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """Broadcast to all connected WebSocket users. Returns count of notified users."""
        count = 0
        for user_id in list(self._ws_connections.keys()):
            await self.notify(
                user_id, title, body, NotificationChannel.WEBSOCKET, priority, metadata
            )
            count += 1
        return count

    # ── Channel Implementations ───────────────────────────────

    async def _send_websocket(self, notif: Notification) -> None:
        """Send via WebSocket to all connections for this user."""
        connections = self._ws_connections.get(notif.user_id, [])
        if not connections:
            _logger.debug("No WebSocket connections for user %s", notif.user_id)
            raise RuntimeError(f"No WebSocket connections for user {notif.user_id}")

        payload = json.dumps(
            {
                "type": "notification",
                "id": notif.id,
                "title": notif.title,
                "body": notif.body,
                "priority": notif.priority.value,
                "metadata": notif.metadata,
                "created_at": notif.created_at.isoformat(),
            },
            ensure_ascii=False,
        )

        dead = []
        for ws in connections:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)

        # Clean up dead connections
        for ws in dead:
            self._ws_connections[notif.user_id].remove(ws)

    async def _send_email(self, notif: Notification) -> None:
        """Send via SMTP email."""
        if not self.config.smtp_host:
            raise RuntimeError("SMTP not configured")

        # Use asyncio to avoid blocking
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._send_email_sync, notif)

    def _send_email_sync(self, notif: Notification) -> None:
        """Synchronous email send (runs in executor)."""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[PlanAgent] {notif.title}"
        msg["From"] = self.config.smtp_from
        msg["To"] = notif.user_id  # user_id should be email for email channel

        # Plain text
        text_part = MIMEText(notif.body, "plain", "utf-8")
        msg.attach(text_part)

        # HTML (escape user input to prevent XSS)
        safe_title = html_escape(notif.title)
        safe_body = html_escape(notif.body).replace("\n", "<br>")
        html_body = f"""
        <html>
        <body style="font-family: -apple-system, BlinkMacSystemFont, sans-serif; padding: 20px;">
            <h2 style="color: #1a1a2e;">{safe_title}</h2>
            <div style="padding: 15px; background: #f5f5f5; border-radius: 8px; margin: 10px 0;">
                {safe_body}
            </div>
            <p style="color: #666; font-size: 12px;">
                Sent by PlanAgent at {notif.created_at.isoformat()}<br>
                Priority: {notif.priority.value}
            </p>
        </body>
        </html>
        """
        html_part = MIMEText(html_body, "html", "utf-8")
        msg.attach(html_part)

        with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port) as server:
            if self.config.smtp_tls:
                server.starttls()
            if self.config.smtp_user and self.config.smtp_password:
                server.login(self.config.smtp_user, self.config.smtp_password)
            server.send_message(msg)

    async def _send_webhook(self, notif: Notification) -> None:
        """Send via HTTP webhook."""
        if not self.config.webhook_urls:
            raise RuntimeError("No webhook URLs configured")

        client = await self._get_http_client()
        payload = {
            "event": "notification",
            "id": notif.id,
            "user_id": notif.user_id,
            "title": notif.title,
            "body": notif.body,
            "priority": notif.priority.value,
            "metadata": notif.metadata,
            "created_at": notif.created_at.isoformat(),
        }

        errors = []
        for url in self.config.webhook_urls:
            try:
                resp = await client.post(url, json=payload)
                if resp.status_code >= 400:
                    errors.append(f"{url}: HTTP {resp.status_code}")
            except Exception as exc:
                errors.append(f"{url}: {exc}")

        if errors and len(errors) == len(self.config.webhook_urls):
            raise RuntimeError(f"All webhooks failed: {'; '.join(errors)}")

    # ── Query ─────────────────────────────────────────────────

    def get_notifications(
        self,
        user_id: str,
        limit: int = 50,
        undelivered_only: bool = False,
    ) -> list[Notification]:
        """Get notification history for a user."""
        results = [
            n
            for n in self._notification_log
            if n.user_id == user_id and (not undelivered_only or not n.delivered)
        ]
        return results[-limit:]

    def get_stats(self) -> dict[str, Any]:
        """Get notification statistics."""
        total = len(self._notification_log)
        delivered = sum(1 for n in self._notification_log if n.delivered)
        failed = sum(1 for n in self._notification_log if n.error)
        return {
            "total": total,
            "delivered": delivered,
            "failed": failed,
            "ws_connections": {uid: len(conns) for uid, conns in self._ws_connections.items()},
        }
