"""Tests for LLM decision integration, LLM debate, decision options,
hypotheses, and calibration features."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from planagent.config import Settings
from planagent.domain.enums import ClaimStatus, EventTopic
from planagent.domain.models import Claim
from planagent.events.bus import InMemoryEventBus
from planagent.services.debate import DebateService
from planagent.services.openai_client import DebatePositionPayload
from planagent.services.simulation import SelectedAction, SimulationService
from planagent.simulation.domain_packs import registry
from planagent.simulation.rules import RuleRegistry


# ── LLM Decision Integration ────────────────────────────────────────────────


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


def test_rule_engine_decision_method() -> None:
    service = build_service()
    state = service._resolve_initial_state(registry.get("corporate"), "developer_tools_saas")
    claim = build_claim(
        "Demand growth accelerated after renewal expansion delivered ROI savings.",
        "ev-test",
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
    assert selected.decision_method == "rule_engine"
    assert selected.action_id == "hire"


def test_fallback_random_when_no_rules_match() -> None:
    service = build_service()
    state = service._resolve_initial_state(registry.get("corporate"), "developer_tools_saas")
    selected = asyncio.run(
        service._select_action(
            "corporate",
            state,
            active_claim=None,
            rules=[],
            recent_claims=[],
            action_history=[],
        )
    )
    assert selected.decision_method in ("fallback_random", "rule_engine")
    assert selected.action_id != ""


def test_selected_action_carries_decision_method() -> None:
    action = SelectedAction(
        action_id="hire",
        why_selected="test",
        rule_ids=[],
        evidence_ids=[],
        expected_effect={},
        actual_effect={},
        decision_method="llm_assisted",
    )
    assert action.decision_method == "llm_assisted"


# ── LLM Debate Integration ──────────────────────────────────────────────────


def test_debate_service_llm_method_exists() -> None:
    service = DebateService(
        settings=Settings(),
        event_bus=InMemoryEventBus(),
    )
    assert hasattr(service, "_llm_debate_rounds")
    assert hasattr(service, "_build_assessment_from_llm_rounds")


def test_debate_service_falls_back_without_openai() -> None:
    service = DebateService(
        settings=Settings(),
        event_bus=InMemoryEventBus(),
        openai_service=None,
    )
    result = asyncio.run(
        service._llm_debate_rounds(
            topic="test topic",
            trigger_type="pivot_decision",
            context="test context",
            evidence_ids=["ev-1"],
        )
    )
    assert result is None


def test_build_assessment_from_llm_rounds() -> None:
    from planagent.domain.api import DebateTriggerRequest

    service = DebateService(
        settings=Settings(),
        event_bus=InMemoryEventBus(),
    )
    payload = DebateTriggerRequest(
        topic="test topic",
        trigger_type="pivot_decision",
    )
    rounds = [
        {
            "round_number": 1,
            "role": "advocate",
            "position": "SUPPORT",
            "confidence": 0.8,
            "arguments": [
                {"claim": "strong support", "evidence_ids": ["ev-1"], "reasoning": "test", "strength": "STRONG"},
            ],
            "rebuttals": [],
            "concessions": [],
        },
        {
            "round_number": 1,
            "role": "challenger",
            "position": "OPPOSE",
            "confidence": 0.4,
            "arguments": [
                {"claim": "weak challenge", "evidence_ids": ["ev-1"], "reasoning": "test", "strength": "MODERATE"},
            ],
            "rebuttals": [],
            "concessions": [],
        },
        {
            "round_number": 2,
            "role": "arbitrator",
            "position": "SUPPORT",
            "confidence": 0.85,
            "arguments": [
                {"claim": "advocate wins", "evidence_ids": ["ev-1"], "reasoning": "test", "strength": "STRONG"},
            ],
            "rebuttals": [],
            "concessions": [],
        },
    ]
    assessment = service._build_assessment_from_llm_rounds(
        rounds, ["ev-1"], payload,
    )
    assert assessment.verdict == "ACCEPTED"
    assert assessment.support_confidence == 0.8
    assert assessment.challenge_confidence == 0.4
    assert len(assessment.rounds) == 3
    assert assessment.context_payload.get("debate_method") == "llm"


class RoleRoutingOpenAIStub:
    def __init__(self) -> None:
        self.targets: list[str] = []

    def is_configured(self, target: str) -> bool:
        return target in {"debate_advocate", "debate_challenger", "debate_arbitrator"}

    async def generate_debate_position(self, **kwargs) -> DebatePositionPayload:
        self.targets.append(kwargs["target"])
        role = kwargs["role"]
        position = "CONDITIONAL" if role == "arbitrator" else ("SUPPORT" if role == "advocate" else "OPPOSE")
        return DebatePositionPayload(
            position=position,
            confidence=0.75,
            arguments=[
                {
                    "claim": f"{role} claim",
                    "evidence_ids": ["ev-1"],
                    "reasoning": "test",
                    "strength": "MODERATE",
                }
            ],
        )


def test_llm_debate_uses_role_specific_targets() -> None:
    stub = RoleRoutingOpenAIStub()
    service = DebateService(
        settings=Settings(),
        event_bus=InMemoryEventBus(),
        openai_service=stub,  # type: ignore[arg-type]
    )

    rounds = asyncio.run(
        service._llm_debate_rounds(
            topic="test topic",
            trigger_type="pivot_decision",
            context="test context",
            evidence_ids=["ev-1"],
        )
    )

    assert rounds
    assert {"debate_advocate", "debate_challenger", "debate_arbitrator"} <= set(stub.targets)


# ── Decision Options + Hypotheses API ────────────────────────────────────────


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    from planagent.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_decision_options_and_hypotheses_flow(client) -> None:
    # Create a simulation run first
    sim_resp = await client.post(
        "/simulation/runs",
        json={
            "company_id": "test-options-co",
            "company_name": "Test Options Co",
            "market": "ai",
            "tick_count": 3,
            "actor_template": "ai_model_provider",
        },
    )
    assert sim_resp.status_code == 201
    run_id = sim_resp.json()["id"]

    # Wait briefly for inline execution to complete and options to generate
    import asyncio as aio
    await aio.sleep(0.1)

    # List decision options
    opts_resp = await client.get(f"/runs/{run_id}/options")
    assert opts_resp.status_code == 200
    options = opts_resp.json()
    assert isinstance(options, list)
    # Options should have been auto-generated
    if len(options) > 0:
        assert options[0]["run_id"] == run_id
        assert "title" in options[0]
        assert "confidence" in options[0]
        assert "ranking" in options[0]

    # Create a manual option
    create_opt_resp = await client.post(
        f"/runs/{run_id}/options",
        json={
            "title": "Pivot to enterprise",
            "description": "Shift focus to enterprise customers.",
            "expected_effects": {"market_share": 0.05, "pipeline": 0.1},
            "risks": ["Slower growth initially"],
            "confidence": 0.7,
            "ranking": 1,
        },
    )
    assert create_opt_resp.status_code == 201
    option_id = create_opt_resp.json()["id"]

    # List hypotheses
    hyp_resp = await client.get(f"/runs/{run_id}/hypotheses")
    assert hyp_resp.status_code == 200
    hypotheses = hyp_resp.json()
    assert isinstance(hypotheses, list)

    # Create a hypothesis
    create_hyp_resp = await client.post(
        f"/runs/{run_id}/hypotheses",
        json={
            "prediction": "Market share will increase by 5% within 3 months",
            "time_horizon": "3_months",
            "decision_option_id": option_id,
        },
    )
    assert create_hyp_resp.status_code == 201
    hyp_id = create_hyp_resp.json()["id"]
    assert create_hyp_resp.json()["verification_status"] == "PENDING"

    # Verify the hypothesis
    verify_resp = await client.post(
        f"/hypotheses/{hyp_id}/verify",
        json={
            "verification_status": "CONFIRMED",
            "actual_outcome": "Market share increased by 5.2% as predicted.",
        },
    )
    assert verify_resp.status_code == 200
    assert verify_resp.json()["verification_status"] == "CONFIRMED"
    assert verify_resp.json()["actual_outcome"] is not None
    assert verify_resp.json()["verified_at"] is not None


async def test_calibration_compute(client) -> None:
    resp = await client.post(
        "/calibration/compute",
        json={"domain_id": "corporate"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["domain_id"] == "corporate"
    assert "calibration_score" in data
    assert "total_hypotheses" in data
    assert "rule_accuracy" in data

    # List calibration records
    list_resp = await client.get("/calibration", params={"domain_id": "corporate"})
    assert list_resp.status_code == 200
    records = list_resp.json()
    assert isinstance(records, list)


# ── Evidence Updated Event Topic ────────────────────────────────────────────


def test_evidence_updated_event_topic() -> None:
    assert EventTopic.EVIDENCE_UPDATED.value == "evidence.updated"


def test_in_memory_event_bus_records_dead_letter_topic() -> None:
    bus = InMemoryEventBus()
    asyncio.run(bus.publish_dead_letter("knowledge.extracted", {"error": "boom"}))
    assert bus.events == [
        {"topic": "knowledge.extracted.dlq", "payload": {"error": "boom"}},
    ]


# ── Knowledge Worker Re-evaluation ──────────────────────────────────────────


def test_knowledge_worker_recalculate_confidence() -> None:
    from planagent.workers.knowledge import KnowledgeWorker

    worker = KnowledgeWorker(Settings(), InMemoryEventBus())
    base = 0.6
    # Support raises confidence
    result = worker._recalculate_confidence(base, 2, 0, 0.8, 0.0)
    assert result > base

    # Conflict lowers confidence
    result = worker._recalculate_confidence(base, 0, 2, 0.0, 0.8)
    assert result < base

    # Mixed signals
    result = worker._recalculate_confidence(base, 1, 1, 0.7, 0.5)
    assert abs(result - base) < 0.2
