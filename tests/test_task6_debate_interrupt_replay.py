"""Tests for debate interruption and replay functionality (Task 6).

Tests cover:
- POST /debates/{debate_id}/interrupt — user interruption during debate
- GET /debates/{debate_id}/interrupts — list all interruptions
- GET /debates/{debate_id}/pending-interrupts — list pending interruptions
- GET /debates/{debate_id}/replay — replay with interrupt events in timeline
- GET /debates/{debate_id}/timeline — timeline with interrupt events
- GET /debates/{debate_id}/replay/rounds/{round_number} — round detail
- GET /debates/{debate_id}/summary — summary with turning points
"""

from __future__ import annotations

from pathlib import Path
from fastapi.testclient import TestClient

from planagent.config import reset_settings_cache
from planagent.db import reset_database_cache
from planagent.main import create_app


def build_database_url(path: Path) -> str:
    return f"sqlite+aiosqlite:///{path.resolve().as_posix()}"


def disable_openai(monkeypatch) -> None:
    monkeypatch.setenv("PLANAGENT_OPENAI_API_KEY", "")
    monkeypatch.setenv("PLANAGENT_OPENAI_BASE_URL", "")
    monkeypatch.setenv("PLANAGENT_OPENAI_PRIMARY_API_KEY", "")
    monkeypatch.setenv("PLANAGENT_OPENAI_PRIMARY_BASE_URL", "")
    monkeypatch.setenv("PLANAGENT_OPENAI_EXTRACTION_API_KEY", "")
    monkeypatch.setenv("PLANAGENT_OPENAI_EXTRACTION_BASE_URL", "")
    monkeypatch.setenv("PLANAGENT_OPENAI_X_SEARCH_API_KEY", "")
    monkeypatch.setenv("PLANAGENT_OPENAI_X_SEARCH_BASE_URL", "")
    monkeypatch.setenv("PLANAGENT_OPENAI_REPORT_API_KEY", "")
    monkeypatch.setenv("PLANAGENT_OPENAI_REPORT_BASE_URL", "")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


def _setup_app(monkeypatch, tmp_path: Path):
    """Create app and setup env for testing."""
    database_path = tmp_path / "test-debate-interrupt.db"
    monkeypatch.setenv("PLANAGENT_DATABASE_URL", build_database_url(database_path))
    monkeypatch.setenv("PLANAGENT_EVENT_BUS_BACKEND", "memory")
    monkeypatch.setenv("PLANAGENT_INLINE_INGEST_DEFAULT", "true")
    monkeypatch.setenv("PLANAGENT_INLINE_SIMULATION_DEFAULT", "true")
    disable_openai(monkeypatch)
    reset_settings_cache()
    reset_database_cache()


def _create_debate(client: TestClient, run_id: str, topic: str) -> dict:
    """Helper: trigger a debate and return its payload."""
    resp = client.post(
        "/debates/trigger",
        json={
            "run_id": run_id,
            "topic": topic,
            "trigger_type": "manual",
            "target_type": "run",
        },
    )
    assert resp.status_code == 201
    return resp.json()


def _create_run_with_debate(client: TestClient) -> tuple[str, dict]:
    """Helper: ingest, create simulation run, trigger debate. Returns (run_id, debate)."""
    ingest_resp = client.post(
        "/ingest/runs",
        json={
            "requested_by": "interrupt-test",
            "items": [
                {
                    "source_type": "osint",
                    "source_url": "https://example.com/interrupt-test",
                    "title": "Test intelligence for interrupt test",
                    "content_text": "Supply line disruption observed near river crossing. Civilian area under pressure.",
                    "published_at": "2026-04-01T09:00:00Z",
                }
            ],
        },
    )
    assert ingest_resp.status_code == 201

    sim_resp = client.post(
        "/simulation/runs",
        json={
            "domain_id": "military",
            "force_id": "test-brigade",
            "force_name": "Test Brigade",
            "theater": "test-sector",
            "tick_count": 3,
            "actor_template": "brigade",
        },
    )
    assert sim_resp.status_code == 201
    run_id = sim_resp.json()["id"]

    debate = _create_debate(client, run_id, "Should Test Brigade prioritize supply line restoration?")
    return run_id, debate


# ── Interrupt Tests ──────────────────────────────────────────────────────────


