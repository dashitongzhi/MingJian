from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from planagent.config import Settings
from planagent.config import reset_settings_cache
from planagent.db import get_database
from planagent.db import reset_database_cache
from planagent.domain.api import SourceSeedInput
from planagent.domain.models import (
    Claim,
    DebateSessionRecord,
    DebateVerdictRecord,
    EvidenceItem,
    IngestRun,
    KnowledgeGraphEdge,
    KnowledgeGraphNode,
    ReviewItem,
    DeadLetterEvent,
    SourceHealth,
)
from planagent.events.bus import InMemoryEventBus
from planagent.main import create_app
from planagent.services.openai_client import (
    EvidenceExtractionPayload,
    ExtractedClaimPayload,
    OpenAIService,
    resolve_openclaw_model_selector,
)
from planagent.services.pipeline import PhaseOnePipelineService
from planagent.workers.graph import GraphWorker
from planagent.workers.ingest import IngestWorker
from planagent.workers.knowledge import KnowledgeWorker
from planagent.workers.review import ReviewWorker


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
    monkeypatch.setenv("PLANAGENT_X_BEARER_TOKEN", "")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


def test_inline_ingest_creates_review_queue_and_promotes_claims(monkeypatch, tmp_path: Path) -> None:
    database_path = tmp_path / "planagent-test.db"
    monkeypatch.setenv("PLANAGENT_DATABASE_URL", build_database_url(database_path))
    monkeypatch.setenv("PLANAGENT_EVENT_BUS_BACKEND", "memory")
    monkeypatch.setenv("PLANAGENT_INLINE_INGEST_DEFAULT", "true")
    disable_openai(monkeypatch)
    reset_settings_cache()
    reset_database_cache()

    payload = {
        "requested_by": "test-analyst",
        "items": [
            {
                "source_type": "rss",
                "source_url": "https://example.com/acme-gpu",
                "title": "Acme ships new GPU orchestration service",
                "content_text": (
                    "Acme shipped a new GPU orchestration service across three regions and "
                    "reduced model training cost by 22 percent after a six-week rollout. "
                    "Costs increase."
                ),
                "published_at": "2026-03-16T08:00:00Z",
            }
        ],
    }

    with TestClient(create_app()) as client:
        ingest_response = client.post("/ingest/runs", json=payload)
        assert ingest_response.status_code == 201
        ingest_run = ingest_response.json()
        assert ingest_run["status"] == "COMPLETED"
        assert ingest_run["summary"]["processed_items"] == 1
        assert ingest_run["summary"]["accepted_claims"] >= 1
        assert ingest_run["summary"]["review_claims"] == 1

        evidence_response = client.get("/evidence")
        claims_response = client.get("/claims")
        events_response = client.get("/events")
        review_items_response = client.get("/review/items")
        snapshots_response = client.get("/sources/snapshots")

        assert evidence_response.status_code == 200
        assert len(evidence_response.json()["items"]) == 1
        assert claims_response.status_code == 200
        assert len(claims_response.json()["items"]) == 2
        assert events_response.status_code == 200
        assert len(events_response.json()["items"]) == 1
        assert review_items_response.status_code == 200
        review_items = review_items_response.json()
        assert len(review_items) == 1
        assert review_items[0]["status"] == "PENDING"
        assert snapshots_response.status_code == 200
        snapshots = snapshots_response.json()
        assert len(snapshots) == 1
        assert snapshots[0]["storage_backend"] == "filesystem"
        assert snapshots[0]["byte_size"] > 0

        accept_response = client.post(
            f"/review/items/{review_items[0]['id']}/accept",
            json={"reviewer_id": "qa", "note": "Promote the short metric claim."},
        )
        assert accept_response.status_code == 200
        assert accept_response.json()["status"] == "ACCEPTED"

        signal_response = client.get("/signals")
        assert signal_response.status_code == 200
        assert len(signal_response.json()["items"]) == 1


