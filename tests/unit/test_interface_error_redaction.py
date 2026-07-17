from __future__ import annotations

from typing import Any

import pytest

from planagent.api.routes.monitoring import monitoring_events_stream
from planagent.config import Settings
from planagent.mcp.protocol import MCPProtocolHandler
from planagent.services.jarvis import JarvisOrchestrator, JarvisTask


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
