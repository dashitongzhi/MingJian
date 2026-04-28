from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from planagent.config import reset_settings_cache
from planagent.db import reset_database_cache
from planagent.main import create_app
from planagent.services.openai_client import OpenAIService, ReportNarrativePayload


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


class DummyAsyncClient:
    async def close(self) -> None:
        return None


def test_military_simulation_branch_and_report_flow(monkeypatch, tmp_path: Path) -> None:
    database_path = tmp_path / "planagent-phase3.db"
    monkeypatch.setenv("PLANAGENT_DATABASE_URL", build_database_url(database_path))
    monkeypatch.setenv("PLANAGENT_EVENT_BUS_BACKEND", "memory")
    monkeypatch.setenv("PLANAGENT_INLINE_INGEST_DEFAULT", "true")
    monkeypatch.setenv("PLANAGENT_INLINE_SIMULATION_DEFAULT", "true")
    disable_openai(monkeypatch)
    reset_settings_cache()
    reset_database_cache()

    ingest_payload = {
        "requested_by": "phase3-test",
        "items": [
            {
                "source_type": "osint",
                "source_url": "https://example.com/blue-shield-update",
                "title": "Blue Shield Brigade faces supply and drone pressure",
                "content_text": (
                    "Blue Shield Brigade saw a supply convoy disrupted after bridge damage near the river crossing. "
                    "Blue Shield Brigade faced repeated drone strikes near civilian districts during the night. "
                    "Blue Shield Brigade received fresh ISR satellite coverage before a storm reduced mobility across the eastern sector."
                ),
                "published_at": "2026-03-17T09:00:00Z",
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

        simulation_response = client.post("/simulation/runs", json=simulation_payload)
        assert simulation_response.status_code == 201
        baseline_run = simulation_response.json()
        assert baseline_run["domain_id"] == "military"
        assert baseline_run["force_id"] == "blue-shield-brigade"
        assert baseline_run["status"] == "COMPLETED"
        assert baseline_run["summary"]["report_id"]
        assert "mil.supply_resilience" in baseline_run["summary"]["matched_rules"]
        assert "mil.air_defense_rebalance" in baseline_run["summary"]["matched_rules"]

        trace_response = client.get(f"/runs/{baseline_run['id']}/decision-trace")
        assert trace_response.status_code == 200
        trace = trace_response.json()
        assert len(trace) == 4
        assert trace[0]["action_id"] == "open_supply_line"
        assert trace[1]["action_id"] in {"rebalance_air_defense", "secure_objective"}
        assert "enemy response" in trace[0]["why_selected"].lower()
        assert {"objective_control", "supply_network", "enemy_readiness", "enemy_pressure"} <= set(
            trace[0]["actual_effect"]
        )
        final_state = baseline_run["summary"]["final_state"]
        assert {"objective_control", "supply_network", "recovery_capacity", "enemy_readiness", "enemy_pressure"} <= set(
            final_state
        )
        assert baseline_run["summary"]["military_tick_summaries"]
        assert baseline_run["summary"]["military_tick_summaries"][0]["enemy_action_id"]
        assert baseline_run["summary"]["enemy_posture"]["focus"]
        assert baseline_run["summary"]["enemy_order_of_battle"]
        assert baseline_run["summary"]["objective_network"]["routes"]
        assert baseline_run["summary"]["objective_network"]["objectives"]

        geo_assets_response = client.get(f"/runs/{baseline_run['id']}/geo-assets")
        assert geo_assets_response.status_code == 200
        geo_assets = geo_assets_response.json()
        assert len(geo_assets) >= 5
        assert {asset["asset_type"] for asset in geo_assets} >= {
            "supply_hub",
            "civilian_area",
            "isr_node",
            "supply_route",
            "objective_zone",
        }

        shocks_response = client.get(f"/runs/{baseline_run['id']}/external-shocks")
        assert shocks_response.status_code == 200
        shocks = shocks_response.json()
        assert len(shocks) >= 4
        assert {shock["shock_type"] for shock in shocks} >= {
            "supply_disruption",
            "air_attack",
            "isr_window",
            "weather_window",
        }

        scenario_response = client.post(
            f"/scenario/runs/{baseline_run['id']}",
            json={
                "fork_step": 2,
                "tick_count": 2,
                "assumptions": ["Civilian corridors stay open."],
                "decision_deltas": ["Protect civilian zones before any additional maneuver."],
                "state_overrides": {"civilian_risk": 0.72, "logistics_throughput": 0.68},
                "probability_band": "medium-high",
            },
        )
        assert scenario_response.status_code == 201
        branch = scenario_response.json()
        assert branch["branch_id"]
        assert branch["run_id"]
        assert branch["parent_run_id"] == baseline_run["id"]
        assert branch["report_id"]
        assert branch["probability_band"] == "medium-high"
        assert branch["decision_deltas"] == ["Protect civilian zones before any additional maneuver."]
        assert branch["kpi_trajectory"]

        branch_geo_response = client.get(f"/runs/{branch['run_id']}/geo-assets")
        assert branch_geo_response.status_code == 200
        branch_assets = branch_geo_response.json()
        assert any(asset["properties"]["status"] == "at_risk" for asset in branch_assets)

        compare_response = client.get(f"/runs/{baseline_run['id']}/scenario-compare")
        assert compare_response.status_code == 200
        compare_payload = compare_response.json()
        assert compare_payload["baseline_run_id"] == baseline_run["id"]
        assert compare_payload["branch_count"] == 1
        assert compare_payload["branches"][0]["branch_id"] == branch["branch_id"]
        assert {"civilian_risk", "objective_control", "enemy_pressure", "attrition_rate"} <= set(compare_payload["metric_names"])

        report_response = client.get(f"/military/scenarios/{branch['branch_id']}/reports/latest")
        assert report_response.status_code == 200
        report = report_response.json()
        assert report["force_id"] == "blue-shield-brigade"
        assert report["scenario_id"] == branch["branch_id"]
        assert report["sections"]["scenario_tree"]["branch_id"] == branch["branch_id"]
        assert report["sections"]["scenario_compare"]
        assert report["sections"]["geo_map"]["assets"]
        assert report["sections"]["external_shocks"]
        assert report["sections"]["combat_exchange"]
        assert report["sections"]["combat_exchange"][0]["enemy_action_id"]
        assert report["sections"]["objective_network"]["objective_control"] is not None
        assert report["sections"]["objective_network"]["enemy_pressure"] is not None
        assert report["sections"]["objective_network"]["routes"]
        assert report["sections"]["objective_network"]["objectives"]
        assert report["sections"]["objective_network"]["edges"]
        assert report["sections"]["enemy_posture"]["focus"]
        assert report["sections"]["enemy_order_of_battle"]
        assert report["sections"]["geo_map"]["network"]["edges"]
        assert report["sections"]["audit"]["military_use_mode"] == "full_domain"
        assert report["sections"]["audit"]["simulation_only"] is True
        assert "assumptions" in report["sections"]["audit"]

        rules_response = client.post("/admin/rules/reload")
        assert rules_response.status_code == 200
        rules_payload = rules_response.json()
        assert "military" in rules_payload["domains"]
        assert rules_payload["rules_loaded"] >= 9


def test_military_report_uses_report_target_when_configured(monkeypatch, tmp_path: Path) -> None:
    database_path = tmp_path / "planagent-phase3-report-model.db"
    monkeypatch.setenv("PLANAGENT_DATABASE_URL", build_database_url(database_path))
    monkeypatch.setenv("PLANAGENT_EVENT_BUS_BACKEND", "memory")
    monkeypatch.setenv("PLANAGENT_INLINE_INGEST_DEFAULT", "true")
    monkeypatch.setenv("PLANAGENT_INLINE_SIMULATION_DEFAULT", "true")
    disable_openai(monkeypatch)
    monkeypatch.setenv("PLANAGENT_OPENAI_REPORT_API_KEY", "report-key")
    monkeypatch.setenv("PLANAGENT_OPENAI_REPORT_BASE_URL", "https://report.example/v1")

    monkeypatch.setattr(OpenAIService, "_build_client", lambda self, api_key, base_url: DummyAsyncClient() if api_key else None)

    async def fake_enhance_military_report(
        self,
        force_name: str,
        theater: str,
        evidence_statements: list[str],
        actions: list[str],
        leading_indicators: list[dict[str, float]],
        matched_rules: list[str],
        external_shocks: list[dict[str, object]],
        scenario_assumptions: list[str] | None = None,
    ) -> ReportNarrativePayload:
        assert force_name == "Blue Shield Brigade"
        assert theater == "eastern-sector"
        assert external_shocks
        return ReportNarrativePayload(
            executive_summary="Model narrative says readiness recovered while civilian risk stayed visible.",
            strategy_recommendations=[
                "Keep supply restoration paired with corridor protection.",
                "Preserve ISR coverage on civilian approaches.",
            ],
            why_this_happened="The model highlighted the combined effect of matched rules and recurring shocks.",
        )

    monkeypatch.setattr(OpenAIService, "enhance_military_report", fake_enhance_military_report)
    reset_settings_cache()
    reset_database_cache()

    ingest_payload = {
        "requested_by": "phase3-report-model-test",
        "items": [
            {
                "source_type": "osint",
                "source_url": "https://example.com/blue-shield-report-model",
                "title": "Blue Shield Brigade faces supply and drone pressure",
                "content_text": (
                    "Blue Shield Brigade saw a supply convoy disrupted after bridge damage near the river crossing. "
                    "Blue Shield Brigade faced repeated drone strikes near civilian districts during the night. "
                    "Blue Shield Brigade received fresh ISR satellite coverage before a storm reduced mobility across the eastern sector."
                ),
                "published_at": "2026-03-17T09:00:00Z",
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

        simulation_response = client.post("/simulation/runs", json=simulation_payload)
        assert simulation_response.status_code == 201
        baseline_run = simulation_response.json()

        scenario_response = client.post(
            f"/scenario/runs/{baseline_run['id']}",
            json={
                "fork_step": 2,
                "tick_count": 2,
                "assumptions": ["Civilian corridors stay open."],
                "decision_deltas": ["Protect civilian zones before any additional maneuver."],
                "state_overrides": {"civilian_risk": 0.72, "logistics_throughput": 0.68},
                "probability_band": "medium-high",
            },
        )
        assert scenario_response.status_code == 201
        branch = scenario_response.json()

        report_response = client.get(f"/military/scenarios/{branch['branch_id']}/reports/latest")
        assert report_response.status_code == 200
        report = report_response.json()

    assert report["summary"] == "Model narrative says readiness recovered while civilian risk stayed visible."
    assert report["sections"]["strategy_recommendations"] == [
        "Keep supply restoration paired with corridor protection.",
        "Preserve ISR coverage on civilian approaches.",
    ]
    assert report["sections"]["why_this_happened"]["model_narrative"] == (
        "The model highlighted the combined effect of matched rules and recurring shocks."
    )
