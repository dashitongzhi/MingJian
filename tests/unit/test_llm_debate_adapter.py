from typing import Any
from types import SimpleNamespace

import pytest

from planagent.config import Settings
from planagent.domain.api import DebateTriggerRequest
from planagent.services.debate.llm import LLMDebateAdapter
from planagent.services.openai_client import DebatePositionPayload


class RoleRoutingOpenAIStub:
    def __init__(self) -> None:
        self.targets: list[str] = []
        self.calls: list[tuple[str, str]] = []

    def is_configured(self, target: str) -> bool:
        return target in {"debate_advocate", "debate_challenger"}

    async def generate_debate_position(self, **kwargs: Any) -> DebatePositionPayload:
        role = str(kwargs["role"])
        target = str(kwargs["target"])
        self.targets.append(target)
        self.calls.append((role, target))
        return DebatePositionPayload(
            position="OPPOSE" if role == "challenger" else "SUPPORT",
            confidence=0.75,
            arguments=[
                {
                    "claim": f"{role} claim",
                    "evidence_ids": ["evidence-1"],
                    "reasoning": "test",
                    "strength": "MODERATE",
                }
            ],
        )


class InterruptPortStub:
    def __init__(self) -> None:
        self.pending = True

    async def get_pending_interrupts(self, session: Any, debate_id: str) -> list[Any]:
        if not self.pending:
            return []
        return [SimpleNamespace(id="interrupt-1")]

    def format_interrupts_for_context(self, interrupts: list[Any]) -> str:
        return "Human analyst requested a logistics check." if interrupts else ""

    async def mark_interrupts_injected(
        self,
        session: Any,
        debate_id: str,
        round_number: int,
    ) -> int:
        self.pending = False
        return 1


class SessionStub:
    async def flush(self) -> None:
        return None


class AgentRegistryStub:
    def get_provider_config(self, role: str) -> dict[str, str] | None:
        if role != "advocate":
            return None
        return {
            "provider_type": "anthropic",
            "api_key": "registry-key",
            "model": "registry-model",
        }


class AnthropicProviderStub:
    parsed: dict[str, Any] | None = None
    calls = 0

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs

    async def generate_json(self, **kwargs: Any) -> tuple[str, dict[str, Any] | None]:
        type(self).calls += 1
        return "{}", type(self).parsed

    async def close(self) -> None:
        return None


@pytest.mark.anyio
async def test_llm_adapter_streams_round_observations_with_role_routing() -> None:
    openai_service = RoleRoutingOpenAIStub()
    adapter = LLMDebateAdapter(
        settings=Settings(_env_file=None),
        openai_service=openai_service,  # type: ignore[arg-type]
        agent_registry=None,
    )

    events = [
        event
        async for event in adapter.stream_rounds(
            topic="Should the posture change?",
            trigger_type="pivot_decision",
            context="Current evidence remains contested.",
            evidence_ids=["evidence-1"],
            debate_mode="fast",
            domain_id="corporate",
            custom_agents=[],
        )
    ]

    assert [event.event for event in events] == [
        "debate_round_start",
        "debate_round_complete",
        "debate_round_start",
        "debate_round_complete",
        "debate_round_start",
        "debate_round_complete",
    ]
    assert {"debate_advocate", "debate_challenger"} <= set(openai_service.targets)


@pytest.mark.anyio
async def test_llm_adapter_returns_no_rounds_without_a_provider() -> None:
    adapter = LLMDebateAdapter(
        settings=Settings(_env_file=None, anthropic_api_key=""),
        openai_service=None,
        agent_registry=None,
    )

    rounds = await adapter.collect_rounds(
        topic="Should the posture change?",
        trigger_type="pivot_decision",
        context="Current evidence remains contested.",
        evidence_ids=["evidence-1"],
        debate_mode="fast",
        domain_id="corporate",
        custom_agents=[],
    )

    assert rounds is None


@pytest.mark.anyio
async def test_llm_adapter_injects_interrupt_before_the_round_starts() -> None:
    adapter = LLMDebateAdapter(
        settings=Settings(_env_file=None),
        openai_service=RoleRoutingOpenAIStub(),  # type: ignore[arg-type]
        agent_registry=None,
    )

    events = [
        event
        async for event in adapter.stream_rounds(
            topic="Should the posture change?",
            trigger_type="pivot_decision",
            context="Current evidence remains contested.",
            evidence_ids=["evidence-1"],
            debate_mode="fast",
            domain_id="corporate",
            custom_agents=[],
            session=SessionStub(),  # type: ignore[arg-type]
            debate_id="debate-1",
            interrupt_port=InterruptPortStub(),
        )
    ]

    assert [event.event for event in events[:3]] == [
        "debate_interrupt_injected",
        "debate_round_start",
        "debate_round_complete",
    ]
    assert events[0].payload["interrupt_ids"] == ["interrupt-1"]