def test_queued_ingest_flows_through_ingest_and_knowledge_workers(monkeypatch, tmp_path: Path) -> None:
    database_path = tmp_path / "planagent-queued.db"
    database_url = build_database_url(database_path)
    monkeypatch.setenv("PLANAGENT_DATABASE_URL", database_url)
    monkeypatch.setenv("PLANAGENT_EVENT_BUS_BACKEND", "memory")
    monkeypatch.setenv("PLANAGENT_INLINE_INGEST_DEFAULT", "false")
    disable_openai(monkeypatch)
    reset_settings_cache()
    reset_database_cache()

    payload = {
        "requested_by": "queued-analyst",
        "items": [
            {
                "source_type": "rss",
                "source_url": "https://example.com/queued-acme-gpu",
                "title": "Queued Acme ships new GPU orchestration service",
                "content_text": (
                    "Acme shipped a new GPU orchestration service across three regions and "
                    "reduced model training cost by 22 percent after a six-week rollout. "
                    "Costs increase."
                ),
                "published_at": "2026-03-16T08:00:00Z",
            }
        ],
    }

    with TestClient(create_app()) as client:
        ingest_response = client.post("/ingest/runs", json=payload)
        assert ingest_response.status_code == 201
        ingest_run = ingest_response.json()
        assert ingest_run["status"] == "PENDING"
        assert client.get("/evidence").json()["items"] == []
        assert client.get("/claims").json()["items"] == []
        assert client.get("/review/items").json() == []

    event_bus = InMemoryEventBus()
    settings = Settings(_env_file=None)
    ingest_worker = IngestWorker(settings, event_bus)
    knowledge_worker = KnowledgeWorker(settings, event_bus)

    ingest_result = asyncio.run(ingest_worker.run_once())
    assert ingest_result["processed_runs"] == 1
    assert [e.topic for e in event_bus._events.get("raw.ingested", [])] == ["raw.ingested"]

    async def load_counts() -> tuple[str | None, int, int, int]:
        database = get_database(database_url)
        async with database.session() as session:
            run = await session.get(IngestRun, ingest_run["id"])
            evidence_count = int((await session.scalar(select(func.count()).select_from(EvidenceItem))) or 0)
            claim_count = int((await session.scalar(select(func.count()).select_from(Claim))) or 0)
            review_count = int((await session.scalar(select(func.count()).select_from(ReviewItem))) or 0)
            return (run.status if run is not None else None, evidence_count, claim_count, review_count)

    status, evidence_count, claim_count, review_count = asyncio.run(load_counts())
    assert status == "PROCESSING"
    assert evidence_count == 0
    assert claim_count == 0
    assert review_count == 0

    knowledge_result = asyncio.run(knowledge_worker.run_once())
    assert knowledge_result["processed_items"] == 1
    assert knowledge_result["completed_runs"] == 1
    all_topics = []
    for topic in ["raw.ingested", "evidence.created", "claim.review_requested", "knowledge.extracted"]:
        all_topics.extend([e.topic for e in event_bus._events.get(topic, [])])
    assert all_topics == [
        "raw.ingested",
        "evidence.created",
        "claim.review_requested",
        "knowledge.extracted",
    ]

    status, evidence_count, claim_count, review_count = asyncio.run(load_counts())
    assert status == "COMPLETED"
    assert evidence_count == 1
    assert claim_count == 2
    assert review_count == 1


