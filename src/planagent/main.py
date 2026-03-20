from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
import uvicorn

import planagent.simulation  # noqa: F401
from planagent.api.routes import router
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
    app.include_router(router)
    return app


app = create_app()


def run() -> None:
    uvicorn.run("planagent.main:app", host="0.0.0.0", port=8000, reload=False)
