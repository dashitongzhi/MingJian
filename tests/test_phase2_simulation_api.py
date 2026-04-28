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


def test_agent_startup_simulation_handles_platform_pressure_and_roi_signals(monkeypatch, tmp_path: Path) -> None:
    database_path = tmp_path / "planagent-agent-startup.db"
    monkeypatch.setenv("PLANAGENT_DATABASE_URL", build_database_url(database_path))
    monkeypatch.setenv("PLANAGENT_EVENT_BUS_BACKEND", "memory")
    monkeypatch.setenv("PLANAGENT_INLINE_INGEST_DEFAULT", "true")
    monkeypatch.setenv("PLANAGENT_INLINE_SIMULATION_DEFAULT", "true")
    disable_openai(monkeypatch)
    reset_settings_cache()
    reset_database_cache()

    ingest_payload = {
        "requested_by": "agent-startup-template",
        "items": [
            {
                "source_type": "blog",
                "source_url": "https://example.com/agent-market-pressure",
                "title": "Bundled platforms and enterprise friction reshape the agent market",
                "content_text": (
                    "Microsoft bundled native copilots into existing platform suites, increasing platform pressure "
                    "for smaller agent startups. Enterprise security reviews and procurement checks slowed several "
                    "agent pilots across regulated buyers."
                ),
                "published_at": "2026-03-20T09:00:00Z",
            },
            {
                "source_type": "blog",
                "source_url": "https://example.com/agent-proof-points",
                "title": "Reliability work and renewals create a narrower but healthier wedge",
                "content_text": (
                    "The startup paused launches after latency and accuracy issues and redirected the team toward "
                    "reliability improvements. A design partner later signed a renewal after measurable ROI, labor "
                    "savings, and faster case resolution hours."
                ),
                "published_at": "2026-03-21T09:00:00Z",
            },
        ],
    }
    unrelated_payload = {
        "requested_by": "unrelated-corporate-history",
        "items": [
            {
                "source_type": "blog",
                "source_url": "https://example.com/acme-unrelated",
                "title": "Acme AI launches another GPU-heavy release",
                "content_text": (
                    "Acme AI launched another GPU-heavy release and faced a cost increase during the same quarter."
                ),
                "published_at": "2026-03-18T09:00:00Z",
            }
        ],
    }

    simulation_payload = {
        "company_id": "agent-wedge-lab",
        "company_name": "Agent Wedge Lab",
        "market": "enterprise-agents",
        "tick_count": 4,
        "actor_template": "developer_tools_saas",
    }

    with TestClient(create_app()) as client:
        unrelated_response = client.post("/ingest/runs", json=unrelated_payload)
        assert unrelated_response.status_code == 201

        ingest_response = client.post("/ingest/runs", json=ingest_payload)
        assert ingest_response.status_code == 201

        simulation_response = client.post("/simulation/runs", json=simulation_payload)
        assert simulation_response.status_code == 201
        simulation_run = simulation_response.json()
        assert simulation_run["status"] == "COMPLETED"
        assert simulation_run["summary"]["ticks_completed"] == 4
        assert set(simulation_run["summary"]["matched_rules"]) == {
            "corp.platform_squeeze",
            "corp.enterprise_friction",
            "corp.reliability_reset",
            "corp.roi_pull",
        }
        assert {
            "platform_bundling_pressure",
            "enterprise_buying_friction",
            "reliability_incident",
            "validated_roi",
        } <= {
            shock["shock_type"]
            for shock in client.get(f"/runs/{simulation_run['id']}/external-shocks").json()
        }
        assert {
            "pipeline",
            "active_deployments",
            "implementation_capacity",
            "support_load",
            "reliability_debt",
            "gross_margin",
            "nrr",
            "churn_risk",
        } <= set(simulation_run["summary"]["final_state"])

        trace_response = client.get(f"/runs/{simulation_run['id']}/decision-trace")
        assert trace_response.status_code == 200
        trace = trace_response.json()
        assert [record["action_id"] for record in trace] == [
            "focus_vertical",
            "tighten_scope",
            "improve_reliability",
            "hire",
        ]

        report_response = client.get("/companies/agent-wedge-lab/reports/latest")
        assert report_response.status_code == 200
        report = report_response.json()
        assert "strategy_recommendations" in report["sections"]
        assert report["sections"]["why_this_happened"]["rules_hit"]
        assert report["sections"]["startup_kpi_pack"]["preset_id"] == "agent_startup"

        kpi_response = client.get(f"/runs/{simulation_run['id']}/startup-kpis")
        assert kpi_response.status_code == 200
        kpi_pack = kpi_response.json()
        assert kpi_pack["preset_id"] == "agent_startup"
        assert {card["metric_id"] for card in kpi_pack["cards"]} >= {
            "design_partner_capacity",
            "roi_proof",
            "deployment_window",
            "delivery_load",
            "retention_quality",
            "margin_health",
        }
        assert {"pipeline", "support_load", "nrr"} <= {
            item["metric"] for item in report["sections"]["leading_indicators"]
        }