def test_graph_worker_persists_evidence_claim_graph(monkeypatch, tmp_path: Path) -> None:
    database_path = tmp_path / "planagent-graph.db"
    database_url = build_database_url(database_path)
    monkeypatch.setenv("PLANAGENT_DATABASE_URL", database_url)
    monkeypatch.setenv("PLANAGENT_EVENT_BUS_BACKEND", "memory")
    monkeypatch.setenv("PLANAGENT_INLINE_INGEST_DEFAULT", "true")
    disable_openai(monkeypatch)
    reset_settings_cache()
    reset_database_cache()

    with TestClient(create_app()) as client:
        response = client.post(
            "/ingest/runs",
            json={
                "requested_by": "graph-test",
                "tenant_id": "graph-lab",
                "items": [
                    {
                        "source_type": "rss",
                        "source_url": "https://example.com/graph-acme",
                        "title": "Acme launches agent workflow product",
                        "content_text": (
                            "Acme launched an agent workflow product and increased enterprise "
                            "pipeline by 18 percent."
                        ),
                    }
                ],
            },
        )
        assert response.status_code == 201

    event_bus = InMemoryEventBus()
    graph_worker = GraphWorker(Settings(_env_file=None), event_bus)
    result = asyncio.run(graph_worker.run_once())
    assert result["evidence_nodes_processed"] == 1
    assert result["artifact_nodes_processed"] >= 1

    async def load_graph_counts() -> tuple[int, int, int]:
        database = get_database(database_url)
        async with database.session() as session:
            node_count = int((await session.scalar(select(func.count()).select_from(KnowledgeGraphNode))) or 0)
            edge_count = int((await session.scalar(select(func.count()).select_from(KnowledgeGraphEdge))) or 0)
            embedded_count = int(
                (
                    await session.scalar(
                        select(func.count())
                        .select_from(KnowledgeGraphNode)
                        .where(KnowledgeGraphNode.embedding_model == "hashing-v1")
                    )
                )
                or 0
            )
            return node_count, edge_count, embedded_count

    node_count, edge_count, embedded_count = asyncio.run(load_graph_counts())
    assert node_count >= 3
    assert edge_count >= 2
    assert embedded_count >= 3

    with TestClient(create_app()) as client:
        graph_response = client.get("/knowledge/graph", params={"tenant_id": "graph-lab"})
        assert graph_response.status_code == 200
        graph = graph_response.json()
        assert any(node["node_type"] == "evidence" for node in graph["nodes"])
        assert any(edge["relation_type"] == "supports_claim" for edge in graph["edges"])

        search_response = client.get(
            "/knowledge/search",
            params={"tenant_id": "graph-lab", "q": "agent workflow product", "limit": 5},
        )
        assert search_response.status_code == 200
        search_results = search_response.json()
        assert search_results
        assert search_results[0]["score"] > 0


def test_review_worker_auto_rejects_conflicting_claim_with_accepted_context(monkeypatch, tmp_path: Path) -> None:
    database_path = tmp_path / "planagent-review-worker.db"
    database_url = build_database_url(database_path)
    monkeypatch.setenv("PLANAGENT_DATABASE_URL", database_url)
    monkeypatch.setenv("PLANAGENT_EVENT_BUS_BACKEND", "memory")
    monkeypatch.setenv("PLANAGENT_INLINE_INGEST_DEFAULT", "true")
    disable_openai(monkeypatch)
    reset_settings_cache()
    reset_database_cache()

    accepted_payload = {
        "requested_by": "review-accepted",
        "items": [
            {
                "source_type": "rss",
                "source_url": "https://example.com/acme-cost-rise",
                "title": "Acme GPU pricing outlook",
                "content_text": (
                    "Acme training costs increased sharply in March as GPU prices climbed across three "
                    "regions and supplier quotes rose for emergency capacity buys."
                ),
                "published_at": "2026-03-18T09:00:00Z",
            }
        ],
    }
    conflicting_payload = {
        "requested_by": "review-conflict",
        "items": [
            {
                "source_type": "rss",
                "source_url": "https://example.com/acme-cost-drop",
                "title": "Acme GPU pricing outlook",
                "content_text": "Acme training costs decreased sharply in March.",
            }
        ],
    }

    with TestClient(create_app()) as client:
        first_response = client.post("/ingest/runs", json=accepted_payload)
        assert first_response.status_code == 201
        second_response = client.post("/ingest/runs", json=conflicting_payload)
        assert second_response.status_code == 201

        review_items = client.get("/review/items").json()
        assert len(review_items) == 1
        assert review_items[0]["status"] == "PENDING"

    event_bus = InMemoryEventBus()
    settings = Settings(_env_file=None)
    review_worker = ReviewWorker(settings, event_bus)

    review_result = asyncio.run(review_worker.run_once())
    assert review_result["pending_items"] == 1
    assert review_result["debated_items"] == 1
    assert review_result["auto_rejected"] == 1
    assert review_result["auto_accepted"] == 0
    assert [e.topic for e in event_bus._events.get("debate.triggered", [])] + [e.topic for e in event_bus._events.get("debate.completed", [])] == [
        "debate.triggered",
        "debate.completed",
    ]

    async def load_review_state() -> tuple[str | None, str | None, int, str | None]:
        database = get_database(database_url)
        async with database.session() as session:
            review_item = (
                await session.scalars(select(ReviewItem).order_by(ReviewItem.created_at.desc()).limit(1))
            ).first()
            claim = await session.get(Claim, review_item.claim_id if review_item is not None else "")
            debate_count = int((await session.scalar(select(func.count()).select_from(DebateSessionRecord))) or 0)
            latest_verdict = (
                await session.scalars(select(DebateVerdictRecord).limit(1))
            ).first()
            return (
                review_item.status if review_item is not None else None,
                claim.status if claim is not None else None,
                debate_count,
                latest_verdict.verdict if latest_verdict is not None else None,
            )

    review_status, claim_status, debate_count, verdict = asyncio.run(load_review_state())
    assert review_status == "REJECTED"
    assert claim_status == "REJECTED"
    assert debate_count == 1
    assert verdict == "REJECTED"


