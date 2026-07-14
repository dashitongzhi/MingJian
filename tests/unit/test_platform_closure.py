from __future__ import annotations

import asyncio
from pathlib import Path

from planagent.events.bus import ConsumedEvent, InMemoryEventBus, build_event_envelope
from planagent.domain.enums import EventTopic
from planagent.events.topology import build_stream_topology, validate_stream_topology
from planagent.config import Settings
from planagent.services.jarvis import JarvisOrchestrator, JarvisTask
from planagent.services.platform_topology import PlatformTopologyService
from planagent.simulation.domain_packs import registry
from planagent.simulation.rules import RuleRegistry
from planagent.worker_cli import _retry_or_dead_letter_event
from planagent.workers.ingest import IngestWorker
from planagent.workers.watch_ingest import WatchIngestWorker


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


def test_rule_registry_reload_rolls_back_on_invalid_yaml(tmp_path) -> None:
    domain_dir = tmp_path / "energy"
    domain_dir.mkdir()
    rules_path = domain_dir / "default_rules.yaml"
    rules_path.write_text(
        """
rules:
  - id: energy.grid_stress
    domain: energy
    trigger:
      keywords: [grid]
    action_id: rebalance_load
    effects:
      - target: reserve_margin
        op: add
        value: -0.2
""",
        encoding="utf-8",
    )
    rule_registry = RuleRegistry(tmp_path)
    assert [rule.rule_id for rule in rule_registry.get_rules("energy")] == [
        "energy.grid_stress"
    ]

    rules_path.write_text(
        """
rules:
  - id: energy.broken
    domain: energy
    trigger:
      keywords: [grid]
    effects:
      - op: add
        value: -0.2
""",
        encoding="utf-8",
    )

    try:
        rule_registry.reload()
    except KeyError:
        pass
    else:
        raise AssertionError("invalid rule reload should fail")

    assert [rule.rule_id for rule in rule_registry.get_rules("energy")] == [
        "energy.grid_stress"
    ]


def test_domain_pack_discovery_keeps_builtin_packs_idempotent() -> None:
    before = {pack.domain_id for pack in registry.all()}
    loaded = registry.discover()
    after = {pack.domain_id for pack in registry.all()}

    assert "corporate" in after
    assert "planagent.simulation.domain_packs.military.pack" not in loaded
    assert before.issubset(after)
    assert loaded == []


def test_stream_topology_covers_workers_and_jarvis_repair_topics() -> None:
    topology = {item.topic: item for item in build_stream_topology()}

    assert validate_stream_topology() == []
    assert topology[EventTopic.RAW_INGESTED.value].consumer_group == "knowledge-worker"
    assert topology[EventTopic.RAW_INGESTED.value].dead_letter_stream == "stream:raw.ingested.dlq"
    assert EventTopic.VERIFICATION_FAILED.value in topology
    assert EventTopic.JARVIS_REPAIR_REQUESTED.value in topology


def test_platform_topology_reports_full_runtime_contract(tmp_path) -> None:
    domain_dir = tmp_path / "corporate"
    domain_dir.mkdir()
    (domain_dir / "default_rules.yaml").write_text(
        """
rules:
  - id: corporate.market_shift
    domain: corporate
    trigger:
      keywords: [market]
    action_id: update_recommendation
    effects:
      - target: demand_signal
        op: add
        value: 0.1
""",
        encoding="utf-8",
    )

    async def scenario():
        bus = InMemoryEventBus()
        await bus.set_backpressure_signal(True, "pending work exceeded threshold")
        service = PlatformTopologyService(
            Settings(
                _env_file=None,
                database_url="postgresql+psycopg://planagent:secret@db:5432/planagent",
                source_snapshot_backend="minio",
                minio_endpoint="minio:9000",
                minio_bucket="planagent-snapshots",
            ),
            bus,
            RuleRegistry(tmp_path),
            registry,
        )
        return await service.collect()

    topology = asyncio.run(scenario())

    assert topology.ready is True
    assert topology.database.metadata["expected_extensions"] == ["vector", "postgis", "pg_trgm"]
    assert topology.object_storage.metadata["backend"] == "minio"
    assert topology.event_bus.metadata["backpressure"] == {
        "active": True,
        "reason": "pending work exceeded threshold",
    }
    stream_topics = {item["topic"] for item in topology.event_bus.metadata["streams"]}
    assert EventTopic.JARVIS_REPAIR_REQUESTED.value in stream_topics
    assert topology.rules.metadata["rule_counts"] == {"corporate": 1}
    assert "corporate" in set(topology.domain_packs.metadata["packs"])
    assert "multi_agent_debate" in topology.workflow.metadata["steps"]
    assert topology.workflow.metadata["monitoring_contract"] == "24h_local_window"


