from __future__ import annotations

import asyncio
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from fastapi.testclient import TestClient

from planagent.config import reset_settings_cache
from planagent.config import get_settings
from planagent.db import reset_database_cache
from planagent.db import get_database
from planagent.domain.models import (
    Hypothesis,
    RawSourceItem,
    RecommendationVersion,
    SourceChangeRecord,
    StrategicBriefRecord,
    StrategicSession,
    WatchRule,
)
from planagent.domain.models import utc_now
from planagent.events.bus import build_event_bus
from planagent.main import create_app
from planagent.services.analysis import AutomatedAnalysisService, SourceFetchBundle
from planagent.services.assistant import StrategicAssistantService
from planagent.services.openai_client import OpenAIService
from planagent.services.workbench import WorkbenchService
from planagent.simulation.rules import get_rule_registry
from planagent.workers.strategic_watch import StrategicWatchWorker
from planagent.workers.watch_ingest import WatchIngestWorker


def build_database_url(path: Path) -> str:
    return f"sqlite+aiosqlite:///{path.resolve().as_posix()}"


def disable_openai(monkeypatch: pytest.MonkeyPatch) -> None:
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


def test_console_page_and_assistant_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
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
        "context": {
            " market ": " APAC ",
            "notes": " Budget is capped at 5 million. ",
        },
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
        assert "market: APAC" in body["analysis"]["findings"][0]
        assert "notes: Budget" in body["analysis"]["findings"][0]
        assert body["analysis"]["summary"]
        assert body["ingest_run"]["status"] == "COMPLETED"
        assert body["simulation_run"]["status"] == "COMPLETED"
        assert body["latest_report"]["summary"]
        assert body["debate"]["verdict"]["verdict"] in {"ACCEPTED", "REJECTED", "CONDITIONAL"}
        assert (
            "User decision context:\n"
            "- market: APAC\n"
            "- notes: Budget is capped at 5 million."
            in body["debate"]["context_payload"]["user_context"]
        )
        assert body["panel_discussion"]
        assert body["workbench"]["run_id"] == body["simulation_run"]["id"]
        assert body["session_id"]
        assert body["workflow"]["version"] == "complete_decision_workflow_v1"
        assert body["workflow"]["first_result_ready"] is True
        assert body["workflow"]["user_can_decide"] is True
        assert body["workflow"]["research_agents"]["agent_count"] >= 0
        assert body["workflow"]["consensus"]["status"] in {
            "broadly_accepted",
            "contested",
            "skipped",
        }
        assert body["workflow"]["recommendation_version"]["version_number"] == 1
        phase_keys = {phase["key"] for phase in body["workflow"]["phases"]}
        assert {
            "evidence_collection",
            "multi_agent_debate",
            "first_recommendation",
            "local_monitoring",
        }.issubset(phase_keys)
        assert body["monitoring"]["mode"] == "community_24h"
        assert body["monitoring"]["watch_rule_id"]

        session_response = client.get(f"/assistant/sessions/{body['session_id']}")
        assert session_response.status_code == 200
        assert session_response.json()["session"]["source_preferences"]["decision_context"] == {
            "market": "APAC",
            "notes": "Budget is capped at 5 million.",
        }

        async def load_analyst_note() -> RawSourceItem:
            database = get_database()
            async with database.session() as session:
                analyst_note = (
                    await session.scalars(
                        select(RawSourceItem).where(
                            RawSourceItem.ingest_run_id == body["ingest_run"]["id"],
                            RawSourceItem.source_type == "analyst_note",
                        )
                    )
                ).one()
                return analyst_note

        analyst_note = asyncio.run(load_analyst_note())
        assert analyst_note.content_text == (
            f"{payload['topic']} Decision context: "
            "- market: APAC - notes: Budget is capped at 5 million."
        )
        assert analyst_note.source_metadata["decision_context"] == {
            "market": "APAC",
            "notes": "Budget is capped at 5 million.",
        }

        source_response = client.get(f"/watch/rules/{body['monitoring']['watch_rule_id']}/sources")
        assert source_response.status_code == 200
        source_types = {item["source_type"] for item in source_response.json()}
        assert {
            "google_news",
            "reddit",
            "hacker_news",
            "github",
            "rss",
            "gdelt",
            "aviation",
        }.issubset(source_types)

        second_run_response = client.post("/assistant/runs", json=payload)
        assert second_run_response.status_code == 201
        second_body = second_run_response.json()
        assert second_body["session_id"] != body["session_id"]
        assert second_body["monitoring"]["watch_rule_id"] != body["monitoring"]["watch_rule_id"]

        versions_response = client.get(f"/assistant/session/{body['session_id']}/recommendations")
        assert versions_response.status_code == 200
        versions = versions_response.json()
        assert versions
        assert versions[0]["trigger_type"] == "initial_result"

        daily_response = client.post("/assistant/daily-brief", json=payload)
        assert daily_response.status_code == 200
        daily_body = daily_response.json()
        assert daily_body["domain_id"] == "corporate"
        assert daily_body["summary"]