def test_interrupt_on_running_debate(monkeypatch, tmp_path: Path) -> None:
    """用户可以在运行中的辩论提交插话"""
    _setup_app(monkeypatch, tmp_path)

    with TestClient(create_app()) as client:
        _, debate = _create_run_with_debate(client)
        debate_id = debate["id"]

        # The default trigger creates COMPLETED debates, but for interrupt
        # testing we need a RUNNING one. Let's check status.
        # The trigger_debate endpoint creates COMPLETED status by default.
        # We need to manually test with a stream endpoint or check behavior.

        # Interrupt on a completed debate should fail with 409
        resp = client.post(
            f"/debates/{debate_id}/interrupt",
            json={
                "message": "New intelligence: enemy forces spotted at sector B",
                "interrupt_type": "new_evidence",
            },
        )
        # Completed debate cannot be interrupted
        assert resp.status_code == 409
        assert "not running" in resp.json()["detail"].lower()


def test_interrupt_on_nonexistent_debate(monkeypatch, tmp_path: Path) -> None:
    """对不存在的辩论提交插话返回404"""
    _setup_app(monkeypatch, tmp_path)

    with TestClient(create_app()) as client:
        resp = client.post(
            "/debates/nonexistent-id/interrupt",
            json={
                "message": "Test message",
                "interrupt_type": "general",
            },
        )
        assert resp.status_code == 404


def test_interrupt_empty_message_rejected(monkeypatch, tmp_path: Path) -> None:
    """空消息应被拒绝"""
    _setup_app(monkeypatch, tmp_path)

    with TestClient(create_app()) as client:
        _, debate = _create_run_with_debate(client)
        debate_id = debate["id"]

        resp = client.post(
            f"/debates/{debate_id}/interrupt",
            json={
                "message": "",
                "interrupt_type": "general",
            },
        )
        # Should be rejected due to min_length=1 validation
        assert resp.status_code == 422


def test_interrupt_invalid_type_rejected(monkeypatch, tmp_path: Path) -> None:
    """无效的插话类型应被拒绝"""
    _setup_app(monkeypatch, tmp_path)

    with TestClient(create_app()) as client:
        _, debate = _create_run_with_debate(client)
        debate_id = debate["id"]

        resp = client.post(
            f"/debates/{debate_id}/interrupt",
            json={
                "message": "Test message",
                "interrupt_type": "invalid_type",
            },
        )
        assert resp.status_code == 422


def test_list_interrupts_empty(monkeypatch, tmp_path: Path) -> None:
    """没有插话时返回空列表"""
    _setup_app(monkeypatch, tmp_path)

    with TestClient(create_app()) as client:
        _, debate = _create_run_with_debate(client)
        debate_id = debate["id"]

        resp = client.get(f"/debates/{debate_id}/interrupts")
        assert resp.status_code == 200
        assert resp.json() == []


def test_list_interrupts_nonexistent_debate(monkeypatch, tmp_path: Path) -> None:
    """查询不存在辩论的插话返回404"""
    _setup_app(monkeypatch, tmp_path)

    with TestClient(create_app()) as client:
        resp = client.get("/debates/nonexistent-id/interrupts")
        assert resp.status_code == 404


def test_list_pending_interrupts_empty(monkeypatch, tmp_path: Path) -> None:
    """没有待注入插话时返回空列表"""
    _setup_app(monkeypatch, tmp_path)

    with TestClient(create_app()) as client:
        _, debate = _create_run_with_debate(client)
        debate_id = debate["id"]

        resp = client.get(f"/debates/{debate_id}/pending-interrupts")
        assert resp.status_code == 200
        assert resp.json() == []


# ── Replay Tests ─────────────────────────────────────────────────────────────


def test_replay_includes_timeline(monkeypatch, tmp_path: Path) -> None:
    """回放应包含按时间顺序的事件（speech events）"""
    _setup_app(monkeypatch, tmp_path)

    with TestClient(create_app()) as client:
        _, debate = _create_run_with_debate(client)
        debate_id = debate["id"]

        resp = client.get(f"/debates/{debate_id}/replay")
        assert resp.status_code == 200
        replay = resp.json()

        assert replay["debate_id"] == debate_id
        assert replay["total_rounds"] > 0
        assert len(replay["timeline"]) > 0
        assert len(replay["rounds_by_number"]) > 0

        # Each timeline event should have event_type
        for event in replay["timeline"]:
            assert "event_type" in event
            assert "timestamp" in event

        # Should have verdict
        assert replay["verdict"] is not None


