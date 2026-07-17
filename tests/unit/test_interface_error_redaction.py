from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from planagent.api.routes.monitoring import monitoring_events_stream
from planagent.config import Settings
from planagent.domain.api import AnalysisRequest
from planagent.mcp.protocol import MCPProtocolHandler
from planagent.services.analysis import AutomatedAnalysisService
from planagent.services.jarvis import JarvisOrchestrator, JarvisTask
from planagent.services.prediction import PredictionService
from planagent.workers.strategic_watch import StrategicWatchWorker
from planagent.workers.watch_ingest import WatchIngestWorker


_SECRET_ERROR = "provider token sk-secret at http://10.0.0.8:6379"


class _FailingEventBus:
    async def consume(self, **kwargs: Any) -> list[Any]:
        _ = kwargs
        raise RuntimeError(_SECRET_ERROR)

    async def close(self) -> None:
        return None


class _ConnectedRequest:
    async def is_disconnected(self) -> bool:
        return False


class _FailingOpenAIService:
    def is_configured(self, target: str) -> bool:
        _ = target
        return True

    async def generate_json_for_target(self, **kwargs: Any) -> tuple[str, dict[str, Any]]:
        _ = kwargs
        raise RuntimeError(_SECRET_ERROR)


class _FakeSession:
    def __init__(self, records: dict[str, Any] | None = None) -> None:
        self.records = records or {}

    async def rollback(self) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def get(self, model: Any, record_id: str) -> Any:
        _ = model
        return self.records.get(record_id)


class _FakeDatabase:
    @asynccontextmanager
    async def session(self):
        yield _FakeSession()

    async def test_connection(self, target: str) -> str:
        _ = target
        raise RuntimeError(_SECRET_ERROR)


@pytest.mark.asyncio
async def test_monitoring_stream_redacts_internal_event_bus_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "planagent.api.routes.monitoring.build_event_bus",
        lambda settings: _FailingEventBus(),
    )
    response = await monitoring_events_stream(_ConnectedRequest())  # type: ignore[arg-type]

    chunk = await anext(response.body_iterator)
    await response.body_iterator.aclose()

    assert _SECRET_ERROR not in chunk
    assert "Monitoring stream temporarily unavailable" in chunk


@pytest.mark.asyncio
async def test_analysis_source_events_redact_provider_exceptions() -> None:
    service = AutomatedAnalysisService(Settings(_env_file=None))

    async def fail_fetch(query: str, limit: int) -> list[Any]:
        _ = (query, limit)
        raise RuntimeError(_SECRET_ERROR)

    adapter = SimpleNamespace(
        key="test-provider",
        label="Test Provider",
        enabled=True,
        limit=1,
        unavailable_reason=None,
        agent_name="test-agent",
        agent_icon="test",
        task_desc="test source",
        fetch_query=fail_fetch,
    )
    service.source_registry.build_adapters = lambda payload, query, domain_id: [  # type: ignore[method-assign]
        adapter
    ]
    event_queue: asyncio.Queue[Any] = asyncio.Queue()

    bundle = await service._fetch_related_sources(
        AnalysisRequest(content="test", domain_id="corporate"),
        "test",
        "corporate",
        event_queue=event_queue,
    )
    events = []
    while not event_queue.empty():
        events.append(event_queue.get_nowait())

    serialized = str(
        {
            "steps": [step.model_dump(mode="json") for step in bundle.steps],
            "events": [event.payload for event in events],
        }
    )
    assert _SECRET_ERROR not in serialized
    assert "Source provider request failed" in serialized


@pytest.mark.asyncio
async def test_mcp_internal_error_does_not_echo_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handler = MCPProtocolHandler("test", "1.0", "2024-11-05")

    async def fail_dispatch(method: str, params: dict[str, Any]) -> dict[str, Any]:
        _ = (method, params)
        raise RuntimeError(_SECRET_ERROR)

    monkeypatch.setattr(handler, "_dispatch", fail_dispatch)
    response = await handler.handle_message({"jsonrpc": "2.0", "id": 1, "method": "ping"})

    assert response is not None
    error = response["error"]
    assert isinstance(error, dict)
    assert _SECRET_ERROR not in str(error)
    assert error["message"] == "Internal server error"