def test_corporate_scenario_branch_compare_and_report_flow(monkeypatch, tmp_path: Path) -> None:
    database_path = tmp_path / "planagent-corporate-scenarios.db"
    monkeypatch.setenv("PLANAGENT_DATABASE_URL", build_database_url(database_path))
    monkeypatch.setenv("PLANAGENT_EVENT_BUS_BACKEND", "memory")
    monkeypatch.setenv("PLANAGENT_INLINE_INGEST_DEFAULT", "true")
    monkeypatch.setenv("PLANAGENT_INLINE_SIMULATION_DEFAULT", "true")
    disable_openai(monkeypatch)
    reset_settings_cache()
    reset_database_cache()

    ingest_payload = {
        "requested_by": "corporate-branch-test",
        "items": [
            {
                "source_type": "blog",
                "source_url": "https://example.com/startup-branch-signals-a",
                "title": "Platforms and enterprise friction squeeze the wedge",
                "content_text": (
                    "Large platforms bundled native copilots into existing suites, increasing platform pressure "
                    "for smaller agent startups. Enterprise security reviews and procurement checks slowed several "
                    "agent pilots across regulated buyers."
                ),
                "published_at": "2026-03-20T09:00:00Z",
            },
            {
                "source_type": "blog",
                "source_url": "https://example.com/startup-branch-signals-b",
                "title": "Reliability work creates renewals and ROI proof",
                "content_text": (
                    "The startup paused launches after latency and accuracy issues and redirected the team toward "
                    "reliability improvements. A design partner later signed a renewal after measurable ROI, labor "
                    "savings, and faster case resolution hours."
                ),
                "published_at": "2026-03-21T09:00:00Z",
            },
        ],
    }
    simulation_payload = {
        "company_id": "branch-agent-lab",
        "company_name": "Branch Agent Lab",
        "market": "enterprise-agents",
        "tick_count": 4,
        "actor_template": "developer_tools_saas",
    }

    with TestClient(create_app()) as client:
        assert client.post("/ingest/runs", json=ingest_payload).status_code == 201

        baseline_response = client.post("/simulation/runs", json=simulation_payload)
        assert baseline_response.status_code == 201
        baseline_run = baseline_response.json()

        scenario_response = client.post(
            f"/scenario/runs/{baseline_run['id']}",
            json={
                "fork_step": 2,
                "tick_count": 2,
                "assumptions": ["Support queue keeps growing while renewals get harder."],
                "decision_deltas": ["Prioritize renewals and service quality over new deployment volume."],
                "state_overrides": {
                    "support_load": 0.66,
                    "reliability_debt": 0.52,
                    "nrr": 0.91,
                    "churn_risk": 0.24,
                },
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
        assert branch["kpi_trajectory"]

        compare_response = client.get(f"/runs/{baseline_run['id']}/scenario-compare")
        assert compare_response.status_code == 200
        compare_payload = compare_response.json()
        assert compare_payload["baseline_run_id"] == baseline_run["id"]
        assert compare_payload["domain_id"] == "corporate"
        assert compare_payload["branch_count"] == 1
        assert compare_payload["baseline_report_id"] == baseline_run["summary"]["report_id"]
        assert compare_payload["baseline_recommendations"]
        assert compare_payload["summary"]
        assert compare_payload["branches"][0]["branch_id"] == branch["branch_id"]
        assert compare_payload["branches"][0]["report_id"] == branch["report_id"]
        assert compare_payload["branches"][0]["recommendation_summary"]
        assert compare_payload["branches"][0]["key_deltas"]
        assert compare_payload["branches"][0]["debate_suggestion"]["target_type"] == "branch"
        assert compare_payload["branches"][0]["debate_suggestion"]["target_id"] == branch["branch_id"]
        assert {"support_load", "nrr", "churn_risk"} <= set(compare_payload["metric_names"])

        report_response = client.get(f"/scenarios/{branch['branch_id']}/reports/latest")
        assert report_response.status_code == 200
        report = report_response.json()
        assert report["company_id"] == "branch-agent-lab"
        assert report["scenario_id"] == branch["branch_id"]
        assert report["sections"]["scenario_tree"]["branch_id"] == branch["branch_id"]
        assert report["sections"]["scenario_compare"]
        assert report["sections"]["why_this_happened"]["scenario_assumptions"] == [
            "Support queue keeps growing while renewals get harder."
        ]

        debate_response = client.post(
            "/debates/trigger",
            json=compare_payload["branches"][0]["debate_suggestion"],
        )
        assert debate_response.status_code == 201
        debate = debate_response.json()
        assert debate["target_type"] == "branch"
        assert debate["target_id"] == branch["branch_id"]
        assert debate["run_id"] == branch["run_id"]
        assert debate["context_payload"]["branch_id"] == branch["branch_id"]
        assert debate["context_payload"]["baseline_run_id"] == baseline_run["id"]

        baseline_workbench_response = client.get(f"/runs/{baseline_run['id']}/workbench")
        assert baseline_workbench_response.status_code == 200
        baseline_workbench = baseline_workbench_response.json()
        assert baseline_workbench["scenario_compare"]["baseline_run_id"] == baseline_run["id"]
        assert baseline_workbench["scenario_compare"]["branch_count"] == 1
        assert baseline_workbench["scenario_compare"]["branches"][0]["branch_id"] == branch["branch_id"]
        assert baseline_workbench["scenario_compare"]["branches"][0]["debate_suggestion"]["target_id"] == branch["branch_id"]

        branch_workbench_response = client.get(f"/runs/{branch['run_id']}/workbench")
        assert branch_workbench_response.status_code == 200
        branch_workbench = branch_workbench_response.json()
        assert branch_workbench["scenario_tree"]["active_branch_id"] == branch["branch_id"]
        assert branch_workbench["scenario_compare"]["baseline_run_id"] == baseline_run["id"]
        assert {item["debate_id"] for item in branch_workbench["debate_records"]} == {debate["id"]}

        search_response = client.post(
            f"/runs/{baseline_run['id']}/scenario-search",
            json={
                "depth": 3,
                "beam_width": 2,
                "tick_count": 2,
                "assumptions": ["Run a compact beam search around renewal pressure."],
            },
        )
        assert search_response.status_code == 201
        searched_branches = search_response.json()
        assert len(searched_branches) == 2
        assert {item["parent_run_id"] for item in searched_branches} == {baseline_run["id"]}
        assert all(item["report_id"] for item in searched_branches)
        assert all("search_depth=3" in item["assumptions"] for item in searched_branches)

        replay_response = client.get(f"/runs/{baseline_run['id']}/replay-package")
        assert replay_response.status_code == 200
        replay = replay_response.json()
        assert replay["run_id"] == baseline_run["id"]
        assert replay["domain_id"] == "corporate"
        assert replay["package"]["run"]["id"] == baseline_run["id"]
        assert replay["package"]["snapshots"]
        assert replay["package"]["decisions"]
        assert replay["package"]["reports"]

        jarvis_response = client.post(
            "/jarvis/runs",
            json={
                "run_id": baseline_run["id"],
                "target_type": "run",
                "target_id": baseline_run["id"],
                "prompt": "Review scenario logic and provenance.",
            },
        )
        assert jarvis_response.status_code == 201
        jarvis = jarvis_response.json()
        assert jarvis["status"] == "COMPLETED"
        assert jarvis["profile_id"] == "plan-agent"
        assert jarvis["result_payload"]["verdict"] == "PASS"
        assert jarvis["result_payload"]["run_status"] == "COMPLETED"

        jarvis_list_response = client.get("/jarvis/runs", params={"run_id": baseline_run["id"]})
        assert jarvis_list_response.status_code == 200
        assert [item["id"] for item in jarvis_list_response.json()] == [jarvis["id"]]


def test_startup_tenant_isolation_keeps_reports_and_claims_separate(monkeypatch, tmp_path: Path) -> None:
    database_path = tmp_path / "planagent-agent-startup-tenants.db"
    monkeypatch.setenv("PLANAGENT_DATABASE_URL", build_database_url(database_path))
    monkeypatch.setenv("PLANAGENT_EVENT_BUS_BACKEND", "memory")
    monkeypatch.setenv("PLANAGENT_INLINE_INGEST_DEFAULT", "true")
    monkeypatch.setenv("PLANAGENT_INLINE_SIMULATION_DEFAULT", "true")
    disable_openai(monkeypatch)
    reset_settings_cache()
    reset_database_cache()

    tenant_startup = {
        "requested_by": "startup-tenant",
        "tenant_id": "startup-lab",
        "preset_id": "agent_startup",
        "items": [
            {
                "source_type": "blog",
                "source_url": "https://example.com/startup-lab/platform",
                "title": "Platforms squeeze generic agent products",
                "content_text": (
                    "Large platforms bundled native copilots into existing suites, raising platform pressure "
                    "for smaller enterprise agent startups. Procurement and security reviews slowed pilots."
                ),
                "published_at": "2026-03-20T09:00:00Z",
            },
            {
                "source_type": "blog",
                "source_url": "https://example.com/startup-lab/roi",
                "title": "Reliability work led to renewals",
                "content_text": (
                    "The startup paused launches after latency and accuracy issues, then focused on reliability. "
                    "A design partner renewed after measurable ROI and case-resolution savings."
                ),
                "published_at": "2026-03-21T09:00:00Z",
            },
        ],
    }
    tenant_history = {
        "requested_by": "history-tenant",
        "tenant_id": "history-lab",
        "items": [
            {
                "source_type": "blog",
                "source_url": "https://example.com/history-lab/release",
                "title": "Shared company ships a broad launch and hits cost pressure",
                "content_text": (
                    "The company launched a broad release for enterprise agents, but GPU cost increased sharply "
                    "across the same quarter."
                ),
                "published_at": "2026-03-18T09:00:00Z",
            }
        ],
    }
    simulation_payload = {
        "company_id": "shared-agent-company",
        "company_name": "Shared Agent Company",
        "market": "enterprise-agents",
        "tick_count": 4,
        "actor_template": "developer_tools_saas",
        "preset_id": "agent_startup",
    }

    with TestClient(create_app()) as client:
        assert client.post("/ingest/runs", json=tenant_history).status_code == 201
        assert client.post("/ingest/runs", json=tenant_startup).status_code == 201

        startup_run = client.post(
            "/simulation/runs",
            json={**simulation_payload, "tenant_id": "startup-lab"},
        )
        assert startup_run.status_code == 201
        startup_payload = startup_run.json()
        assert startup_payload["tenant_id"] == "startup-lab"
        assert set(startup_payload["summary"]["matched_rules"]) == {
            "corp.platform_squeeze",
            "corp.enterprise_friction",
            "corp.reliability_reset",
            "corp.roi_pull",
        }

        history_run = client.post(
            "/simulation/runs",
            json={**simulation_payload, "tenant_id": "history-lab"},
        )
        assert history_run.status_code == 201
        history_payload = history_run.json()
        assert "corp.cost_pressure" in history_payload["summary"]["matched_rules"]
        assert "corp.platform_squeeze" not in history_payload["summary"]["matched_rules"]
        assert "corp.roi_pull" not in history_payload["summary"]["matched_rules"]

        startup_report = client.get(
            "/companies/shared-agent-company/reports/latest",
            params={"tenant_id": "startup-lab"},
        )
        assert startup_report.status_code == 200
        assert startup_report.json()["run_id"] == startup_payload["id"]

        history_report = client.get(
            "/companies/shared-agent-company/reports/latest",
            params={"tenant_id": "history-lab"},
        )
        assert history_report.status_code == 200
        assert history_report.json()["run_id"] == history_payload["id"]

        startup_claims = client.get(
            "/claims",
            params={"tenant_id": "startup-lab", "preset_id": "agent_startup", "limit": 2, "offset": 0},
        )
        assert startup_claims.status_code == 200
        startup_claim_payload = startup_claims.json()
        assert startup_claim_payload
        assert len(startup_claim_payload) <= 2
        assert {item["tenant_id"] for item in startup_claim_payload} == {"startup-lab"}
        assert {item["preset_id"] for item in startup_claim_payload} == {"agent_startup"}

        history_claims = client.get(
            "/claims",
            params={"tenant_id": "history-lab", "limit": 5, "offset": 0},
        )
        assert history_claims.status_code == 200
        assert history_claims.json()
        assert {item["tenant_id"] for item in history_claims.json()} == {"history-lab"}

        startup_evidence = client.get(
            "/evidence",
            params={"tenant_id": "startup-lab", "preset_id": "agent_startup", "limit": 5, "offset": 0},
        )
        assert startup_evidence.status_code == 200
        assert startup_evidence.json()
        assert {item["tenant_id"] for item in startup_evidence.json()} == {"startup-lab"}
        assert {item["preset_id"] for item in startup_evidence.json()} == {"agent_startup"}


def test_agent_startup_preset_api_runs_examples_and_returns_kpis(monkeypatch, tmp_path: Path) -> None:
    database_path = tmp_path / "planagent-agent-startup-preset.db"
    monkeypatch.setenv("PLANAGENT_DATABASE_URL", build_database_url(database_path))
    monkeypatch.setenv("PLANAGENT_EVENT_BUS_BACKEND", "memory")
    monkeypatch.setenv("PLANAGENT_INLINE_INGEST_DEFAULT", "true")
    monkeypatch.setenv("PLANAGENT_INLINE_SIMULATION_DEFAULT", "true")
    disable_openai(monkeypatch)
    reset_settings_cache()
    reset_database_cache()

    with TestClient(create_app()) as client:
        response = client.post(
            "/presets/agent-startup/runs",
            json={
                "requested_by": "preset-test",
                "tenant_id": " Founder Lab 01 ",
                "scenarios": ["baseline", "downside"],
            },
        )
        assert response.status_code == 201
        payload = response.json()
        assert payload["preset_id"] == "agent_startup"
        assert payload["tenant_id"] == "founder-lab-01"
        assert payload["ingest_run"]["tenant_id"] == "founder-lab-01"
        assert payload["ingest_run"]["preset_id"] == "agent_startup"
        assert [item["scenario"] for item in payload["scenarios"]] == ["baseline", "downside"]

        for item in payload["scenarios"]:
            assert item["run"]["tenant_id"] == "founder-lab-01"
            assert item["run"]["preset_id"] == "agent_startup"
            assert item["startup_kpi_pack"]["preset_id"] == "agent_startup"
            assert item["report_path"].endswith("tenant_id=founder-lab-01")
            workbench = client.get(f"/runs/{item['run']['id']}/workbench")
            assert workbench.status_code == 200
            assert workbench.json()["startup_kpi_pack"]["preset_id"] == "agent_startup"
