from __future__ import annotations

import asyncio

from planagent.events.bus import ConsumedEvent, InMemoryEventBus
from planagent.config import Settings
from planagent.services.jarvis import JarvisOrchestrator, JarvisTask
from planagent.simulation.domain_packs import registry
from planagent.simulation.rules import RuleRegistry
from planagent.worker_cli import _retry_or_dead_letter_event


def test_rule_registry_loads_yaml_conditions_and_python_handlers(tmp_path) -> None:
    domain_dir = tmp_path / "energy"
    domain_dir.mkdir()
    (domain_dir / "handlers.py").write_text(
        "\n".join(
            [
                "from planagent.simulation.rules import RuleEffect, rule_handler",
                "",
                "@rule_handler('energy.grid_stress')",
                "def handle_grid_stress(shock, state):",
                "    return [RuleEffect(target='reserve_margin', op='add', value=-0.1)]",
            ]
        ),
        encoding="utf-8",
    )
    (domain_dir / "default_rules.yaml").write_text(
        """
rules:
  - id: energy.grid_stress
    domain: energy
    trigger:
      conditions:
        - field: event_type
          op: eq
          value: grid stress
    action_id: rebalance_load
    effects:
      - target: reserve_margin
        op: add
        value: -0.2
""",
        encoding="utf-8",
    )

    rule_registry = RuleRegistry(tmp_path)
    rules = rule_registry.get_rules("energy")

    assert len(rules) == 1
    assert rules[0].matches("Regional grid stress is rising.")
    assert rules[0].trigger_conditions[0].field == "event_type"
    assert rule_registry.get_handler("energy.grid_stress") is not None


def test_domain_pack_discovery_keeps_builtin_packs_idempotent() -> None:
    before = {pack.domain_id for pack in registry.all()}
    loaded = registry.discover()
    after = {pack.domain_id for pack in registry.all()}

    assert {"corporate", "military"}.issubset(after)
    assert before.issubset(after)
    assert loaded == []


def test_stream_worker_retries_before_dead_letter() -> None:
    async def scenario() -> tuple[list[ConsumedEvent], list[ConsumedEvent]]:
        bus = InMemoryEventBus()
        event = ConsumedEvent(
            topic="raw.ingested",
            message_id="external-1",
            payload={"raw_item_id": "raw-1"},
        )
        await _retry_or_dead_letter_event(
            bus,
            "knowledge-worker",
            "knowledge-worker-test",
            event,
            RuntimeError("temporary failure"),
            max_attempts=3,
            retry_base_seconds=0,
        )
        retried = await bus.consume(["raw.ingested"], "knowledge-worker", "consumer", 10, 0)
        dead_letters = await bus.consume(["raw.ingested.dlq"], "knowledge-worker", "consumer", 10, 0)
        return retried, dead_letters

    retried, dead_letters = asyncio.run(scenario())

    assert len(retried) == 1
    assert retried[0].payload["_worker"]["attempts"] == 2
    assert dead_letters == []


def test_jarvis_retries_failed_targets_before_repair_plan() -> None:
    class FlakyOpenAI:
        def __init__(self) -> None:
            self.calls = 0

        def is_configured(self, target: str) -> bool:
            return True

        async def generate_json_for_target(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("temporary model outage")
            return "", {"status": "ok", "findings": []}

    async def scenario():
        orchestrator = JarvisOrchestrator(Settings(_env_file=None), FlakyOpenAI())  # type: ignore[arg-type]
        return await orchestrator.orchestrate(
            JarvisTask(task_type="analysis", payload={"query": "retry test"})
        )

    result = asyncio.run(scenario())
    step_names = [step.step for step in result.steps]

    assert "validate_primary_retry" in step_names
    assert result.status == "COMPLETED"
    assert result.verdict == "PASS"
