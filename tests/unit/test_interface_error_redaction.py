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
from planagent.services.notification import NotificationConfig, NotificationService
from planagent.services.openai_client import OpenAIService
from planagent.services.pipeline import PhaseOnePipelineService
from planagent.services.prediction import PredictionService
from planagent.services.simulation import SimulationService
from planagent.workers.base import public_worker_error
from planagent.workers.review import ReviewWorker
from planagent.workers.strategic_watch import StrategicWatchWorker
from planagent.workers.watch_ingest import WatchIngestWorker
from planagent.workers.prediction_revision import PredictionRevisionWorker


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
async def test_analysis_fetch_task_failure_redacts_internal_exception() -> None:
    service = AutomatedAnalysisService(Settings(_env_file=None))

    async def fail_fetch(*args: Any, **kwargs: Any) -> Any:
        _ = (args, kwargs)
        raise RuntimeError(_SECRET_ERROR)

    service._fetch_related_sources = fail_fetch  # type: ignore[method-assign]
    results = [
        item
        async for item in service._fetch_related_sources_with_events(
            AnalysisRequest(content="test", domain_id="corporate"),
            "test",
            "corporate",
        )
    ]

    serialized = str(results)
    assert _SECRET_ERROR not in serialized
    assert "Source fetching failed" in serialized


@pytest.mark.asyncio
async def test_analysis_stream_redacts_event_generator_failure() -> None:
    service = AutomatedAnalysisService(Settings(_env_file=None))

    async def fail_events(*args: Any, **kwargs: Any):
        _ = (args, kwargs)
        raise RuntimeError(_SECRET_ERROR)
        yield  # pragma: no cover

    service._fetch_related_sources_with_events = fail_events  # type: ignore[method-assign]
    events = [
        event
        async for event in service.stream_analysis(
            AnalysisRequest(content="test", domain_id="corporate")
        )
    ]

    serialized = str([event.payload for event in events])
    assert _SECRET_ERROR not in serialized
    assert "Source fetching failed" in serialized


@pytest.mark.asyncio
async def test_source_health_persists_only_generic_provider_failure() -> None:
    service = AutomatedAnalysisService(Settings(_env_file=None))
    record = SimpleNamespace(
        status="OK",
        consecutive_failures=0,
        last_error=None,
        last_failure_at=None,
        updated_at=None,
    )
    service._get_source_health = AsyncMock(  # type: ignore[method-assign]
        return_value=record
    )

    await service.record_source_failure(object(), "test-provider", _SECRET_ERROR)  # type: ignore[arg-type]

    assert record.status == "ERROR"
    assert record.consecutive_failures == 1
    assert record.last_error == "Source provider request failed"


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
async def test_openai_connection_diagnostics_do_not_echo_exception_messages() -> None:
    service = OpenAIService(
        Settings(
            _env_file=None,
            openai_primary_api_key="configured-key",
            openai_primary_model="test-model",
        )
    )
    failure = RuntimeError(
        "Authorization: Bearer provider-secret at "
        "https://user:password@10.0.0.8/v1?api_key=query-secret"
    )
    service.clients["primary"] = SimpleNamespace(
        responses=SimpleNamespace(create=AsyncMock(side_effect=failure)),
        chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(side_effect=failure))),
    )
    service._create_chat_completion_raw = AsyncMock(  # type: ignore[method-assign]
        side_effect=failure
    )

    result = await service.test_connection(target="primary")

    assert result.ok is False
    assert result.last_error is not None
    assert "provider-secret" not in result.last_error
    assert "password" not in result.last_error
    assert "query-secret" not in result.last_error
    assert "RuntimeError" in result.last_error


@pytest.mark.asyncio
async def test_notification_delivery_errors_are_redacted() -> None:
    service = NotificationService(NotificationConfig())
    service._send_websocket = AsyncMock(  # type: ignore[method-assign]
        side_effect=RuntimeError(_SECRET_ERROR)
    )

    notification = await service.notify(
        user_id="user-1",
        title="Test",
        body="Test body",
    )

    assert notification.delivered is False
    assert notification.error == "Notification delivery failed"
    assert _SECRET_ERROR not in str(notification)


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


@pytest.mark.asyncio
async def test_prediction_revision_event_failures_are_redacted() -> None:
    event = SimpleNamespace(
        topic="evidence.created",
        message_id="event-1",
        payload={"evidence_item_id": "evidence-1"},
    )
    published: list[dict[str, Any]] = []

    class FakeEventBus:
        async def reclaim_pending(self, **kwargs: Any) -> list[Any]:
            _ = kwargs
            return [event]

        async def consume(self, **kwargs: Any) -> list[Any]:
            _ = kwargs
            return []

        async def publish_dead_letter(self, topic: str, payload: dict[str, Any]) -> None:
            _ = topic
            published.append(payload)

        async def ack(self, topic: str, group: str, message_id: str) -> None:
            _ = (topic, group, message_id)

    worker = PredictionRevisionWorker.__new__(PredictionRevisionWorker)
    worker.event_bus = FakeEventBus()  # type: ignore[assignment]
    worker.worker_instance_id = "prediction-revision-worker"
    worker._enqueue_from_payload = AsyncMock(  # type: ignore[method-assign]
        side_effect=RuntimeError(_SECRET_ERROR)
    )

    enqueued, errors = await worker._consume_revision_events(_FakeSession())

    assert enqueued == 0
    assert errors == ["evidence.created:event-1:Worker execution failed"]
    assert published[0]["error"] == "Worker execution failed"
    assert _SECRET_ERROR not in str({"errors": errors, "published": published})


