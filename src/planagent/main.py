from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

import planagent.simulation  # noqa: F401
from planagent.api.routes import router
from planagent.api.routes.ws import router as websocket_router
from planagent.config import get_settings
from planagent.db import get_database
from planagent.events.bus import build_event_bus
from planagent.services.openai_client import OpenAIService
from planagent.simulation.rules import get_rule_registry


def create_app() -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database = get_database(settings.database_url)
        await database.init_models()
        app.state.event_bus = build_event_bus(settings)
        app.state.rule_registry = get_rule_registry(settings.rules_dir)
        app.state.openai_service = OpenAIService(settings)
        try:
            yield
        finally:
            await app.state.openai_service.close()
            await app.state.event_bus.close()
            await database.dispose()

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    app.include_router(websocket_router)

    # 条件性注册 MCP Server 路由
    if settings.mcp_enabled:
        from planagent.mcp.server import router as mcp_router

        app.include_router(mcp_router, tags=["MCP Server"])

    return app


app = create_app()


def run() -> None:
    uvicorn.run("planagent.main:app", host="0.0.0.0", port=8000, reload=False)