def test_review_worker_auto_accepts_corroborated_claim_without_conflict(monkeypatch, tmp_path: Path) -> None:
    database_path = tmp_path / "planagent-review-worker-accept.db"
    database_url = build_database_url(database_path)
    monkeypatch.setenv("PLANAGENT_DATABASE_URL", database_url)
    monkeypatch.setenv("PLANAGENT_EVENT_BUS_BACKEND", "memory")
    monkeypatch.setenv("PLANAGENT_INLINE_INGEST_DEFAULT", "true")
    disable_openai(monkeypatch)
    reset_settings_cache()
    reset_database_cache()

    accepted_payload = {
        "requested_by": "review-accepted",
        "items": [
            {
                "source_type": "rss",
                "source_url": "https://example.com/acme-cost-rise-primary",
                "title": "Acme GPU pricing outlook",
                "content_text": (
                    "Acme training costs increased sharply in March as GPU prices climbed across three "
                    "regions and supplier quotes rose for emergency capacity buys."
                ),
                "published_at": "2026-03-18T09:00:00Z",
            }
        ],
    }
    corroborating_payload = {
        "requested_by": "review-corroborating",
        "items": [
            {
                "source_type": "rss",
                "source_url": "https://example.com/acme-cost-rise-secondary",
                "title": "Acme GPU pricing outlook",
                "content_text": "Acme training costs increased sharply in March.",
            }
        ],
    }

    with TestClient(create_app()) as client:
        first_response = client.post("/ingest/runs", json=accepted_payload)
        assert first_response.status_code == 201
        second_response = client.post("/ingest/runs", json=corroborating_payload)
        assert second_response.status_code == 201

        review_items = client.get("/review/items").json()
        assert len(review_items) == 1
        assert review_items[0]["status"] == "PENDING"

    event_bus = InMemoryEventBus()
    settings = Settings(_env_file=None)
    review_worker = ReviewWorker(settings, event_bus)

    review_result = asyncio.run(review_worker.run_once())
    assert review_result["pending_items"] == 1
    assert review_result["debated_items"] == 1
    assert review_result["auto_accepted"] == 1
    assert review_result["auto_rejected"] == 0
    topics = [e.topic for e in event_bus._events.get("debate.triggered", [])] + [e.topic for e in event_bus._events.get("debate.completed", [])] + [e.topic for e in event_bus._events.get("evidence.created", [])]
    assert topics == [
        "debate.triggered",
        "debate.completed",
        "evidence.created",
    ]

    async def load_review_state() -> tuple[str | None, str | None, int, str | None]:
        database = get_database(database_url)
        async with database.session() as session:
            review_item = (
                await session.scalars(select(ReviewItem).order_by(ReviewItem.created_at.desc()).limit(1))
            ).first()
            claim = await session.get(Claim, review_item.claim_id if review_item is not None else "")
            debate_count = int((await session.scalar(select(func.count()).select_from(DebateSessionRecord))) or 0)
            latest_verdict = (
                await session.scalars(select(DebateVerdictRecord).limit(1))
            ).first()
            return (
                review_item.status if review_item is not None else None,
                claim.status if claim is not None else None,
                debate_count,
                latest_verdict.verdict if latest_verdict is not None else None,
            )

    review_status, claim_status, debate_count, verdict = asyncio.run(load_review_state())
    assert review_status == "ACCEPTED"
    assert claim_status == "ACCEPTED"
    assert debate_count == 1
    assert verdict == "ACCEPTED"