def test_extension_points_are_available_for_private_editions() -> None:
    from planagent.extensions import (
        AgentExtensionRegistry,
        NoopNotificationBackend,
        NoopPredictionHooks,
        SourceExtensionRegistry,
    )

    source_registry = SourceExtensionRegistry()
    agent_registry = AgentExtensionRegistry()
    source_registry.register("private_source", object())
    agent_registry.register("private_agent", object())

    assert "private_source" in source_registry.all()
    assert "private_agent" in agent_registry.all()
    assert NoopPredictionHooks().before_reforecast({"topic": "x"}) == {"topic": "x"}
    assert NoopNotificationBackend().send("audit", {"ok": True}) is None


def test_postgres_extension_topology_is_declared_in_init_and_migration() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    init_sql = (repo_root / "docker/postgres/init/001_extensions.sql").read_text(
        encoding="utf-8"
    )
    migration_sql = (repo_root / "migrations/versions/0021_pgvector_embedding.py").read_text(
        encoding="utf-8"
    )

    for extension in ("vector", "postgis", "pg_trgm"):
        assert f"CREATE EXTENSION IF NOT EXISTS {extension}" in init_sql
        assert f"CREATE EXTENSION IF NOT EXISTS {extension}" in migration_sql
    assert "ALTER COLUMN embedding_vector TYPE vector(64)" in migration_sql
    assert "USING hnsw (embedding_vector vector_cosine_ops)" in migration_sql


def test_in_memory_bus_backpressure_signal_round_trips() -> None:
    async def scenario() -> tuple[bool, dict[str, object], bool]:
        bus = InMemoryEventBus()
        await bus.set_backpressure_signal(True, "queue is saturated")
        active = await bus.is_backpressure_active()
        status = await bus.backpressure_status()
        await bus.set_backpressure_signal(False, "queue normalized")
        cleared = await bus.is_backpressure_active()
        return active, status, cleared

    active, status, cleared = asyncio.run(scenario())

    assert active is True
    assert status == {"active": True, "reason": "queue is saturated"}
    assert cleared is False


def test_event_bus_enriches_stream_contract_fields() -> None:
    async def scenario() -> ConsumedEvent:
        bus = InMemoryEventBus()
        await bus.publish(
            EventTopic.RAW_INGESTED.value,
            {
                "source_id": "rss",
                "item_hash": "abc123",
                "tenant_id": "tenant-a",
                "workspace_id": "workspace-a",
                "session_id": "session-a",
            },
        )
        events = await bus.consume(
            [EventTopic.RAW_INGESTED.value],
            "knowledge-worker",
            "consumer",
            10,
            0,
        )
        return events[0]

    event = asyncio.run(scenario())

    assert event.payload["event_id"]
    assert event.payload["correlation_id"]
    assert event.payload["session_id"] == "session-a"
    assert event.payload["edition"] == "cloud"
    assert event.payload["tenant_id"] == "tenant-a"
    assert event.payload["workspace_id"] == "workspace-a"
    assert event.payload["attempt"] == 1
    assert event.payload["created_at"]
    assert event.payload["idempotency_key"] == "rss:abc123"


