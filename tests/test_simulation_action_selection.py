from __future__ import annotations

import asyncio
from pathlib import Path

from planagent.config import Settings
from planagent.domain.enums import ClaimStatus
from planagent.domain.models import Claim
from planagent.events.bus import InMemoryEventBus
from planagent.services.simulation import SelectedAction, SimulationService
from planagent.simulation.domain_packs import registry
from planagent.simulation.rules import RuleRegistry


def build_service() -> SimulationService:
    return SimulationService(
        settings=Settings(),
        event_bus=InMemoryEventBus(),
        rule_registry=RuleRegistry(Path("rules")),
    )


def build_claim(statement: str, evidence_id: str, confidence: float = 0.9) -> Claim:
    return Claim(
        evidence_item_id=evidence_id,
        subject="test-subject",
        predicate="signals",
        object_text=statement,
        statement=statement,
        confidence=confidence,
        status=ClaimStatus.ACCEPTED.value,
        requires_review=False,
    )


def build_state(domain_id: str, actor_template: str) -> dict[str, float]:
    service = build_service()
    return service._resolve_initial_state(registry.get(domain_id), actor_template)


def test_select_action_aggregates_supporting_rules_for_shared_action() -> None:
    service = build_service()
    state = build_state("corporate", "developer_tools_saas")
    claim = build_claim(
        "Demand growth accelerated after renewal expansion delivered ROI savings and faster support hours.",
        "ev-hire",
    )

    selected = asyncio.run(
        service._select_action(
            "corporate",
            state,
            claim,
            service.rule_registry.get_rules("corporate"),
            recent_claims=[claim],
            action_history=[],
        )
    )

    assert selected.action_id == "hire"
    assert set(selected.rule_ids) == {"corp.hiring_push", "corp.roi_pull"}
    assert selected.evidence_ids == ["ev-hire"]


def test_select_action_uses_state_constraints_before_committing_to_hiring() -> None:
    service = build_service()
    state = build_state("corporate", "developer_tools_saas")
    state["cash"] = 24.0
    state["runway_weeks"] = 18.0

    claim = build_claim("Demand growth accelerated across enterprise buyers.", "ev-demand")
    selected = asyncio.run(
        service._select_action(
            "corporate",
            state,
            claim,
            service.rule_registry.get_rules("corporate"),
            recent_claims=[claim],
            action_history=[],
        )
    )

    assert selected.action_id == "tighten_scope"
    assert selected.rule_ids == []


def test_select_action_penalizes_immediate_repeats_when_fresh_evidence_shifts() -> None:
    service = build_service()
    state = build_state("corporate", "developer_tools_saas")
    platform_claim = build_claim(
        "Microsoft bundled native copilots into existing platform suites, increasing platform pressure.",
        "ev-platform",
    )
    security_claim = build_claim(
        "Enterprise security reviews and procurement checks slowed several pilots.",
        "ev-security",
    )

    selected = asyncio.run(
        service._select_action(
            "corporate",
            state,
            security_claim,
            service.rule_registry.get_rules("corporate"),
            recent_claims=[platform_claim, security_claim],
            action_history=["focus_vertical"],
        )
    )

    assert selected.action_id == "tighten_scope"
    assert selected.rule_ids == ["corp.enterprise_friction"]


def test_corporate_fallback_hires_when_pipeline_outgrows_capacity() -> None:
    service = build_service()
    state = build_state("corporate", "developer_tools_saas")
    state["pipeline"] = 1.24
    state["active_deployments"] = 3.8
    state["implementation_capacity"] = 3.2
    state["support_load"] = 0.56
    state["gross_margin"] = 0.68
    state["runway_weeks"] = 60.0

    selected = asyncio.run(
        service._select_action(
            "corporate",
            state,
            active_claim=None,
            rules=service.rule_registry.get_rules("corporate"),
            recent_claims=[],
            action_history=[],
        )
    )

    assert selected.action_id == "hire"
    assert selected.rule_ids == []
    assert selected.decision_method == "fallback_random"


def test_military_resolution_adds_enemy_response_and_exchange_effects() -> None:
    service = build_service()
    state = build_state("military", "brigade")
    state["logistics_throughput"] = 0.7
    state["supply_network"] = 0.68
    state["objective_control"] = 0.46
    state["enemy_pressure"] = 0.74
    state["enemy_readiness"] = 0.84

    claim = build_claim(
        "Supply convoys were disrupted near the bridge while drone strikes hit the contested district.",
        "ev-mil-outcome",
    )
    selected = SelectedAction(
        action_id="open_supply_line",
        why_selected="Test harness selected the supply action.",
        rule_ids=["mil.supply_resilience"],
        evidence_ids=["ev-mil-outcome"],
        expected_effect={
            "logistics_throughput": 0.14,
            "supply_network": 0.1,
            "ammo": 0.06,
            "readiness": 0.04,
        },
        actual_effect={
            "logistics_throughput": 0.14,
            "supply_network": 0.1,
            "ammo": 0.06,
            "readiness": 0.04,
        },
    )

    resolution = service._military.resolve_military_action_outcome(state, selected, claim, enemy_history=[])

    assert resolution.enemy_action_id in {
        "enemy_probe_supply",
        "enemy_fire_raid",
        "enemy_press_objective",
    }
    assert resolution.actual_effect != selected.actual_effect
    assert {"objective_control", "supply_network", "enemy_readiness", "enemy_pressure", "attrition_rate"} <= set(
        resolution.actual_effect
    )
    assert resolution.fire_balance <= 0.75
    assert resolution.fire_balance >= -0.75