def test_assistant_run_rejects_invalid_decision_context(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    database_path = tmp_path / "planagent-assistant-context-validation.db"
    monkeypatch.setenv("PLANAGENT_DATABASE_URL", build_database_url(database_path))
    monkeypatch.setenv("PLANAGENT_EVENT_BUS_BACKEND", "memory")
    disable_openai(monkeypatch)
    reset_settings_cache()
    reset_database_cache()

    invalid_contexts = [
        {f"key-{index}": "value" for index in range(21)},
        {" ": "value"},
        {"k" * 65: "value"},
        {"notes": "x" * 2001},
        {key: "x" * 2000 for key in ("a", "b", "c", "d")},
    ]

    with TestClient(create_app(), raise_server_exceptions=False) as client:
        for context in invalid_contexts:
            response = client.post(
                "/assistant/runs",
                json={
                    "topic": "Evaluate a constrained market launch.",
                    "domain_id": "corporate",
                    "context": context,
                    "auto_fetch_news": False,
                },
            )
            assert response.status_code == 422
            assert any("context" in error["loc"] for error in response.json()["detail"])


def test_assistant_keeps_private_context_out_of_public_search_query(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    database_path = tmp_path / "planagent-assistant-context-query.db"
    monkeypatch.setenv("PLANAGENT_DATABASE_URL", build_database_url(database_path))
    monkeypatch.setenv("PLANAGENT_EVENT_BUS_BACKEND", "memory")
    monkeypatch.setenv("PLANAGENT_INLINE_INGEST_DEFAULT", "true")
    monkeypatch.setenv("PLANAGENT_INLINE_SIMULATION_DEFAULT", "true")
    disable_openai(monkeypatch)
    reset_settings_cache()
    reset_database_cache()

    captured: list[tuple[str, str, dict[str, str]]] = []

    async def capture_public_query(
        self: AutomatedAnalysisService,
        payload,
        query: str,
        domain_id: str,
    ) -> SourceFetchBundle:
        _ = self
        captured.append((query, payload.content, payload.decision_context))
        return SourceFetchBundle(sources=[], steps=[])

    monkeypatch.setattr(
        AutomatedAnalysisService,
        "_fetch_related_sources",
        capture_public_query,
    )

    with TestClient(create_app()) as client:
        response = client.post(
            "/assistant/runs",
            json={
                "topic": "Assess launch",
                "context": {"internal_note": "Project Orchid customer list"},
                "domain_id": "corporate",
                "include_x": False,
            },
        )

    assert response.status_code == 201
    assert captured == [
        (
            "Assess launch",
            "Assess launch",
            {"internal_note": "Project Orchid customer list"},
        )
    ]
    assert "Project Orchid customer list" in response.json()["analysis"]["findings"][0]


def test_assistant_stream_emits_key_events(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
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


def test_assistant_stream_does_not_expose_internal_exception_details(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    database_path = tmp_path / "planagent-assistant-stream-error.db"
    monkeypatch.setenv("PLANAGENT_DATABASE_URL", build_database_url(database_path))
    monkeypatch.setenv("PLANAGENT_EVENT_BUS_BACKEND", "memory")
    disable_openai(monkeypatch)
    reset_settings_cache()
    reset_database_cache()

    async def fail_stream(self, session, payload):
        _ = (self, session, payload)
        if False:
            yield None
        raise RuntimeError("upstream secret sk-should-never-reach-the-client")

    monkeypatch.setattr(StrategicAssistantService, "stream", fail_stream)

    with TestClient(create_app()) as client:
        with client.stream(
            "POST",
            "/assistant/stream",
            json={"topic": "Test safe stream errors", "include_x": False},
        ) as response:
            body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "event: error" in body
    assert "sk-should-never-reach-the-client" not in body
    assert "Stream processing failed" in body


def test_assistant_post_debate_warning_redacts_internal_exception_details(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    database_path = tmp_path / "planagent-assistant-post-debate-error.db"
    monkeypatch.setenv("PLANAGENT_DATABASE_URL", build_database_url(database_path))
    monkeypatch.setenv("PLANAGENT_EVENT_BUS_BACKEND", "memory")
    monkeypatch.setenv("PLANAGENT_INLINE_INGEST_DEFAULT", "true")
    monkeypatch.setenv("PLANAGENT_INLINE_SIMULATION_DEFAULT", "true")
    disable_openai(monkeypatch)
    reset_settings_cache()
    reset_database_cache()

    async def fail_workbench(self, session, run_id):
        _ = (self, session, run_id)
        raise RuntimeError("provider token sk-secret at http://10.0.0.8:6379")

    monkeypatch.setattr(WorkbenchService, "build_run_workbench", fail_workbench)
    payload = {
        "topic": "Test safe post-debate warnings",
        "domain_id": "corporate",
        "subject_id": "safe-warning-test",
        "subject_name": "Safe Warning Test",
        "market": "testing",
        "tick_count": 1,
        "auto_fetch_news": False,
        "include_google_news": False,
        "include_reddit": False,
        "include_hacker_news": False,
        "include_x": False,
    }

    with TestClient(create_app()) as client:
        with client.stream("POST", "/assistant/stream", json=payload) as response:
            body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "post_debate_errors" in body
    assert "Workbench generation failed" in body
    assert "sk-secret" not in body
    assert "10.0.0.8" not in body


def test_strategic_session_persists_briefs_and_runs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
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
        repeated_run = client.post(
            "/assistant/runs",
            json={
                **payload,
                "session_id": session_id,
                "topic": "改写问题表述，但仍属于同一创业公司战略会话。",
            },
        )
        assert repeated_run.status_code == 201
        assert (
            repeated_run.json()["monitoring"]["watch_rule_id"]
            == (run_response.json()["monitoring"]["watch_rule_id"])
        )
        assert (
            repeated_run.json()["monitoring"]["expires_at"]
            == run_response.json()["monitoring"]["expires_at"]
        )

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
        assert len(detail_body["recent_runs"]) == 2
        assert detail_body["daily_briefs"][0]["analysis"]["summary"]
        assert all(
            item["result"]["session_id"] == session_id for item in detail_body["recent_runs"]
        )


def test_daily_brief_does_not_read_hypotheses_from_another_unscoped_session(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "planagent-assistant-session-isolation.db"
    monkeypatch.setenv("PLANAGENT_DATABASE_URL", build_database_url(database_path))
    monkeypatch.setenv("PLANAGENT_EVENT_BUS_BACKEND", "memory")
    monkeypatch.setenv("PLANAGENT_INLINE_INGEST_DEFAULT", "true")
    monkeypatch.setenv("PLANAGENT_INLINE_SIMULATION_DEFAULT", "true")
    disable_openai(monkeypatch)
    reset_settings_cache()
    reset_database_cache()

    source_payload = {
        "topic": "Track the first unscoped company and create its hypotheses.",
        "domain_id": "corporate",
        "subject_id": "unscoped-source",
        "subject_name": "Unscoped Source",
        "market": "ai",
        "tick_count": 1,
        "auto_fetch_news": False,
        "include_google_news": False,
        "include_reddit": False,
        "include_hacker_news": False,
        "include_github": False,
        "include_rss_feeds": False,
        "include_gdelt": False,
        "include_x": False,
    }
    target_payload = {
        **source_payload,
        "topic": "Track a separate unscoped company without importing unrelated hypotheses.",
        "session_name": "Isolated unscoped target",
        "subject_id": "unscoped-target",
        "subject_name": "Unscoped Target",
    }

    with TestClient(create_app()) as client:
        source_response = client.post("/assistant/runs", json=source_payload)
        assert source_response.status_code == 201
        target_response = client.post("/assistant/sessions", json=target_payload)
        assert target_response.status_code == 201
        target_session_id = target_response.json()["id"]
        brief_response = client.post(
            "/assistant/daily-brief",
            json={**target_payload, "session_id": target_session_id},
        )
        assert brief_response.status_code == 200

        async def read_isolation_state() -> tuple[int, list[str]]:
            database = get_database()
            async with database.session() as session:
                hypothesis_count = len(list((await session.scalars(select(Hypothesis))).all()))
                brief = (
                    await session.scalars(
                        select(StrategicBriefRecord)
                        .where(StrategicBriefRecord.session_id == target_session_id)
                        .order_by(StrategicBriefRecord.generated_at.desc())
                        .limit(1)
                    )
                ).first()
                assert brief is not None
                pending = brief.analysis_payload["intelligence_brief"]["pending_hypotheses"]
                return hypothesis_count, pending

        hypothesis_count, pending_hypotheses = asyncio.run(read_isolation_state())

    assert hypothesis_count > 0
    assert pending_hypotheses == []


def test_strategic_watch_worker_refreshes_due_session(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
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
        "context": {"operating region": "Eastern Corridor"},
        "auto_fetch_news": False,
        "include_google_news": False,
        "include_reddit": False,
        "include_hacker_news": False,
        "include_x": False,
    }

    with TestClient(create_app()) as client:
        create_response = client.post("/assistant/sessions", json=payload)
        assert create_response.status_code == 201
        create_body = create_response.json()
        session_id = create_body["id"]
        assert create_body["source_preferences"]["decision_context"] == payload["context"]

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
        assert (
            "operating region: Eastern Corridor"
            in detail_body["daily_briefs"][0]["analysis"]["findings"][0]
        )
        assert len(detail_body["recent_runs"]) == 1
        assert detail_body["recommendation_versions"]
        assert detail_body["recommendation_versions"][0]["trigger_type"] == "scheduled_refresh"
        assert detail_body["session"]["next_refresh_at"] is not None


def test_watch_source_change_recommendation_keeps_provenance(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    database_path = tmp_path / "planagent-source-change-recommendation.db"
    monkeypatch.setenv("PLANAGENT_DATABASE_URL", build_database_url(database_path))
    monkeypatch.setenv("PLANAGENT_EVENT_BUS_BACKEND", "memory")
    monkeypatch.setenv("PLANAGENT_INLINE_INGEST_DEFAULT", "true")
    monkeypatch.setenv("PLANAGENT_INLINE_SIMULATION_DEFAULT", "true")
    disable_openai(monkeypatch)
    reset_settings_cache()
    reset_database_cache()

    payload = {
        "topic": "重大供应链中断迫使团队重新评估扩张计划。",
        "domain_id": "corporate",
        "subject_id": "acme-capacity",
        "subject_name": "Acme Capacity",
        "market": "enterprise-agents",
        "tick_count": 1,
        "auto_fetch_news": False,
        "include_google_news": False,
        "include_reddit": False,
        "include_hacker_news": False,
        "include_github": False,
        "include_rss_feeds": False,
        "include_gdelt": False,
        "include_x": False,
    }

    with TestClient(create_app()) as client:
        initial_response = client.post("/assistant/runs", json=payload)
        assert initial_response.status_code == 201
        initial_body = initial_response.json()
        session_id = initial_body["session_id"]
        rule_id = initial_body["monitoring"]["watch_rule_id"]

        async def run_worker_once() -> tuple[dict[str, object], RecommendationVersion, list[str]]:
            database = get_database()
            async with database.session() as session:
                rule = await session.get(WatchRule, rule_id)
                assert rule is not None
                rule.source_types = []
                rule.next_poll_at = utc_now() - timedelta(minutes=1)
                rule.trigger_threshold = 0.55
                rule.change_significance_threshold = "medium"
                await session.commit()

            settings = get_settings()
            event_bus = build_event_bus(settings)
            openai_service = OpenAIService(settings)
            worker = WatchIngestWorker(
                settings,
                event_bus,
                get_rule_registry(settings.rules_dir),
                openai_service,
            )
            try:
                result = await worker.run_once()
            finally:
                await event_bus.close()
                await openai_service.close()

            async with database.session() as session:
                changes = list(
                    (
                        await session.scalars(
                            select(SourceChangeRecord)
                            .where(SourceChangeRecord.watch_rule_id == rule_id)
                            .order_by(SourceChangeRecord.created_at.asc())
                        )
                    ).all()
                )
                recommendation = (
                    await session.scalars(
                        select(RecommendationVersion)
                        .where(RecommendationVersion.session_id == session_id)
                        .order_by(RecommendationVersion.version_number.desc())
                        .limit(1)
                    )
                ).first()
                assert recommendation is not None
                return result, recommendation, [change.id for change in changes]

        result, recommendation, source_change_ids = asyncio.run(run_worker_once())

        assert result["polled"] == 1
        assert result["failed"] == 0
        assert source_change_ids
        assert recommendation.session_id == session_id
        assert recommendation.watch_rule_id == rule_id
        assert recommendation.trigger_type == "source_change"
        assert recommendation.trigger_source_change_id == source_change_ids[0]
        assert recommendation.source_change_ids == source_change_ids
        assert recommendation.change_summary
