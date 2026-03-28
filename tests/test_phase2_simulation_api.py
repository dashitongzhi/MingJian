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
    monkeypatch.setenv("PLANAGENT_OPENAI_REPORT_API_KEY", "")
    monkeypatch.setenv("PLANAGENT_OPENAI_REPORT_BASE_URL", "")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


def test_corporate_simulation_generates_trace_and_report(monkeypatch, tmp_path: Path) -> None:
    database_path = tmp_path / "planagent-phase2.db"
    monkeypatch.setenv("PLANAGENT_DATABASE_URL", build_database_url(database_path))
    monkeypatch.setenv("PLANAGENT_EVENT_BUS_BACKEND", "memory")
    monkeypatch.setenv("PLANAGENT_INLINE_INGEST_DEFAULT", "true")
    monkeypatch.setenv("PLANAGENT_INLINE_SIMULATION_DEFAULT", "true")
    disable_openai(monkeypatch)
    reset_settings_cache()
    reset_database_cache()

    ingest_payload = {
        "requested_by": "phase2-test",
        "items": [
            {
                "source_type": "blog",
                "source_url": "https://example.com/acme-ai-update",
                "title": "Acme AI expands product and feels GPU pressure",
                "content_text": (
                    "Acme AI launched a new inference release across three regions and demand growth "
                    "accelerated among enterprise buyers after the rollout. "
                    "Acme AI faced GPU cost increase across its training clusters, pushing infrastructure "
                    "cost higher and tightening margins."
                ),
                "published_at": "2026-03-17T09:00:00Z",
            }
        ],
    }

    simulation_payload = {
        "company_id": "acme-ai",
        "company_name": "Acme AI",
        "market": "foundation-models",
        "tick_count": 3,
        "actor_template": "ai_model_provider",
    }

    with TestClient(create_app()) as client:
        ingest_response = client.post("/ingest/runs", json=ingest_payload)
        assert ingest_response.status_code == 201

        simulation_response = client.post("/simulation/runs", json=simulation_payload)
        assert simulation_response.status_code == 201
        simulation_run = simulation_response.json()
        assert simulation_run["status"] == "COMPLETED"
        assert simulation_run["summary"]["ticks_completed"] == 3
        assert simulation_run["summary"]["report_id"]
        assert "corp.ship_momentum" in simulation_run["summary"]["matched_rules"]
        assert "corp.cost_pressure" in simulation_run["summary"]["matched_rules"]

        trace_response = client.get(f"/runs/{simulation_run['id']}/decision-trace")
        assert trace_response.status_code == 200
        trace = trace_response.json()
        assert len(trace) == 3
        assert trace[0]["action_id"] == "ship_feature"
        assert trace[1]["action_id"] == "optimize_cost"
        assert trace[0]["policy_rule_ids"] == ["corp.ship_momentum"]

        report_response = client.get("/companies/acme-ai/reports/latest")
        assert report_response.status_code == 200
        report = report_response.json()
        assert report["company_id"] == "acme-ai"
        assert "why_this_happened" in report["sections"]
        assert report["sections"]["why_this_happened"]["rules_hit"]

        rules_response = client.post("/admin/rules/reload")
        assert rules_response.status_code == 200
        rules_payload = rules_response.json()
        assert "corporate" in rules_payload["domains"]
        assert rules_payload["rules_loaded"] >= 4