def test_event_bus_idempotency_key_is_stable_without_generated_correlation() -> None:
    first = build_event_envelope(EventTopic.RAW_INGESTED.value, {"raw_item_id": "raw-1"})
    second = build_event_envelope(EventTopic.RAW_INGESTED.value, {"raw_item_id": "raw-1"})

    assert first["correlation_id"] != second["correlation_id"]
    assert first["idempotency_key"] == second["idempotency_key"]


def test_in_memory_bus_refreshes_backpressure_from_pending_count() -> None:
    async def scenario() -> tuple[dict[str, object], dict[str, object]]:
        bus = InMemoryEventBus()
        await bus.publish(EventTopic.RAW_INGESTED.value, {"raw_item_id": "raw-1"})
        active = await bus.refresh_backpressure(
            topics=[EventTopic.RAW_INGESTED.value],
            group="knowledge-worker",
            pending_threshold=0,
            ttl_seconds=10,
        )
        events = await bus.consume(
            [EventTopic.RAW_INGESTED.value],
            "knowledge-worker",
            "consumer",
            10,
            0,
        )
        await bus.ack(EventTopic.RAW_INGESTED.value, "knowledge-worker", events[0].message_id)
        cleared = await bus.refresh_backpressure(
            topics=[EventTopic.RAW_INGESTED.value],
            group="knowledge-worker",
            pending_threshold=0,
            ttl_seconds=10,
        )
        return active, cleared

    active, cleared = asyncio.run(scenario())

    assert active["active"] is True
    assert active["pending"] == 1
    assert "pending=1 exceeded threshold=0" in str(active["reason"])
    assert cleared == {"active": False, "reason": None, "pending": 0}


def test_ingest_producers_pause_when_event_bus_backpressure_is_active(tmp_path) -> None:
    async def scenario() -> tuple[dict[str, object], dict[str, object]]:
        settings = Settings(_env_file=None, event_bus_backend="memory")
        bus = InMemoryEventBus()
        await bus.set_backpressure_signal(True, "pending work exceeded threshold")
        ingest_result = await IngestWorker(settings, bus).run_once()
        watch_result = await WatchIngestWorker(
            settings,
            bus,
            RuleRegistry(tmp_path / "rules"),
        ).run_once()
        return ingest_result, watch_result

    ingest_result, watch_result = asyncio.run(scenario())

    assert ingest_result == {
        "processed_runs": 0,
        "backpressure_active": True,
        "reason": "event_bus_backpressure_signal",
        "threshold": 1000,
    }
    assert watch_result["claimed_rules"] == 0
    assert watch_result["backpressure_active"] is True
    assert watch_result["reason"] == "event_bus_backpressure_signal"


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
    assert retried[0].payload["attempt"] == 2
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


def test_jarvis_publishes_repair_event_for_verification_findings() -> None:
    class UnconfiguredOpenAI:
        def is_configured(self, target: str) -> bool:
            return False

    async def scenario():
        bus = InMemoryEventBus()
        orchestrator = JarvisOrchestrator(Settings(_env_file=None), UnconfiguredOpenAI(), bus)  # type: ignore[arg-type]
        result = await orchestrator.orchestrate(
            JarvisTask(task_type="analysis", payload={"query": "repair test", "source_count": 0})
        )
        repair_events = await bus.consume(
            [EventTopic.JARVIS_REPAIR_REQUESTED.value],
            "test",
            "consumer",
            10,
            0,
        )
        verification_events = await bus.consume(
            [EventTopic.VERIFICATION_FAILED.value],
            "test",
            "consumer",
            10,
            0,
        )
        return result, repair_events, verification_events

    result, repair_events, verification_events = asyncio.run(scenario())

    assert result.status == "PARTIAL"
    assert result.verdict == "CONDITIONAL_PASS"
    assert len(repair_events) == 1
    assert repair_events[0].payload["repair_actions"][0]["action"] == "configure_target"
    assert len(verification_events) == 1
