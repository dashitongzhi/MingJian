from __future__ import annotations

from datetime import datetime, timezone
import os

from sqlalchemy.engine import make_url

from planagent.config import Settings
from planagent.domain.api import PlatformTopologyComponentRead, PlatformTopologyRead
from planagent.events.topology import build_stream_topology, validate_stream_topology
from planagent.simulation.domain_packs import DomainPackRegistry
from planagent.simulation.rules import RuleRegistry


EXPECTED_POSTGRES_EXTENSIONS = ("vector", "postgis", "pg_trgm")
WORKFLOW_STEPS = (
    "decision_request",
    "multi_source_ingest",
    "knowledge_graph",
    "simulation",
    "multi_agent_debate",
    "first_recommendation",
    "strategic_session",
    "recommendation_version_timeline",
    "scheduled_refresh",
    "material_source_change_refresh",
    "decision_record_feedback",
)


class PlatformTopologyService:
    def __init__(
        self,
        settings: Settings,
        event_bus: object | None,
        rule_registry: RuleRegistry,
        domain_pack_registry: DomainPackRegistry,
        edition: str = "community",
    ) -> None:
        self.settings = settings
        self.event_bus = event_bus
        self.rule_registry = rule_registry
        self.domain_pack_registry = domain_pack_registry
        self.edition = edition

    async def collect(self) -> PlatformTopologyRead:
        issues: list[str] = []
        database = self._database_component(issues)
        object_storage = self._object_storage_component(issues)
        event_bus = await self._event_bus_component(issues)
        rules = self._rules_component(issues)
        domain_packs = self._domain_packs_component(issues)
        workflow = self._workflow_component(issues)

        return PlatformTopologyRead(
            generated_at=datetime.now(timezone.utc),
            ready=not issues,
            edition=self.edition,
            database=database,
            object_storage=object_storage,
            event_bus=event_bus,
            rules=rules,
            domain_packs=domain_packs,
            workflow=workflow,
            issues=issues,
        )

    def _database_component(self, issues: list[str]) -> PlatformTopologyComponentRead:
        url = make_url(self.settings.database_url)
        dialect = url.get_backend_name()
        is_postgres = dialect.startswith("postgresql")
        if not is_postgres:
            issues.append(
                "database is not PostgreSQL; pgvector/PostGIS topology is running in dev fallback"
            )
        return PlatformTopologyComponentRead(
            name="postgres",
            status="configured" if is_postgres else "dev_fallback",
            detail=(
                "PostgreSQL topology expects pgvector, PostGIS, and pg_trgm extensions."
                if is_postgres
                else "Non-PostgreSQL database is allowed for local tests only."
            ),
            metadata={
                "dialect": dialect,
                "driver": url.get_driver_name(),
                "database": url.database,
                "host": url.host,
                "expected_extensions": list(EXPECTED_POSTGRES_EXTENSIONS),
                "vector_dimensions": self.settings.graph_embedding_dimensions,
            },
        )

    def _object_storage_component(self, issues: list[str]) -> PlatformTopologyComponentRead:
        backend = self.settings.source_snapshot_backend.lower()
        if backend not in {"filesystem", "minio"}:
            issues.append(f"unknown source snapshot backend: {backend}")
            status = "invalid"
        elif backend == "filesystem":
            status = "dev_fallback"
        else:
            status = "configured"
        return PlatformTopologyComponentRead(
            name="source_snapshots",
            status=status,
            detail=(
                "MinIO stores immutable source snapshots for replay and recommendation versioning."
                if backend == "minio"
                else "Filesystem source snapshots are enabled for local Community runs."
            ),
            metadata={
                "backend": backend,
                "minio_endpoint": self.settings.minio_endpoint,
                "minio_bucket": self.settings.minio_bucket,
                "minio_secure": self.settings.minio_secure,
                "filesystem_dir": str(self.settings.source_snapshot_dir),
                "retention_days": self.settings.source_snapshot_retention_days,
            },
        )

    async def _event_bus_component(self, issues: list[str]) -> PlatformTopologyComponentRead:
        validation_errors = validate_stream_topology()
        issues.extend(validation_errors)
        backpressure_status = await self._backpressure_status()
        streams = [item.to_dict() for item in build_stream_topology()]
        return PlatformTopologyComponentRead(
            name="redis_streams",
            status="configured" if not validation_errors else "invalid",
            detail="Redis Streams topology covers producers, consumer groups, DLQ, retries, and backpressure.",
            metadata={
                "backend": self.settings.event_bus_backend,
                "redis_url": self._redact_url(self.settings.redis_url),
                "stream_maxlen": self.settings.stream_maxlen,
                "pending_idle_ms": self.settings.stream_pending_idle_ms,
                "retry_base_seconds": self.settings.stream_retry_base_seconds,
                "worker_max_attempts": self.settings.worker_max_attempts,
                "backpressure": backpressure_status,
                "streams": streams,
                "validation_errors": validation_errors,
            },
        )

    async def _backpressure_status(self) -> dict[str, object]:
        if self.event_bus is None:
            return {"active": False, "reason": None}
        status_getter = getattr(self.event_bus, "backpressure_status", None)
        if status_getter is not None:
            return dict(await status_getter())
        active_getter = getattr(self.event_bus, "is_backpressure_active", None)
        if active_getter is not None:
            return {"active": bool(await active_getter()), "reason": None}
        return {"active": False, "reason": None}

    def _rules_component(self, issues: list[str]) -> PlatformTopologyComponentRead:
        domains: list[str] = []
        rule_counts: dict[str, int] = {}
        root = self.rule_registry.rules_root
        if root.exists():
            for candidate in sorted(path.name for path in root.iterdir() if path.is_dir()):
                rules = self.rule_registry.get_rules(candidate)
                if rules:
                    domains.append(candidate)
                    rule_counts[candidate] = len(rules)
        if not domains:
            issues.append("no YAML/Python simulation rules are loaded")
        return PlatformTopologyComponentRead(
            name="rules",
            status="configured" if domains else "missing",
            detail="Rules load from YAML and Python handlers, with hot reload exposed through /admin/rules/reload.",
            metadata={
                "rules_root": str(root),
                "domains": domains,
                "rule_counts": rule_counts,
                "configured_rule_modules": self._configured_modules("PLANAGENT_RULE_MODULES"),
            },
        )

    def _domain_packs_component(self, issues: list[str]) -> PlatformTopologyComponentRead:
        loaded_modules = self.domain_pack_registry.discover()
        packs = sorted(pack.domain_id for pack in self.domain_pack_registry.all())
        expected_builtin = {"corporate"}
        if os.getenv("PLANAGENT_ENABLE_MILITARY_DOMAIN_PACK", "").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }:
            expected_builtin.add("military")
        missing_builtin = sorted(expected_builtin - set(packs))
        for domain_id in missing_builtin:
            issues.append(f"missing built-in domain pack: {domain_id}")
        return PlatformTopologyComponentRead(
            name="domain_packs",
            status="configured" if not missing_builtin else "missing",
            detail="Domain packs are pluginized through registry discovery and configured module imports.",
            metadata={
                "packs": packs,
                "loaded_modules": loaded_modules,
                "configured_domain_pack_modules": self._configured_modules(
                    "PLANAGENT_DOMAIN_PACK_MODULES"
                ),
            },
        )

    def _workflow_component(self, issues: list[str]) -> PlatformTopologyComponentRead:
        if self.edition == "community":
            monitoring_contract = "24h_local_window"
        elif self.edition == "cloud":
            monitoring_contract = "subscription_entitlement_long_running"
        else:
            monitoring_contract = "license_governance_long_running"
        return PlatformTopologyComponentRead(
            name="decision_workflow",
            status="configured",
            detail="User request, multi-source collection, debate, first recommendation, session persistence, and refresh loop are wired.",
            metadata={
                "steps": list(WORKFLOW_STEPS),
                "monitoring_contract": monitoring_contract,
                "recommendation_versions": True,
                "source_change_trigger": True,
                "scheduled_refresh": True,
                "user_feedback": True,
            },
        )

    def _redact_url(self, raw_url: str) -> str:
        url = make_url(raw_url)
        return url.render_as_string(hide_password=True)

    def _configured_modules(self, env_name: str) -> list[str]:
        raw = os.getenv(env_name, "")
        return [item.strip() for item in raw.split(",") if item.strip()]