def test_root_and_openai_status_are_available_without_api_key(monkeypatch, tmp_path: Path) -> None:
    database_path = tmp_path / "planagent-root.db"
    monkeypatch.setenv("PLANAGENT_DATABASE_URL", build_database_url(database_path))
    monkeypatch.setenv("PLANAGENT_EVENT_BUS_BACKEND", "memory")
    disable_openai(monkeypatch)
    monkeypatch.setenv("PLANAGENT_OPENAI_PRIMARY_MODEL", "openai/gpt-5.2")
    reset_settings_cache()
    reset_database_cache()

    with TestClient(create_app()) as client:
        root_response = client.get("/")
        assert root_response.status_code == 200
        assert root_response.json()["status"] == "ok"

        status_response = client.get("/admin/openai/status")
        assert status_response.status_code == 200
        payload = status_response.json()
        assert payload["configured"] is False
        assert payload["configured_targets"] == []
        assert payload["primary_configured"] is False
        assert payload["extraction_configured"] is False
        assert payload["x_search_configured"] is False
        assert payload["report_configured"] is False
        assert payload["responses_api"] is True
        assert payload["primary_model"] == "openai/gpt-5.2"
        assert payload["resolved_primary_model"] == "gpt-5.2"
        assert payload["resolved_extraction_model"] == "gpt-5.2"
        assert payload["resolved_x_search_model"] == "gpt-5.2"
        assert payload["api_key_sources"]["primary"] == "unset"
        assert payload["model_sources"]["report"] == "PLANAGENT_OPENAI_PRIMARY_MODEL"
        assert payload["target_diagnostics"]["primary"]["configured"] is False
        assert payload["target_diagnostics"]["primary"]["resolved_model"] == "gpt-5.2"
        assert payload["target_diagnostics"]["report"]["base_url"] is None

        test_response = client.post("/admin/openai/test", json={})
        assert test_response.status_code == 503
        assert "not configured" in test_response.json()["detail"].lower()


def test_openai_status_reports_target_level_inheritance(monkeypatch, tmp_path: Path) -> None:
    database_path = tmp_path / "planagent-openai-routing.db"
    monkeypatch.setenv("PLANAGENT_DATABASE_URL", build_database_url(database_path))
    monkeypatch.setenv("PLANAGENT_EVENT_BUS_BACKEND", "memory")
    disable_openai(monkeypatch)
    monkeypatch.setenv("PLANAGENT_OPENAI_EXTRACTION_API_KEY", "extract-key")
    monkeypatch.setenv("PLANAGENT_OPENAI_EXTRACTION_BASE_URL", "https://extract.example/v1")
    monkeypatch.setenv("PLANAGENT_OPENAI_EXTRACTION_MODEL", "gemini-3.1-pro-preview-search")
    reset_settings_cache()
    reset_database_cache()

    with TestClient(create_app()) as client:
        status_response = client.get("/admin/openai/status")
        assert status_response.status_code == 200
        payload = status_response.json()

    assert payload["configured"] is True
    assert payload["configured_targets"] == ["extraction", "x_search"]
    assert payload["primary_configured"] is False
    assert payload["extraction_configured"] is True
    assert payload["x_search_configured"] is True
    assert payload["report_configured"] is False
    assert payload["resolved_extraction_model"] == "gemini-3.1-pro-preview-search"
    assert payload["resolved_x_search_model"] == "gemini-3.1-pro-preview-search"
    assert payload["model_sources"]["x_search"] == "PLANAGENT_OPENAI_EXTRACTION_MODEL"
    assert payload["api_key_sources"]["extraction"] == "PLANAGENT_OPENAI_EXTRACTION_API_KEY"
    assert payload["api_key_sources"]["x_search"] == "PLANAGENT_OPENAI_EXTRACTION_API_KEY"
    assert payload["base_url_sources"]["x_search"] == "PLANAGENT_OPENAI_EXTRACTION_BASE_URL"
    assert payload["api_key_sources"]["report"] == "unset"
    assert payload["target_diagnostics"]["extraction"]["configured"] is True
    assert payload["target_diagnostics"]["extraction"]["resolved_model"] == "gemini-3.1-pro-preview-search"
    assert payload["target_diagnostics"]["x_search"]["base_url"] == "https://extract.example/v1"