@pytest.mark.asyncio
async def test_ingest_and_knowledge_state_redacts_internal_failures() -> None:
    service = PhaseOnePipelineService.__new__(PhaseOnePipelineService)
    service.settings = SimpleNamespace(worker_max_attempts=1)
    service._publish_events = AsyncMock()  # type: ignore[method-assign]
    ingest_run = SimpleNamespace(
        id="ingest-1",
        request_payload={"items": []},
        processing_attempts=1,
        last_error=None,
        status="PROCESSING",
        lease_owner="worker",
        lease_expires_at=object(),
        updated_at=None,
    )
    service._claim_ingest_runs = AsyncMock(  # type: ignore[method-assign]
        return_value=[ingest_run]
    )
    service._stage_run_items = AsyncMock(  # type: ignore[method-assign]
        side_effect=RuntimeError(_SECRET_ERROR)
    )
    session = _FakeSession()

    processed = await service.process_queued_runs(session)

    assert processed == 0
    assert ingest_run.last_error == "Ingest processing failed"
    assert _SECRET_ERROR not in ingest_run.last_error

    raw = SimpleNamespace(
        id="raw-1",
        ingest_run_id="ingest-2",
        processing_attempts=1,
        knowledge_status="PROCESSING",
        last_error=None,
        lease_owner="worker",
        lease_expires_at=object(),
        processed_at=None,
    )
    parent_run = SimpleNamespace(id="ingest-2", summary={}, updated_at=None)
    knowledge_session = _FakeSession({"ingest-2": parent_run})
    service._claim_raw_items = AsyncMock(return_value=[raw])  # type: ignore[method-assign]
    service._materialize_knowledge_for_raw_item = AsyncMock(  # type: ignore[method-assign]
        side_effect=RuntimeError(_SECRET_ERROR)
    )
    service._finalize_queued_run = AsyncMock(return_value=False)  # type: ignore[method-assign]

    await service.process_pending_knowledge(knowledge_session)

    assert raw.last_error == "Knowledge materialization failed"
    assert _SECRET_ERROR not in raw.last_error


@pytest.mark.asyncio
async def test_simulation_and_report_state_redacts_internal_failures() -> None:
    service = SimulationService.__new__(SimulationService)
    service.settings = SimpleNamespace(worker_max_attempts=1)
    run = SimpleNamespace(
        id="run-1",
        parent_run_id=None,
        processing_attempts=1,
        last_error=None,
        status="PROCESSING",
        lease_owner="worker",
        lease_expires_at=object(),
        updated_at=None,
    )
    service._claim_simulation_runs = AsyncMock(return_value=[run])  # type: ignore[method-assign]
    service._execute_run = AsyncMock(  # type: ignore[method-assign]
        side_effect=RuntimeError(_SECRET_ERROR)
    )
    session = _FakeSession()

    processed = await service.process_queued_runs(session)

    assert processed == 0
    assert run.last_error == "Simulation execution failed"

    service._claim_report_runs = AsyncMock(return_value=[run])  # type: ignore[method-assign]
    service._generate_report = AsyncMock(  # type: ignore[method-assign]
        side_effect=RuntimeError(_SECRET_ERROR)
    )
    generated = await service.generate_pending_reports(session)

    assert generated == 0
    assert run.last_error == "Report generation failed"
    assert _SECRET_ERROR not in run.last_error


@pytest.mark.asyncio
async def test_review_state_and_worker_results_redact_internal_failures() -> None:
    review_item = SimpleNamespace(
        id="review-1",
        claim_id="claim-1",
        status="PENDING",
        lease_owner="worker",
        lease_expires_at=object(),
        last_error=None,
        updated_at=None,
    )
    claim = SimpleNamespace(id="claim-1")
    session = _FakeSession({"review-1": review_item, "claim-1": claim})

    class FakeDatabase:
        @asynccontextmanager
        async def session(self):
            yield session

    worker = ReviewWorker.__new__(ReviewWorker)
    worker._latest_automated_verdict = AsyncMock(  # type: ignore[method-assign]
        side_effect=RuntimeError(_SECRET_ERROR)
    )

    result = await worker._process_review_item(FakeDatabase(), "review-1")

    assert result["manual_queue"] == 1
    assert review_item.last_error == "Review processing failed"
    assert public_worker_error("claim", "claim-1") == "claim:claim-1:Worker execution failed"
    assert _SECRET_ERROR not in str({"last_error": review_item.last_error})
