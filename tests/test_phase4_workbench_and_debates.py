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


def test_workbench_and_debate_flow(monkeypatch, tmp_path: Path) -> None:
    database_path = tmp_path / "planagent-phase45.db"
    monkeypatch.setenv("PLANAGENT_DATABASE_URL", build_database_url(database_path))
    monkeypatch.setenv("PLANAGENT_EVENT_BUS_BACKEND", "memory")
    monkeypatch.setenv("PLANAGENT_INLINE_INGEST_DEFAULT", "true")
    monkeypatch.setenv("PLANAGENT_INLINE_SIMULATION_DEFAULT", "true")
    disable_openai(monkeypatch)
    reset_settings_cache()
    reset_database_cache()

    ingest_payload = {
        "requested_by": "phase45-test",
        "items": [
            {
                "source_type": "osint",
                "source_url": "https://example.com/blue-shield-phase45",
                "title": "Blue Shield Brigade faces supply and civilian-risk pressure",
                "content_text": (
                    "Blue Shield Brigade saw a supply convoy disrupted after bridge damage near the river crossing. "
                    "Blue Shield Brigade faced repeated drone strikes near civilian districts during the night. "
                    "Blue Shield Brigade received fresh ISR satellite coverage before a storm reduced mobility across the eastern sector."
                ),
                "published_at": "2026-03-20T09:00:00Z",
            },
            {
                "source_type": "note",
                "source_url": "https://example.com/blue-shield-brief",
                "title": "",
                "content_text": "Blue Shield Brigade saw pressure.",
            }
        ],
    }
    simulation_payload = {
        "domain_id": "military",
        "force_id": "blue-shield-brigade",
        "force_name": "Blue Shield Brigade",
        "theater": "eastern-sector",
        "tick_count": 4,
        "actor_template": "brigade",
    }

    with TestClient(create_app()) as client:
        ingest_response = client.post("/ingest/runs", json=ingest_payload)
        assert ingest_response.status_code == 201

        run_response = client.post("/simulation/runs", json=simulation_payload)
        assert run_response.status_code == 201
        run_payload = run_response.json()
        run_id = run_payload["id"]

        debate_response = client.post(
            "/debates/trigger",
            json={
                "run_id": run_id,
                "topic": "Should Blue Shield keep prioritizing supply-line restoration?",
                "trigger_type": "pivot_decision",
                "target_type": "run",
                "context_lines": ["Prioritize readiness recovery without losing civilian protection."],
            },
        )
        assert debate_response.status_code == 201
        debate_payload = debate_response.json()
        assert debate_payload["id"]
        assert debate_payload["topic"].startswith("Should Blue Shield")
        assert debate_payload["verdict"] is not None
        assert len(debate_payload["rounds"]) == 5
        assert debate_payload["verdict"]["verdict"] in {"ACCEPTED", "REJECTED", "CONDITIONAL"}

        second_debate_response = client.post(
            "/debates/trigger",
            json={
                "run_id": run_id,
                "topic": "Should Blue Shield shift ISR coverage toward civilian corridors?",
                "trigger_type": "manual",
                "target_type": "run",
            },
        )
        assert second_debate_response.status_code == 201
        second_debate_payload = second_debate_response.json()
        assert second_debate_payload["id"] != debate_payload["id"]

        debate_detail_response = client.get(f"/debates/{debate_payload['id']}")
        assert debate_detail_response.status_code == 200
        debate_detail = debate_detail_response.json()
        assert debate_detail["id"] == debate_payload["id"]
        assert debate_detail["rounds"][0]["role"] == "advocate"

        run_debates_response = client.get(f"/runs/{run_id}/debates")
        assert run_debates_response.status_code == 200
        run_debates = run_debates_response.json()
        assert len(run_debates) == 2
        assert {item["debate_id"] for item in run_debates} == {
            debate_payload["id"],
            second_debate_payload["id"],
        }

        trace_response = client.get(f"/runs/{run_id}/decision-trace")
        assert trace_response.status_code == 200
        trace = trace_response.json()
        assert trace[-1]["debate_verdict_id"] == debate_payload["id"]

        workbench_response = client.get(f"/runs/{run_id}/workbench")
        assert workbench_response.status_code == 200
        workbench = workbench_response.json()
        assert workbench["run_id"] == run_id
        assert workbench["domain_id"] == "military"
        assert workbench["latest_report_id"]
        assert workbench["review_queue"]
        assert workbench["evidence_graph"]["nodes"]
        assert workbench["evidence_graph"]["edges"]
        assert any(item["event_type"] == "decision" for item in workbench["timeline"])
        assert any(item["event_type"] == "debate" for item in workbench["timeline"])
        assert workbench["geo_map"]["mode"] == "geo"
        assert workbench["geo_map"]["assets"]
        assert workbench["geo_map"]["network"]["routes"]
        assert workbench["geo_map"]["network"]["objectives"]
        assert workbench["geo_map"]["overlays"]["enemy_posture"]["focus"]
        assert workbench["geo_map"]["overlays"]["enemy_order_of_battle"]
        assert workbench["geo_map"]["overlays"]["combat_exchange"]
        assert workbench["scenario_tree"]["baseline_run_id"] == run_id
        assert workbench["scenario_compare"]["baseline_run_id"] == run_id
        assert workbench["scenario_compare"]["branch_count"] == 0
        assert workbench["kpi_comparator"]["metrics"]
        assert {item["debate_id"] for item in workbench["debate_records"]} == {
            debate_payload["id"],
            second_debate_payload["id"],
        }
