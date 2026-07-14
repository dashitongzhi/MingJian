from __future__ import annotations

from urllib.parse import parse_qs

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

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


class CommunityAccessMiddleware:
    """Apply the Community local/remote access policy to every business connection."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        scope_type = scope["type"]
        if scope_type not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return
        if scope_type == "http" and _is_public_request(
            scope,
            expose_auth_routes=get_settings().remote_access_enabled,
        ):
            await self.app(scope, receive, send)
            return

        try:
            payload = resolve_community_access(
                scope["app"],
                _scope_authorization(scope),
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

        scope.setdefault("state", {})["community_access_payload"] = payload
        await self.app(scope, receive, send)


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


def _scope_authorization(scope: Scope) -> str | None:
    authorization = _scope_header(scope, b"authorization")
    if authorization:
        return authorization

    if scope["type"] == "websocket":
        query = parse_qs(scope.get("query_string", b"").decode("utf-8", errors="ignore"))
        token = query.get("token", [""])[0]
        if token:
            return f"Bearer {token}"
    return None


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
