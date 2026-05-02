from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from planagent.config import get_settings
from planagent.db import get_session
from planagent.domain.api import AnalysisResponse, AnalysisStepRead
from planagent.domain.models import AnalysisCacheRecord, utc_now
from planagent.events.bus import build_event_bus
from planagent.services.analysis import AutomatedAnalysisService
from planagent.services.assistant import StrategicAssistantService
from planagent.services.debate import DebateService
from planagent.services.openai_client import OpenAIService
from planagent.services.pipeline import PhaseOnePipelineService
from planagent.services.runtime import RuntimeMonitorService
from planagent.services.simulation import SimulationService
from planagent.services.workbench import WorkbenchService
from planagent.simulation.rules import get_rule_registry


_CACHED_SERVICE_ATTRS = (
    "pipeline_service",
    "simulation_service",
    "analysis_service",
    "debate_service",
    "workbench_service",
    "runtime_monitor_service",
    "assistant_service",
)
_last_app_state = None
_fallback_services_state = type("_FallbackServicesState", (), {})()


def _remember_app_state(request: Request) -> None:
    global _last_app_state
    _last_app_state = request.app.state


def _cache_business_services(state: object) -> None:
    settings = get_settings()
    if not hasattr(state, "pipeline_service"):
        state.pipeline_service = PhaseOnePipelineService(
            settings,
            state.event_bus,
            state.openai_service,
        )
    if not hasattr(state, "simulation_service"):
        state.simulation_service = SimulationService(
            settings,
            state.event_bus,
            state.rule_registry,
            state.openai_service,
        )
    if not hasattr(state, "analysis_service"):
        state.analysis_service = AutomatedAnalysisService(settings, state.openai_service)
    if not hasattr(state, "debate_service"):
        state.debate_service = DebateService(settings, state.event_bus, state.openai_service)
    if not hasattr(state, "workbench_service"):
        state.workbench_service = WorkbenchService()
    if not hasattr(state, "runtime_monitor_service"):
        state.runtime_monitor_service = RuntimeMonitorService(
            settings.backpressure_pending_threshold
        )
    if not hasattr(state, "assistant_service"):
        state.assistant_service = StrategicAssistantService(
            analysis_service=state.analysis_service,
            pipeline_service=state.pipeline_service,
            simulation_service=state.simulation_service,
            debate_service=state.debate_service,
            workbench_service=state.workbench_service,
        )


def _get_state_or_fallback() -> object:
    return _last_app_state if _last_app_state is not None else _fallback_services_state


def clear_services_cache(request: Request | None = None) -> None:
    state = request.app.state if request is not None else _get_state_or_fallback()
    for attr in _CACHED_SERVICE_ATTRS:
        if hasattr(state, attr):
            delattr(state, attr)


def ensure_app_services(request: Request) -> None:
    _remember_app_state(request)
    settings = get_settings()
    if not hasattr(request.app.state, "event_bus"):
        request.app.state.event_bus = build_event_bus(settings)
    if not hasattr(request.app.state, "rule_registry"):
        request.app.state.rule_registry = get_rule_registry(settings.rules_dir)
    if not hasattr(request.app.state, "openai_service"):
        request.app.state.openai_service = OpenAIService(settings)
    _cache_business_services(request.app.state)


def get_pipeline_service(request: Request) -> PhaseOnePipelineService:
    ensure_app_services(request)
    if not hasattr(request.app.state, "pipeline_service"):
        request.app.state.pipeline_service = PhaseOnePipelineService(
            get_settings(),
            request.app.state.event_bus,
            request.app.state.openai_service,
        )
    return request.app.state.pipeline_service


def get_simulation_service(request: Request) -> SimulationService:
    ensure_app_services(request)
    if not hasattr(request.app.state, "simulation_service"):
        request.app.state.simulation_service = SimulationService(
            get_settings(),
            request.app.state.event_bus,
            request.app.state.rule_registry,
            request.app.state.openai_service,
        )
    return request.app.state.simulation_service