@pytest.mark.anyio
async def test_llm_adapter_prefers_registry_anthropic_configuration(monkeypatch) -> None:
    AnthropicProviderStub.calls = 0
    AnthropicProviderStub.parsed = {
        "position": "SUPPORT",
        "confidence": 0.82,
        "arguments": [
            {
                "claim": "Registry-backed advocate claim",
                "evidence_ids": ["evidence-1"],
                "reasoning": "registry test",
                "strength": "STRONG",
            }
        ],
    }
    monkeypatch.setattr(
        "planagent.services.debate.llm.AnthropicProvider",
        AnthropicProviderStub,
    )
    openai_service = RoleRoutingOpenAIStub()
    adapter = LLMDebateAdapter(
        settings=Settings(_env_file=None),
        openai_service=openai_service,  # type: ignore[arg-type]
        agent_registry=AgentRegistryStub(),
    )

    rounds = await adapter.collect_rounds(
        topic="Should the posture change?",
        trigger_type="pivot_decision",
        context="Current evidence remains contested.",
        evidence_ids=["evidence-1"],
        debate_mode="fast",
        domain_id="corporate",
        custom_agents=[],
    )

    assert rounds is not None
    advocate = next(item for item in rounds if item["role"] == "advocate")
    assert advocate["arguments"][0]["claim"] == "Registry-backed advocate claim"
    assert AnthropicProviderStub.calls == 1
    assert all(role != "advocate" for role, _target in openai_service.calls)


@pytest.mark.anyio
async def test_llm_adapter_falls_back_from_anthropic_to_openai(monkeypatch) -> None:
    AnthropicProviderStub.calls = 0
    AnthropicProviderStub.parsed = None
    monkeypatch.setattr(
        "planagent.services.debate.llm.AnthropicProvider",
        AnthropicProviderStub,
    )
    openai_service = RoleRoutingOpenAIStub()
    adapter = LLMDebateAdapter(
        settings=Settings(
            _env_file=None,
            anthropic_api_key="anthropic-key",
            anthropic_model="anthropic-model",
            debate_advocate_provider="anthropic",
        ),
        openai_service=openai_service,  # type: ignore[arg-type]
        agent_registry=None,
    )

    rounds = await adapter.collect_rounds(
        topic="Should the posture change?",
        trigger_type="pivot_decision",
        context="Current evidence remains contested.",
        evidence_ids=["evidence-1"],
        debate_mode="fast",
        domain_id="corporate",
        custom_agents=[],
    )

    assert rounds is not None
    assert AnthropicProviderStub.calls >= 1
    assert "debate_advocate" in openai_service.targets


@pytest.mark.anyio
async def test_llm_adapter_fallback_rounds_preserve_context_and_cross_examination() -> None:
    adapter = LLMDebateAdapter(
        settings=Settings(_env_file=None, anthropic_api_key=""),
        openai_service=None,
        agent_registry=None,
    )

    events = [
        event
        async for event in adapter.stream_rounds(
            topic="Should MingJian ship monitored recommendations?",
            trigger_type="pivot_decision",
            context=(
                "Subject: MingJian Cloud\n"
                "Evidence: source cursor health changed after refresh\n"
                "Report summary: recommendation timeline updated"
            ),
            evidence_ids=["ev-cursor", "ev-report"],
            debate_mode="fast",
            domain_id="corporate",
            custom_agents=[],
        )
    ]
    rounds = [event.payload["round"] for event in events if event.event == "debate_round_complete"]

    advocate = next(item for item in rounds if item["role"] == "advocate")
    challenger = next(item for item in rounds if item["role"] == "challenger")
    advocate_argument = advocate["arguments"][0]
    assert "MingJian" in advocate_argument["claim"]
    assert advocate_argument["evidence_ids"] == ["ev-cursor", "ev-report"]
    assert advocate_argument["fallback_generated"] is True
    assert any("Subject: MingJian Cloud" in item for item in advocate_argument["context_signals"])
    assert challenger["position"] == "OPPOSE"
    prior_claims = {
        argument["claim"]
        for round_payload in rounds
        if round_payload["round_number"] < challenger["round_number"]
        for argument in round_payload["arguments"]
    }
    assert challenger["rebuttals"][0]["counter"] in prior_claims


@pytest.mark.anyio
async def test_llm_adapter_skips_model_preparation_for_branch_debates() -> None:
    adapter = LLMDebateAdapter(
        settings=Settings(_env_file=None),
        openai_service=None,
        agent_registry=None,
    )

    preparation = await adapter.prepare(
        session=SessionStub(),  # type: ignore[arg-type]
        payload=DebateTriggerRequest(
            run_id="run-1",
            topic="Compare the scenario branch.",
            target_type="branch",
            target_id="branch-1",
        ),
        context_port=object(),  # type: ignore[arg-type]
    )

    assert preparation is None
