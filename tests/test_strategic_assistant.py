from __future__ import annotations

import asyncio
from datetime import timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from planagent.config import reset_settings_cache
from planagent.config import get_settings
from planagent.db import reset_database_cache
from planagent.db import get_database
from planagent.domain.models import StrategicSession
from planagent.domain.models import utc_now
from planagent.events.bus import build_event_bus
from planagent.main import create_app
from planagent.services.openai_client import OpenAIService
from planagent.simulation.rules import get_rule_registry
from planagent.workers.strategic_watch import StrategicWatchWorker


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


def test_console_page_and_assistant_run(monkeypatch, tmp_path: Path) -> None:
    database_path = tmp_path / "planagent-assistant.db"
    monkeypatch.setenv("PLANAGENT_DATABASE_URL", build_database_url(database_path))
    monkeypatch.setenv("PLANAGENT_EVENT_BUS_BACKEND", "memory")
    monkeypatch.setenv("PLANAGENT_INLINE_INGEST_DEFAULT", "true")
    monkeypatch.setenv("PLANAGENT_INLINE_SIMULATION_DEFAULT", "true")
    disable_openai(monkeypatch)
    reset_settings_cache()
    reset_database_cache()

    payload = {
        "topic": (
            "Acme AI launched a new enterprise agent product, customer demand increased, "
            "and infrastructure cost rose after the rollout."
        ),
        "domain_id": "corporate",
        "subject_id": "acme-ai",
        "subject_name": "Acme AI",
        "market": "enterprise-agents",
        "tick_count": 3,
        "auto_fetch_news": False,
        "include_google_news": False,
        "include_reddit": False,
        "include_hacker_news": False,
        "include_x": False,
    }

    with TestClient(create_app()) as client:
        console_response = client.get("/console")
        assert console_response.status_code == 200
        assert "Strategic Console" in console_response.text

        run_response = client.post("/assistant/runs", json=payload)
        assert run_response.status_code == 201
        body = run_response.json()
        assert body["topic"] == payload["topic"]
        assert body["domain_id"] == "corporate"
        assert body["subject_id"] == "acme-ai"
        assert body["subject_name"] == "Acme AI"
        assert body["analysis"]["summary"]
        assert body["ingest_run"]["status"] == "COMPLETED"
        assert body["simulation_run"]["status"] == "COMPLETED"
        assert body["latest_report"]["summary"]
        assert body["debate"]["verdict"]["verdict"] in {"ACCEPTED", "REJECTED", "CONDITIONAL"}
        assert body["panel_discussion"]
        assert body["workbench"]["run_id"] == body["simulation_run"]["id"]

        daily_response = client.post("/assistant/daily-brief", json=payload)
        assert daily_response.status_code == 200
        daily_body = daily_response.json()
        assert daily_body["domain_id"] == "corporate"
        assert daily_body["summary"]


def test_assistant_stream_emits_key_events(monkeypatch, tmp_path: Path) -> None:
    database_path = tmp_path / "planagent-assistant-stream.db"
    monkeypatch.setenv("PLANAGENT_DATABASE_URL", build_database_url(database_path))
    monkeypatch.setenv("PLANAGENT_EVENT_BUS_BACKEND", "memory")
    monkeypatch.setenv("PLANAGENT_INLINE_INGEST_DEFAULT", "true")
    monkeypatch.setenv("PLANAGENT_INLINE_SIMULATION_DEFAULT", "true")
    disable_openai(monkeypatch)
    reset_settings_cache()
    reset_database_cache()

    payload = {
        "topic": (
            "Blue Shield Brigade faced drone strikes near civilian districts and a supply convoy was disrupted."
        ),
        "domain_id": "military",
        "subject_id": "blue-shield-brigade",
        "subject_name": "Blue Shield Brigade",
        "theater": "eastern-sector",
        "tick_count": 3,
        "auto_fetch_news": False,
        "include_google_news": False,
        "include_reddit": False,
        "include_hacker_news": False,
        "include_x": False,
    }

    with TestClient(create_app()) as client:
        with client.stream("POST", "/assistant/stream", json=payload) as response:
            assert response.status_code == 200
            body = "".join(response.iter_text())

    assert "event: step" in body
    assert "event: simulation_run" in body
    assert "event: debate_round" in body
    assert "event: discussion" in body
    assert "event: assistant_result" in body