def test_runtime_queue_health_reports_filtered_counts(monkeypatch, tmp_path: Path) -> None:
    database_path = tmp_path / "planagent-runtime-health.db"
    monkeypatch.setenv("PLANAGENT_DATABASE_URL", build_database_url(database_path))
    monkeypatch.setenv("PLANAGENT_EVENT_BUS_BACKEND", "memory")
    monkeypatch.setenv("PLANAGENT_INLINE_INGEST_DEFAULT", "false")
    monkeypatch.setenv("PLANAGENT_INLINE_SIMULATION_DEFAULT", "false")
    disable_openai(monkeypatch)
    reset_settings_cache()
    reset_database_cache()

    inline_payload = {
        "requested_by": "alpha-inline",
        "tenant_id": "alpha-team",
        "preset_id": "agent_startup",
        "execution_mode": "INLINE",
        "items": [
            {
                "source_type": "rss",
                "source_url": "https://example.com/alpha-inline",
                "title": "Alpha ships new GPU orchestration service",
                "content_text": (
                    "Alpha shipped a new GPU orchestration service across three regions and "
                    "reduced model training cost by 22 percent after a six-week rollout. "
                    "Costs increase."
                ),
                "published_at": "2026-03-16T08:00:00Z",
            }
        ],
    }
    alpha_queued_payload = {
        "requested_by": "alpha-queued",
        "tenant_id": "alpha-team",
        "preset_id": "agent_startup",
        "execution_mode": "QUEUED",
        "items": [
            {
                "source_type": "rss",
                "source_url": "https://example.com/alpha-queued",
                "title": "Alpha queued source",
                "content_text": "Alpha queued source says delivery friction increased.",
            }
        ],
    }
    beta_queued_payload = {
        "requested_by": "beta-queued",
        "tenant_id": "beta-team",
        "execution_mode": "QUEUED",
        "items": [
            {
                "source_type": "rss",
                "source_url": "https://example.com/beta-queued",
                "title": "Beta queued source",
                "content_text": "Beta queued source says platform pressure increased.",
            }
        ],
    }

    with TestClient(create_app()) as client:
        assert client.post("/ingest/runs", json=inline_payload).status_code == 201
        assert client.post("/ingest/runs", json=alpha_queued_payload).status_code == 201
        assert client.post("/ingest/runs", json=beta_queued_payload).status_code == 201

        alpha_simulation = client.post(
            "/simulation/runs",
            json={
                "company_id": "alpha-company",
                "company_name": "Alpha Company",
                "market": "enterprise-agents",
                "tick_count": 2,
                "actor_template": "developer_tools_saas",
                "tenant_id": "alpha-team",
                "preset_id": "agent_startup",
                "execution_mode": "QUEUED",
            },
        )
        assert alpha_simulation.status_code == 201
        beta_simulation = client.post(
            "/simulation/runs",
            json={
                "company_id": "beta-company",
                "company_name": "Beta Company",
                "market": "enterprise-agents",
                "tick_count": 2,
                "actor_template": "developer_tools_saas",
                "tenant_id": "beta-team",
                "execution_mode": "QUEUED",
            },
        )
        assert beta_simulation.status_code == 201

        async def seed_operational_health() -> None:
            database = get_database(build_database_url(database_path))
            async with database.session() as session:
                session.add(
                    SourceHealth(
                        source_type="gdelt",
                        status="DEGRADED",
                        consecutive_failures=5,
                        last_error="timeout",
                    )
                )
                session.add(
                    DeadLetterEvent(
                        topic="knowledge.extracted",
                        group_name="graph-worker",
                        consumer_name="graph-worker-test",
                        message_id="1-0",
                        payload={"raw_source_item_id": "raw-test"},
                        error="RuntimeError: boom",
                    )
                )
                await session.commit()

        asyncio.run(seed_operational_health())

        runtime_all = client.get("/admin/runtime/queues")
        assert runtime_all.status_code == 200
        all_payload = runtime_all.json()
        all_queues = {item["queue"]: item for item in all_payload["queues"]}
        assert all_queues["ingest_runs"]["pending"] == 2
        assert all_queues["review_items"]["pending"] == 1
        assert all_queues["simulation_runs"]["pending"] == 2
        assert all_payload["dead_letter_count"] == 1
        assert all_payload["backpressure_active"] is False
        assert all_payload["degraded_sources"] == [
            {
                "source_type": "gdelt",
                "status": "DEGRADED",
                "consecutive_failures": 5,
                "last_error": "timeout",
            }
        ]

        runtime_alpha = client.get(
            "/admin/runtime/queues",
            params={"tenant_id": "Alpha Team", "preset_id": "agent_startup"},
        )
        assert runtime_alpha.status_code == 200
        alpha_payload = runtime_alpha.json()
        alpha_queues = {item["queue"]: item for item in alpha_payload["queues"]}
        assert alpha_payload["tenant_id"] == "alpha-team"
        assert alpha_payload["preset_id"] == "agent_startup"
        assert alpha_queues["ingest_runs"]["pending"] == 1
        assert alpha_queues["review_items"]["pending"] == 1
        assert alpha_queues["simulation_runs"]["pending"] == 1
        assert alpha_queues["raw_source_items"]["pending"] == 0
        assert alpha_payload["review_queue_reasons"] == [
            {
                "queue_reason": "Claim confidence landed in the manual review band.",
                "pending": 1,
                "processing": 0,
                "completed": 0,
                "reclaimable": 0,
            }
        ]