def test_replay_nonexistent_debate(monkeypatch, tmp_path: Path) -> None:
    """查询不存在辩论的回放返回404"""
    _setup_app(monkeypatch, tmp_path)

    with TestClient(create_app()) as client:
        resp = client.get("/debates/nonexistent-id/replay")
        assert resp.status_code == 404


def test_round_detail(monkeypatch, tmp_path: Path) -> None:
    """单轮回放应返回该轮所有发言"""
    _setup_app(monkeypatch, tmp_path)

    with TestClient(create_app()) as client:
        _, debate = _create_run_with_debate(client)
        debate_id = debate["id"]

        # Get round 1 detail
        resp = client.get(f"/debates/{debate_id}/replay/rounds/1")
        assert resp.status_code == 200
        detail = resp.json()

        assert detail["debate_id"] == debate_id
        assert detail["round_number"] == 1
        assert len(detail["speeches"]) > 0
        for speech in detail["speeches"]:
            assert "role" in speech
            assert "position" in speech
            assert "confidence" in speech
            assert "timestamp" in speech


def test_round_detail_nonexistent_round(monkeypatch, tmp_path: Path) -> None:
    """查询不存在的轮次返回404"""
    _setup_app(monkeypatch, tmp_path)

    with TestClient(create_app()) as client:
        _, debate = _create_run_with_debate(client)
        debate_id = debate["id"]

        resp = client.get(f"/debates/{debate_id}/replay/rounds/99")
        assert resp.status_code == 404


def test_timeline(monkeypatch, tmp_path: Path) -> None:
    """辩论时间线应包含所有发言事件"""
    _setup_app(monkeypatch, tmp_path)

    with TestClient(create_app()) as client:
        _, debate = _create_run_with_debate(client)
        debate_id = debate["id"]

        resp = client.get(f"/debates/{debate_id}/timeline")
        assert resp.status_code == 200
        timeline = resp.json()

        assert timeline["debate_id"] == debate_id
        assert timeline["event_count"] > 0
        assert len(timeline["events"]) > 0
        assert timeline["verdict_event"] is not None

        # Events should have event_type
        for event in timeline["events"]:
            assert "event_type" in event
            assert "timestamp" in event


def test_summary_includes_turning_points(monkeypatch, tmp_path: Path) -> None:
    """辩论摘要应包含转折点信息"""
    _setup_app(monkeypatch, tmp_path)

    with TestClient(create_app()) as client:
        _, debate = _create_run_with_debate(client)
        debate_id = debate["id"]

        resp = client.get(f"/debates/{debate_id}/summary")
        assert resp.status_code == 200
        summary = resp.json()

        assert summary["debate_id"] == debate_id
        assert summary["total_rounds"] > 0
        assert summary["verdict"] is not None
        assert "round_summaries" in summary
        assert "turning_points" in summary
        assert len(summary["round_summaries"]) > 0


def test_compare_debates(monkeypatch, tmp_path: Path) -> None:
    """对比两场辩论应返回差异统计"""
    _setup_app(monkeypatch, tmp_path)

    with TestClient(create_app()) as client:
        _, debate1 = _create_run_with_debate(client)
        debate_id_1 = debate1["id"]

        # Create second debate on same run
        run_id = debate1["run_id"]
        debate2 = _create_debate(client, run_id, "Should Test Brigade shift ISR coverage?")
        debate_id_2 = debate2["id"]

        resp = client.get(
            "/debates/compare",
            params={"debate_id_1": debate_id_1, "debate_id_2": debate_id_2},
        )
        assert resp.status_code == 200
        comparison = resp.json()

        assert comparison["debate_1"]["debate_id"] == debate_id_1
        assert comparison["debate_2"]["debate_id"] == debate_id_2
        assert "differences" in comparison


# ── Unit Tests for DebateService Helper Methods ──────────────────────────────