def get_analysis_service(request: Request) -> AutomatedAnalysisService:
    ensure_app_services(request)
    if not hasattr(request.app.state, "analysis_service"):
        request.app.state.analysis_service = AutomatedAnalysisService(
            get_settings(), request.app.state.openai_service
        )
    return request.app.state.analysis_service


def get_debate_service(request: Request) -> DebateService:
    ensure_app_services(request)
    if not hasattr(request.app.state, "debate_service"):
        request.app.state.debate_service = DebateService(
            get_settings(), request.app.state.event_bus, request.app.state.openai_service
        )
    return request.app.state.debate_service


def get_workbench_service() -> WorkbenchService:
    state = _get_state_or_fallback()
    if not hasattr(state, "workbench_service"):
        state.workbench_service = WorkbenchService()
    return state.workbench_service


def get_assistant_service(request: Request) -> StrategicAssistantService:
    ensure_app_services(request)
    if not hasattr(request.app.state, "assistant_service"):
        request.app.state.assistant_service = StrategicAssistantService(
            analysis_service=get_analysis_service(request),
            pipeline_service=get_pipeline_service(request),
            simulation_service=get_simulation_service(request),
            debate_service=get_debate_service(request),
            workbench_service=get_workbench_service(),
        )
    return request.app.state.assistant_service


def get_runtime_monitor_service() -> RuntimeMonitorService:
    state = _get_state_or_fallback()
    if not hasattr(state, "runtime_monitor_service"):
        state.runtime_monitor_service = RuntimeMonitorService(
            get_settings().backpressure_pending_threshold
        )
    return state.runtime_monitor_service


def _analysis_cache_key(payload: object) -> str:
    payload_json = json.dumps(payload.model_dump(mode="json"), sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(payload_json.encode("utf-8")).hexdigest()


async def _get_cached_analysis(session: AsyncSession, payload: object) -> AnalysisResponse | None:
    settings = get_settings()
    if not settings.analysis_cache_enabled or settings.api_cache_ttl_seconds <= 0:
        return None
    cache_key = _analysis_cache_key(payload)
    now = utc_now()
    record = (
        await session.scalars(
            select(AnalysisCacheRecord)
            .where(
                AnalysisCacheRecord.cache_key == cache_key,
                AnalysisCacheRecord.expires_at > now,
            )
            .limit(1)
        )
    ).first()
    if record is None:
        return None
    response = AnalysisResponse.model_validate(record.response_payload)
    cache_step = AnalysisStepRead(
        stage="cache_hit",
        message="Returned cached analysis result.",
        detail=f"cache_key={cache_key}; expires_at={record.expires_at.isoformat()}",
    )
    return response.model_copy(update={"reasoning_steps": [cache_step, *response.reasoning_steps]})


async def _store_cached_analysis(
    session: AsyncSession,
    payload: object,
    response: AnalysisResponse,
) -> None:
    settings = get_settings()
    if not settings.analysis_cache_enabled or settings.api_cache_ttl_seconds <= 0:
        return
    cache_key = _analysis_cache_key(payload)
    now = utc_now()
    expires_at = now + timedelta(seconds=settings.api_cache_ttl_seconds)
    request_payload = payload.model_dump(mode="json")
    response_payload = response.model_dump(mode="json")
    record = (
        await session.scalars(
            select(AnalysisCacheRecord).where(AnalysisCacheRecord.cache_key == cache_key).limit(1)
        )
    ).first()
    if record is None:
        session.add(
            AnalysisCacheRecord(
                cache_key=cache_key,
                domain_id=response.domain_id,
                query=response.query,
                request_payload=request_payload,
                response_payload=response_payload,
                expires_at=expires_at,
            )
        )
    else:
        record.domain_id = response.domain_id
        record.query = response.query
        record.request_payload = request_payload
        record.response_payload = response_payload
        record.created_at = now
        record.expires_at = expires_at
    await session.commit()


def _datetime_is_future(value: datetime, reference: datetime) -> bool:
    candidate = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    baseline = reference if reference.tzinfo is not None else reference.replace(tzinfo=timezone.utc)
    return candidate > baseline