@pytest.mark.asyncio
async def test_jarvis_outputs_redact_provider_failures() -> None:
    orchestrator = JarvisOrchestrator(
        Settings(_env_file=None),
        _FailingOpenAIService(),  # type: ignore[arg-type]
    )

    result = await orchestrator.orchestrate(JarvisTask(task_type="analysis", payload={}))
    connection = await orchestrator.test_target("primary")

    serialized = str({"run": result.to_dict(), "connection": connection})
    assert _SECRET_ERROR not in serialized
    assert "Model request failed" in serialized
    assert "Model review unavailable" in serialized
    assert connection["error"] == "Model connection test failed"


@pytest.mark.asyncio
async def test_strategic_watch_persists_only_generic_refresh_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = StrategicWatchWorker.__new__(StrategicWatchWorker)
    worker.worker_instance_id = "strategic-watch-worker"
    worker._claim_due_sessions = AsyncMock(  # type: ignore[method-assign]
        return_value=[SimpleNamespace(id="session-1")]
    )
    worker._community_window_expired = lambda record: False  # type: ignore[method-assign]

    async def fail_load(session: Any, session_id: str) -> dict[str, Any]:
        _ = (session, session_id)
        raise RuntimeError(_SECRET_ERROR)

    worker.service = SimpleNamespace(load_session_payload=fail_load)
    recorded_errors: list[str] = []

    async def record_failure(session: Any, session_id: str, error: str) -> None:
        _ = (session, session_id)
        recorded_errors.append(error)

    worker._mark_failure = record_failure  # type: ignore[method-assign]
    monkeypatch.setattr("planagent.workers.strategic_watch.get_database", _FakeDatabase)

    result = await worker.run_once()

    assert result["failed_sessions"] == 1
    assert recorded_errors == ["Strategic session refresh failed"]


@pytest.mark.asyncio
async def test_watch_ingest_persists_only_generic_poll_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = WatchIngestWorker.__new__(WatchIngestWorker)
    worker.event_bus = object()  # type: ignore[assignment]
    worker.settings = SimpleNamespace()
    worker.worker_instance_id = "watch-ingest-worker"
    worker._claim_due_rules = AsyncMock(  # type: ignore[method-assign]
        return_value=[SimpleNamespace(id="rule-1")]
    )

    async def fail_poll(session: Any, rule: Any) -> dict[str, Any]:
        _ = (session, rule)
        raise RuntimeError(_SECRET_ERROR)

    worker._poll_rule = fail_poll  # type: ignore[method-assign]
    recorded_errors: list[str] = []

    async def record_failure(session: Any, rule_id: str, error: str) -> None:
        _ = (session, rule_id)
        recorded_errors.append(error)

    worker._mark_failure = record_failure  # type: ignore[method-assign]
    monkeypatch.setattr("planagent.workers.watch_ingest.get_database", _FakeDatabase)

    result = await worker.run_once()

    assert result["failed"] == 1
    assert recorded_errors == ["Watch rule polling failed"]


@pytest.mark.asyncio
async def test_prediction_revision_jobs_expose_only_generic_failures() -> None:
    service = PredictionService.__new__(PredictionService)
    pending_job = SimpleNamespace(
        id="job-pending",
        status="PENDING",
        last_error=None,
        lease_owner="worker",
        lease_expires_at=object(),
        updated_at=None,
    )
    processing_job = SimpleNamespace(
        id="job-processing",
        status="PROCESSING",
        revision_run_id="run-failed",
        last_error=None,
        lease_owner="worker",
        lease_expires_at=object(),
        updated_at=None,
    )
    failed_run = SimpleNamespace(status="FAILED", last_error=_SECRET_ERROR)
    session = _FakeSession({"run-failed": failed_run})
    service._claim_revision_jobs = AsyncMock(  # type: ignore[method-assign]
        return_value=[pending_job, processing_job]
    )
    service._start_revision_simulation = AsyncMock(  # type: ignore[method-assign]
        side_effect=RuntimeError(_SECRET_ERROR)
    )

    processed = await service.process_revision_jobs(session, worker_id="test-worker")

    assert processed == 2
    assert pending_job.last_error == "Prediction revision failed"
    assert processing_job.last_error == "Revision simulation failed"
    assert _SECRET_ERROR not in str([pending_job.last_error, processing_job.last_error])