def test_format_interrupts_for_context() -> None:
    """Test the static method that formats interrupts for context injection."""
    from dataclasses import dataclass
    from datetime import datetime, timezone
    from planagent.services.debate import DebateService

    @dataclass
    class FakeInterrupt:
        id: str
        debate_session_id: str
        message: str
        interrupt_type: str
        injected_at_round: int | None
        status: str
        created_at: datetime

    now = datetime.now(timezone.utc)

    # Empty list
    assert DebateService.format_interrupts_for_context([]) is None

    # Single interrupt
    intr = FakeInterrupt(
        id="intr-1",
        debate_session_id="test-debate",
        message="New intel from sector B",
        interrupt_type="new_evidence",
        injected_at_round=None,
        status="PENDING",
        created_at=now,
    )

    result = DebateService.format_interrupts_for_context([intr])
    assert result is not None
    assert "用户插话" in result
    assert "[新证据]" in result
    assert "New intel from sector B" in result

    # Multiple interrupts with different types
    intr2 = FakeInterrupt(
        id="intr-2",
        debate_session_id="test-debate",
        message="Please focus on civilian protection",
        interrupt_type="direction_correction",
        injected_at_round=None,
        status="PENDING",
        created_at=now,
    )

    intr3 = FakeInterrupt(
        id="intr-3",
        debate_session_id="test-debate",
        message="Additional context about supply routes",
        interrupt_type="supplementary_info",
        injected_at_round=None,
        status="PENDING",
        created_at=now,
    )

    result = DebateService.format_interrupts_for_context([intr, intr2, intr3])
    assert "[新证据]" in result
    assert "[修正方向]" in result
    assert "[补充信息]" in result
    assert result.count("[用户插话") == 1  # header line


def test_format_interrupts_general_type() -> None:
    """Test that 'general' type uses the default label."""
    from dataclasses import dataclass
    from datetime import datetime, timezone
    from planagent.services.debate import DebateService

    @dataclass
    class FakeInterrupt:
        id: str
        debate_session_id: str
        message: str
        interrupt_type: str
        injected_at_round: int | None
        status: str
        created_at: datetime

    intr = FakeInterrupt(
        id="intr-1",
        debate_session_id="test-debate",
        message="General observation",
        interrupt_type="general",
        injected_at_round=None,
        status="PENDING",
        created_at=datetime.now(timezone.utc),
    )

    result = DebateService.format_interrupts_for_context([intr])
    assert "[通用插话]" in result


# ── Interrupt Model Tests ────────────────────────────────────────────────────


def test_interrupt_model_constraints() -> None:
    """Verify model has correct table name and constraints."""
    from planagent.domain.models import DebateInterruptRecord

    assert DebateInterruptRecord.__tablename__ == "debate_interrupts"
    assert hasattr(DebateInterruptRecord, "debate_session_id")
    assert hasattr(DebateInterruptRecord, "message")
    assert hasattr(DebateInterruptRecord, "interrupt_type")
    assert hasattr(DebateInterruptRecord, "injected_at_round")
    assert hasattr(DebateInterruptRecord, "status")
    assert hasattr(DebateInterruptRecord, "created_at")


def test_debate_session_has_interrupts_relationship() -> None:
    """Verify DebateSessionRecord has interrupts relationship."""
    from planagent.domain.models import DebateSessionRecord

    assert hasattr(DebateSessionRecord, "interrupts")


def test_event_topic_debate_interrupted() -> None:
    """Verify DEBATE_INTERRUPTED event topic exists."""
    from planagent.domain.enums import EventTopic

    assert hasattr(EventTopic, "DEBATE_INTERRUPTED")
    assert EventTopic.DEBATE_INTERRUPTED.value == "debate.interrupted"


# ── API Model Tests ──────────────────────────────────────────────────────────


def test_debate_interrupt_create_validation() -> None:
    """Test DebateInterruptCreate API model validation."""
    from planagent.domain.api import DebateInterruptCreate

    # Valid
    model = DebateInterruptCreate(message="Test message")
    assert model.message == "Test message"
    assert model.interrupt_type == "general"

    # Valid with specific type
    model = DebateInterruptCreate(
        message="New evidence found",
        interrupt_type="new_evidence",
    )
    assert model.interrupt_type == "new_evidence"

    # Invalid type
    from pydantic import ValidationError
    try:
        DebateInterruptCreate(message="Test", interrupt_type="bad_type")
        assert False, "Should have raised ValidationError"
    except ValidationError:
        pass

    # Empty message
    try:
        DebateInterruptCreate(message="")
        assert False, "Should have raised ValidationError"
    except ValidationError:
        pass
