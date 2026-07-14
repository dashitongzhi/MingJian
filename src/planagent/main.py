from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

import planagent.simulation  # noqa: F401
from planagent.api.routes import router
from planagent.api.access import CommunityAccessMiddleware
from planagent.api.routes.ws import router as websocket_router
from planagent.config import get_settings
from planagent.db import get_database
from planagent.events.bus import build_event_bus
from planagent.services.openai_client import OpenAIService
from planagent.services.auth import AuthService, AuthConfig
from planagent.services.notification import NotificationService, NotificationConfig
from planagent.services.export import ExportService
from planagent.simulation.rules import get_rule_registry
from planagent.api.routes.auth import get_community_access_payload


def create_app() -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database = get_database()
        await database.init_models()
        app.state.event_bus = build_event_bus(settings)
        app.state.rule_registry = get_rule_registry(settings.rules_dir)
        app.state.openai_service = OpenAIService(settings)

        # Auth service — 使用结构化子模型访问
        auth_config = AuthConfig(
            secret_key=settings.auth.secret_key,
            database_url=settings.db.url,
            environment=settings.env,
            default_admin_password=settings.bootstrap_admin_password or None,
        )
        app.state.auth_service = AuthService(auth_config)

        # Notification service
        notif_config = NotificationConfig(
            smtp_host=getattr(settings, "smtp_host", None),
            smtp_port=getattr(settings, "smtp_port", 587),
            smtp_user=getattr(settings, "smtp_user", None),
            smtp_password=getattr(settings, "smtp_password", None),
            webhook_urls=getattr(settings, "webhook_urls", []),
        )
        app.state.notification_service = NotificationService(notif_config)

        # Export service
        app.state.export_service = ExportService(output_dir="exports")

        try:
            yield
        finally:
            await app.state.notification_service.close()
            await app.state.openai_service.close()
            await app.state.event_bus.close()
            await database.dispose()

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(CommunityAccessMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    app.include_router(router, prefix="/api")
    app.include_router(websocket_router)

    # 条件性注册 MCP Server 路由
    if settings.mcp_enabled:
        from planagent.mcp.server import router as mcp_router

        app.include_router(
            mcp_router,
            tags=["MCP Server"],
            dependencies=[Depends(get_community_access_payload)],
        )

    return app


app = create_app()


def run() -> None:
    settings = get_settings()
    uvicorn.run("planagent.main:app", host=settings.bind_host, port=8000, reload=False)