def test_openclaw_style_model_selector_is_normalized() -> None:
    assert resolve_openclaw_model_selector("openai/gpt-5.2") == "gpt-5.2"
    assert resolve_openclaw_model_selector("openai-codex/gpt-5.2") == "gpt-5.2"
    assert resolve_openclaw_model_selector("openai/gpt-5.4") == "gpt-5.4"
    assert resolve_openclaw_model_selector("GPT-5.4") == "gpt-5.4"
    assert resolve_openclaw_model_selector("GPT-5.3-Codex") == "gpt-5.3-codex"
    assert resolve_openclaw_model_selector("gpt-5.2") == "gpt-5.2"


def test_x_source_uses_x_search_target() -> None:
    from planagent.services.pipeline import select_extraction_target

    assert select_extraction_target("x") == "x_search"
    assert select_extraction_target("twitter") == "x_search"
    assert select_extraction_target("tweet") == "x_search"
    assert select_extraction_target("rss") == "extraction"


def test_raw_chat_completion_parser_supports_sse_chunks() -> None:
    service = OpenAIService(Settings(_env_file=None))
    response_id, text = service._parse_raw_chat_completion(
        "\n".join(
            [
                'data: {"id":"abc","choices":[{"delta":{"role":"assistant","content":""}}]}',
                'data: {"id":"abc","choices":[{"delta":{"content":"<think>internal</think>OK"}}]}',
                "data: [DONE]",
            ]
        )
    )
    assert response_id == "abc"
    assert text == "OK"


class DummyEventBus:
    async def publish(self, topic: str, payload: dict[str, object]) -> None:
        return None


class ExtractionOnlyStubOpenAIService:
    def is_configured(self, target: str) -> bool:
        return target == "extraction"

    async def extract_evidence(
        self,
        title: str,
        body_text: str,
        target: str = "extraction",
    ) -> EvidenceExtractionPayload:
        assert target == "extraction"
        return EvidenceExtractionPayload(
            summary=f"Model summary for {title}",
            claims=[
                ExtractedClaimPayload(
                    statement="Acme reduced model training cost by 22 percent.",
                    confidence=0.88,
                    kind="signal",
                    rationale="The sentence directly states the cost reduction.",
                )
            ],
        )


def test_pipeline_uses_extraction_target_without_primary() -> None:
    service = PhaseOnePipelineService(
        Settings(_env_file=None),
        DummyEventBus(),
        ExtractionOnlyStubOpenAIService(),
    )
    summary, candidates = asyncio.run(
        service._extract_claim_candidates(
            SourceSeedInput(
                source_type="rss",
                source_url="https://example.com/acme-cost",
                title="Acme cuts training costs",
                content_text="Acme reduced model training cost by 22 percent after a rollout.",
            ),
            evidence_confidence=0.82,
        )
    )

    assert summary == "Model summary for Acme cuts training costs"
    assert len(candidates) == 1
    assert candidates[0].statement == "Acme reduced model training cost by 22 percent."
    assert candidates[0].kind == "signal"
    assert candidates[0].reasoning == "openai_responses:The sentence directly states the cost reduction."
