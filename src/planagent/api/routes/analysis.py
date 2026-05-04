from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from planagent.config import get_settings
from planagent.db import get_session
from planagent.domain.api import (
    AnalysisRequest,
    AnalysisResponse,
    DebateTriggerRequest,
    StrategicAssistantRequest,
    StrategicAssistantResponse,
    StrategicSessionDetailRead,
    StrategicSessionRead,
)
from planagent.api.routes._deps import (
    _get_cached_analysis,
    _store_cached_analysis,
    ensure_app_services,
    get_analysis_service,
    get_assistant_service,
    get_debate_service,
)

router = APIRouter()
_CONSOLE_HTML = Path(__file__).resolve().parents[2] / "ui" / "strategic_console.html"
_APP_VERSION = "0.1.0"


@router.get("/")
async def root(request: Request) -> dict[str, object]:
    ensure_app_services(request)
    return {
        "app": get_settings().app_name,
        "status": "ok",
        "docs_url": "/docs",
        "health_url": "/health",
        "console_url": "/console",
        "openai": request.app.state.openai_service.status().model_dump(),
    }


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/live")
async def health_live() -> dict[str, str]:
    return {"status": "ok", "version": _APP_VERSION}


@router.get("/health/ready")
async def health_ready(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    checks = {
        "database": "fail",
        "redis": "skip",
    }

    try:
        await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "fail"

    settings = get_settings()
    if settings.event_bus_backend.lower() == "redis":
        try:
            event_bus = request.app.state.event_bus
            await event_bus.client.ping()
            checks["redis"] = "ok"
        except Exception:
            checks["redis"] = "fail"

    non_skip_checks = [check for check in checks.values() if check != "skip"]
    status = "ok" if all(check == "ok" for check in non_skip_checks) else "degraded"
    return {"status": status, "checks": checks}


@router.post("/analysis", response_model=AnalysisResponse)
async def analyze_content(
    payload: AnalysisRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> AnalysisResponse:
    cached = await _get_cached_analysis(session, payload)
    if cached is not None:
        return cached
    service = get_analysis_service(request)
    response = await service.analyze(payload)
    await _store_cached_analysis(session, payload, response)
    return response


@router.post("/analysis/stream")
async def analyze_content_stream(
    payload: AnalysisRequest,
    request: Request,
) -> StreamingResponse:
    service = get_analysis_service(request)

    async def event_stream():
        async for event in service.stream_analysis(payload):
            yield f"event: {event.event}\n"
            yield f"data: {json.dumps(event.payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/debate/stream")
async def debate_stream(
    payload: DebateTriggerRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    service = get_debate_service(request)

    async def event_stream():
        async for event in service.stream_debate(session, payload):
            yield f"event: {event.event}\n"
            yield f"data: {json.dumps(event.payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/console")
async def strategic_console():
    if _CONSOLE_HTML.exists():
        return FileResponse(str(_CONSOLE_HTML), media_type="text/html")
    return JSONResponse(
        status_code=404,
        content={"detail": "Strategic console UI not yet available. Use the frontend at :3001 instead."},
    )


@router.post("/assistant/runs", response_model=StrategicAssistantResponse, status_code=201)
async def create_strategic_assistant_run(
    payload: StrategicAssistantRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> StrategicAssistantResponse:
    service = get_assistant_service(request)
    return await service.run(session, payload)


@router.post("/assistant/sessions", response_model=StrategicSessionRead, status_code=201)
async def create_strategic_session(
    payload: StrategicAssistantRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> StrategicSessionRead:
    service = get_assistant_service(request)
    return await service.create_session(session, payload)


@router.get("/assistant/sessions", response_model=list[StrategicSessionRead])
async def list_strategic_sessions(
    request: Request,
    tenant_id: str | None = None,
    preset_id: str | None = None,
    limit: int = Query(default=12, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> list[StrategicSessionRead]:
    service = get_assistant_service(request)
    return await service.list_sessions(session, tenant_id=tenant_id, preset_id=preset_id, limit=limit)


@router.get("/assistant/sessions/{session_id}", response_model=StrategicSessionDetailRead)
async def get_strategic_session_detail(
    session_id: str,
    request: Request,
    brief_limit: int = Query(default=10, ge=1, le=50),
    run_limit: int = Query(default=10, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
) -> StrategicSessionDetailRead:
    service = get_assistant_service(request)
    detail = await service.get_session_detail(
        session,
        session_id,
        brief_limit=brief_limit,
        run_limit=run_limit,
    )
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Strategic session {session_id} not found.")
    return detail


@router.post("/assistant/daily-brief", response_model=AnalysisResponse)
async def create_daily_brief(
    payload: StrategicAssistantRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> AnalysisResponse:
    service = get_assistant_service(request)
    return await service.daily_brief(session, payload)


@router.post("/assistant/stream")
async def strategic_assistant_stream(
    payload: StrategicAssistantRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    service = get_assistant_service(request)

    async def event_stream():
        async for event in service.stream(session, payload):
            yield f"event: {event.event}\n"
            yield f"data: {json.dumps(event.payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