def test_strategic_session_persists_briefs_and_runs(monkeypatch, tmp_path: Path) -> None:
    database_path = tmp_path / "planagent-assistant-session.db"
    monkeypatch.setenv("PLANAGENT_DATABASE_URL", build_database_url(database_path))
    monkeypatch.setenv("PLANAGENT_EVENT_BUS_BACKEND", "memory")
    monkeypatch.setenv("PLANAGENT_INLINE_INGEST_DEFAULT", "true")
    monkeypatch.setenv("PLANAGENT_INLINE_SIMULATION_DEFAULT", "true")
    disable_openai(monkeypatch)
    reset_settings_cache()
    reset_database_cache()

    payload = {
        "topic": "持续跟踪一家智能体创业公司的商业信号，观察需求、成本和交付能力变化。",
        "domain_id": "corporate",
        "session_name": "创业公司长期跟踪",
        "subject_id": "agent-founder-lab",
        "subject_name": "Agent Founder Lab",
        "market": "enterprise-agents",
        "tenant_id": "founder-lab",
        "preset_id": "agent_startup",
        "tick_count": 3,
        "auto_fetch_news": False,
        "include_google_news": False,
        "include_reddit": False,
        "include_hacker_news": False,
        "include_x": False,
    }

    with TestClient(create_app()) as client:
        create_response = client.post("/assistant/sessions", json=payload)
        assert create_response.status_code == 201
        session_body = create_response.json()
        session_id = session_body["id"]
        assert session_body["name"] == payload["session_name"]
        assert session_body["auto_refresh_enabled"] is True
        assert session_body["refresh_hour_local"] == 9
        assert session_body["next_refresh_at"] is not None

        daily_response = client.post(
            "/assistant/daily-brief",
            json={**payload, "session_id": session_id},
        )
        assert daily_response.status_code == 200

        run_response = client.post(
            "/assistant/runs",
            json={**payload, "session_id": session_id},
        )
        assert run_response.status_code == 201
        assert run_response.json()["session_id"] == session_id

        list_response = client.get("/assistant/sessions", params={"tenant_id": "founder-lab"})
        assert list_response.status_code == 200
        sessions = list_response.json()
        assert sessions
        assert sessions[0]["id"] == session_id
        assert sessions[0]["latest_brief_summary"]
        assert sessions[0]["latest_run_summary"]

        detail_response = client.get(f"/assistant/sessions/{session_id}")
        assert detail_response.status_code == 200
        detail_body = detail_response.json()
        assert detail_body["session"]["id"] == session_id
        assert len(detail_body["daily_briefs"]) == 1
        assert len(detail_body["recent_runs"]) == 1
        assert detail_body["daily_briefs"][0]["analysis"]["summary"]
        assert detail_body["recent_runs"][0]["result"]["session_id"] == session_id


def test_strategic_watch_worker_refreshes_due_session(monkeypatch, tmp_path: Path) -> None:
    database_path = tmp_path / "planagent-watch-worker.db"
    monkeypatch.setenv("PLANAGENT_DATABASE_URL", build_database_url(database_path))
    monkeypatch.setenv("PLANAGENT_EVENT_BUS_BACKEND", "memory")
    monkeypatch.setenv("PLANAGENT_INLINE_INGEST_DEFAULT", "true")
    monkeypatch.setenv("PLANAGENT_INLINE_SIMULATION_DEFAULT", "true")
    disable_openai(monkeypatch)
    reset_settings_cache()
    reset_database_cache()

    payload = {
        "topic": "持续跟踪某支蓝军旅在东部战区的补给与无人机袭扰动态。",
        "domain_id": "military",
        "session_name": "东部战区蓝军旅",
        "subject_id": "blue-shield-brigade",
        "subject_name": "Blue Shield Brigade",
        "theater": "eastern-sector",
        "tenant_id": "ops-lab",
        "tick_count": 3,
        "auto_fetch_news": False,
        "include_google_news": False,
        "include_reddit": False,
        "include_hacker_news": False,
        "include_x": False,
    }

    with TestClient(create_app()) as client:
        create_response = client.post("/assistant/sessions", json=payload)
        assert create_response.status_code == 201
        session_id = create_response.json()["id"]

        async def run_worker_once() -> dict[str, object]:
            database = get_database()
            async with database.session() as session:
                record = await session.get(StrategicSession, session_id)
                assert record is not None
                record.next_refresh_at = utc_now() - timedelta(minutes=1)
                await session.commit()

            settings = get_settings()
            event_bus = build_event_bus(settings)
            openai_service = OpenAIService(settings)
            worker = StrategicWatchWorker(
                settings,
                event_bus,
                get_rule_registry(settings.rules_dir),
                openai_service,
            )
            try:
                return await worker.run_once()
            finally:
                await event_bus.close()
                await openai_service.close()

        result = asyncio.run(run_worker_once())
        assert result["refreshed_sessions"] == 1

        detail_response = client.get(f"/assistant/sessions/{session_id}")
        assert detail_response.status_code == 200
        detail_body = detail_response.json()
        assert len(detail_body["daily_briefs"]) == 1
        assert detail_body["session"]["next_refresh_at"] is not None
