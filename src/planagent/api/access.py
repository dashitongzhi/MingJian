from __future__ import annotations

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from planagent.api.routes.auth import resolve_community_access
from planagent.config import get_settings


_PUBLIC_GET_PATHS = {
    "/docs",
    "/docs/oauth2-redirect",
    "/health",
    "/health/live",
    "/health/ready",
    "/openapi.json",
    "/redoc",
}
_PUBLIC_AUTH_POST_PATHS = {
    "/auth/login",
    "/auth/refresh",
    "/auth/register",
}
_BROWSER_JWT_SUBPROTOCOL = "mingjian.jwt"
_VIEWER_ACCOUNT_WRITE_PATHS = {
    "/auth/change-password",
    "/auth/logout",
}


class CommunityAccessMiddleware:
    """Apply the Community local/remote access policy to every business connection."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        scope_type = scope["type"]
        if scope_type not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return
        settings = get_settings()
        if scope_type == "http":
            limited_receive = await _receive_with_body_limit(
                scope,
                receive,
                send,
                max_body_bytes=settings.max_request_body_bytes,
            )
            if limited_receive is None:
                return
            receive = limited_receive
            send = _auth_no_store_send(scope, send)
        if scope_type == "http" and _is_public_request(
            scope,
            expose_auth_routes=settings.remote_access_enabled,
        ):
            await self.app(scope, receive, send)
            return

        authorization = _scope_authorization(scope)
        selected_subprotocol: str | None = None
        if scope_type == "websocket" and settings.remote_access_enabled and authorization is None:
            authorization, selected_subprotocol = _scope_browser_authorization(scope)

        try:
            payload = resolve_community_access(
                scope["app"],
                authorization,
                client_host=_scope_client_host(scope),
                local_proxy_credential=_scope_header(scope, b"x-mingjian-local-proxy"),
            )
        except HTTPException as exc:
            if scope_type == "websocket":
                await send(
                    {
                        "type": "websocket.close",
                        "code": 1008,
                        "reason": str(exc.detail),
                    }
                )
                return
            response = JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
                headers=exc.headers,
            )
            await response(scope, receive, send)
            return

        state = scope.setdefault("state", {})
        state["community_access_payload"] = payload
        if selected_subprotocol is not None:
            state["community_websocket_subprotocol"] = selected_subprotocol
        if scope_type == "http" and _is_forbidden_viewer_write(scope, payload):
            response = JSONResponse(
                status_code=403,
                content={"detail": "Viewer role is read-only"},
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


def _auth_no_store_send(scope: Scope, send: Send) -> Send:
    if not _canonical_path(str(scope.get("path", ""))).startswith("/auth/"):
        return send

    async def send_with_no_store(message: Message) -> None:
        if message["type"] == "http.response.start":
            headers: list[tuple[bytes, bytes]] = list(message.get("headers", []))
            headers = [
                (name, value)
                for name, value in headers
                if name.lower() not in {b"cache-control", b"pragma"}
            ]
            headers.extend(
                [
                    (b"cache-control", b"no-store"),
                    (b"pragma", b"no-cache"),
                ]
            )
            message = {**message, "headers": headers}
        await send(message)

    return send_with_no_store


async def _receive_with_body_limit(
    scope: Scope,
    receive: Receive,
    send: Send,
    *,
    max_body_bytes: int,
) -> Receive | None:
    """Buffer at most the configured body limit and replay it to the application."""
    content_length = _scope_header(scope, b"content-length")
    if content_length is not None:
        try:
            if int(content_length) > max_body_bytes:
                await _send_body_too_large(scope, receive, send)
                return None
        except ValueError:
            pass

    body = bytearray()
    while True:
        message = await receive()
        if message["type"] == "http.disconnect":
            replay_message = message
            break
        chunk = message.get("body", b"")
        body.extend(chunk)
        if len(body) > max_body_bytes:
            await _send_body_too_large(scope, receive, send)
            return None
        if not message.get("more_body", False):
            replay_message = {"type": "http.request", "body": bytes(body), "more_body": False}
            break

    replayed = False

    async def replay_receive() -> Message:
        nonlocal replayed
        if not replayed:
            replayed = True
            return replay_message
        return await receive()

    return replay_receive


async def _send_body_too_large(scope: Scope, receive: Receive, send: Send) -> None:
    response = JSONResponse(
        status_code=413,
        content={"detail": "Request body too large"},
    )
    await response(scope, receive, send)


def _is_public_request(scope: Scope, *, expose_auth_routes: bool) -> bool:
    method = str(scope.get("method", "")).upper()
    if method == "OPTIONS":
        return True

    path = _canonical_path(str(scope.get("path", "")))
    if method in {"GET", "HEAD"} and path in _PUBLIC_GET_PATHS:
        return True
    return expose_auth_routes and method == "POST" and path in _PUBLIC_AUTH_POST_PATHS


def _canonical_path(path: str) -> str:
    if path == "/api":
        return "/"
    if path.startswith("/api/"):
        return path[4:]
    return path


def _is_forbidden_viewer_write(scope: Scope, payload: dict[str, object]) -> bool:
    """Keep viewer sessions read-only while allowing their own account maintenance."""
    if payload.get("role") != "viewer":
        return False
    method = str(scope.get("method", "")).upper()
    if method in {"GET", "HEAD", "OPTIONS"}:
        return False
    return _canonical_path(str(scope.get("path", ""))) not in _VIEWER_ACCOUNT_WRITE_PATHS


def _scope_authorization(scope: Scope) -> str | None:
    return _scope_header(scope, b"authorization")


def _scope_browser_authorization(scope: Scope) -> tuple[str | None, str | None]:
    """Extract a browser JWT offered after the safe MingJian protocol marker."""
    raw_protocols = _scope_header(scope, b"sec-websocket-protocol")
    if raw_protocols is None:
        return None, None
    protocols = [item.strip() for item in raw_protocols.split(",") if item.strip()]
    for index, protocol in enumerate(protocols[:-1]):
        if protocol == _BROWSER_JWT_SUBPROTOCOL:
            return f"Bearer {protocols[index + 1]}", _BROWSER_JWT_SUBPROTOCOL
    return None, None


def _scope_header(scope: Scope, header_name: bytes) -> str | None:
    for key, value in scope.get("headers", []):
        if key.lower() == header_name:
            return value.decode("latin-1")
    return None


def _scope_client_host(scope: Scope) -> str | None:
    client = scope.get("client")
    if not client:
        return None
    return str(client[0])
