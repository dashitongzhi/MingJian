from __future__ import annotations

from typing import Any

import pytest

from planagent.api.routes.monitoring import monitoring_events_stream
from planagent.mcp.protocol import MCPProtocolHandler


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
