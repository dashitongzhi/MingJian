from __future__ import annotations

import hashlib
import math
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from planagent.config import Settings
from planagent.db import get_database
from planagent.domain.enums import EventTopic
from planagent.domain.models import (
    Claim,
    EventRecord,
    EvidenceItem,
    KnowledgeGraphEdge,
    KnowledgeGraphNode,
    Signal,
    Trend,
    utc_now,
)
from planagent.events.bus import EventBus
from planagent.services.pipeline import normalize_text, summarize_text
from planagent.workers.base import Worker, WorkerDescription


class GraphWorker(Worker):
    description = WorkerDescription(
        worker_id="graph-worker",
        summary="Builds a persisted evidence/claim/artifact graph from extracted knowledge.",
        consumes=(EventTopic.KNOWLEDGE_EXTRACTED.value, EventTopic.EVIDENCE_UPDATED.value),
        produces=(),
    )

    def __init__(self, settings: Settings, event_bus: EventBus) -> None:
        self.settings = settings
        self.event_bus = event_bus
        self.worker_instance_id = self.description.worker_id

    async def run_once(self) -> dict[str, object]:
        database = get_database(self.settings.database_url)
        errors: list[str] = []
        async with database.session() as session:
            evidence_count, ev_errors = await self._upsert_evidence_claim_graph(session)
            artifact_count, art_errors = await self._upsert_claim_artifacts(session)
            await session.commit()
            errors = ev_errors + art_errors
        return {
            "evidence_nodes_processed": evidence_count,
            "artifact_nodes_processed": artifact_count,
            "errors": errors,
        }

    # ── Evidence → Claim graph ──────────────────────────────────────────────

    async def _upsert_evidence_claim_graph(self, session: AsyncSession) -> tuple[int, list[str]]:
        evidence_items = list(
            (
                await session.scalars(
                    select(EvidenceItem).order_by(EvidenceItem.updated_at.desc()).limit(500)
                )
            ).all()
        )
        if not evidence_items:
            return 0, []

        evidence_ids = [e.id for e in evidence_items]

        # Batch-load all claims for all evidence items — fixes N+1 per-evidence query
        all_claims = list(
            (
                await session.scalars(
                    select(Claim).where(Claim.evidence_item_id.in_(evidence_ids))
                )
            ).all()
        )
        claims_by_evidence: dict[str, list[Claim]] = {}
        for claim in all_claims:
            claims_by_evidence.setdefault(claim.evidence_item_id, []).append(claim)

        # Collect all node and edge keys up front
        node_keys: set[str] = {self._node_key("evidence", eid) for eid in evidence_ids}
        edge_triples: set[tuple[str, str, str]] = set()
        for claim in all_claims:
            node_keys.add(self._node_key("claim", claim.id))
            edge_triples.add(
                (self._node_key("evidence", claim.evidence_item_id), self._node_key("claim", claim.id), "supports_claim")
            )

        existing_nodes = await self._load_existing_nodes(session, node_keys)
        existing_edges = await self._load_existing_edges(session, edge_triples)

        processed = 0
        errors: list[str] = []
        for evidence in evidence_items:
            try:
                evidence_key = self._node_key("evidence", evidence.id)
                self._upsert_node_via_cache(
                    session, existing_nodes,
                    node_key=evidence_key, label=evidence.title, node_type="evidence",
                    tenant_id=evidence.tenant_id, preset_id=evidence.preset_id,
                    source_table="evidence_items", source_id=evidence.id,
                    metadata={"confidence": evidence.confidence, "source_url": evidence.source_url, "summary": evidence.summary},
                )

                for claim in claims_by_evidence.get(evidence.id, []):
                    claim_key = self._node_key("claim", claim.id)
                    self._upsert_node_via_cache(
                        session, existing_nodes,
                        node_key=claim_key, label=summarize_text(claim.statement, max_length=160),
                        node_type=f"claim:{claim.kind}",
                        tenant_id=claim.tenant_id, preset_id=claim.preset_id,
                        source_table="claims", source_id=claim.id,
                        metadata={"confidence": claim.confidence, "status": claim.status, "requires_review": claim.requires_review, "reasoning": claim.reasoning},
                    )
                    self._upsert_edge_via_cache(
                        session, existing_edges,
                        source_node_key=evidence_key, target_node_key=claim_key,
                        relation_type="supports_claim",
                        tenant_id=evidence.tenant_id, preset_id=evidence.preset_id,
                        metadata={"claim_status": claim.status},
                    )
                processed += 1
            except Exception as exc:
                errors.append(f"evidence:{evidence.id}:{type(exc).__name__}:{exc}")
        return processed, errors

    # ── Claim → Artifact graph ──────────────────────────────────────────────

    async def _upsert_claim_artifacts(self, session: AsyncSession) -> tuple[int, list[str]]:
        # Collect all artifacts across all three types
        rows: list[tuple[str, object, str, str, str | None]] = []
        for artifact_type, model, table_name, type_field in [
            ("signal", Signal, "signals", "signal_type"),
            ("event", EventRecord, "events", "event_type"),
            ("trend", Trend, "trends", "trend_type"),
        ]:
            artifacts = list(
                (
                    await session.scalars(
                        select(model).order_by(model.created_at.desc()).limit(500)
                    )
                ).all()
            )
            for artifact in artifacts:
                rows.append((artifact_type, artifact, table_name, type_field, artifact.claim_id))

        if not rows:
            return 0, []

        node_keys: set[str] = set()
        edge_triples: set[tuple[str, str, str]] = set()
        for artifact_type, artifact, _table_name, _type_field, claim_id in rows:
            node_keys.add(self._node_key(artifact_type, artifact.id))
            if claim_id:
                node_keys.add(self._node_key("claim", claim_id))
                edge_triples.add(
                    (self._node_key("claim", claim_id), self._node_key(artifact_type, artifact.id), f"promoted_to_{artifact_type}")
                )

        existing_nodes = await self._load_existing_nodes(session, node_keys)
        existing_edges = await self._load_existing_edges(session, edge_triples)

        processed = 0
        errors: list[str] = []
        for artifact_type, artifact, table_name, type_field, claim_id in rows:
            try:
                artifact_key = self._node_key(artifact_type, artifact.id)
                self._upsert_node_via_cache(
                    session, existing_nodes,
                    node_key=artifact_key, label=artifact.title, node_type=artifact_type,
                    tenant_id=artifact.tenant_id, preset_id=artifact.preset_id,
                    source_table=table_name, source_id=artifact.id,
                    metadata={"confidence": artifact.confidence, "artifact_type": getattr(artifact, type_field)},
                )
                if claim_id:
                    self._upsert_edge_via_cache(
                        session, existing_edges,
                        source_node_key=self._node_key("claim", claim_id),
                        target_node_key=artifact_key,
                        relation_type=f"promoted_to_{artifact_type}",
                        tenant_id=artifact.tenant_id, preset_id=artifact.preset_id,
                        metadata={"confidence": artifact.confidence},
                    )
                processed += 1
            except Exception as exc:
                errors.append(f"{artifact_type}:{artifact.id}:{type(exc).__name__}:{exc}")
        return processed, errors

    # ── Batch-load helpers ──────────────────────────────────────────────────

    async def _load_existing_nodes(
        self, session: AsyncSession, node_keys: set[str]
    ) -> dict[str, KnowledgeGraphNode]:
        if not node_keys:
            return {}
        rows = list(
            (
                await session.scalars(
                    select(KnowledgeGraphNode).where(KnowledgeGraphNode.node_key.in_(list(node_keys)))
                )
            ).all()
        )
        return {n.node_key: n for n in rows}

    async def _load_existing_edges(
        self, session: AsyncSession, triples: set[tuple[str, str, str]]
    ) -> dict[str, KnowledgeGraphEdge]:
        if not triples:
            return {}
        # Build OR conditions for each (source, target, relation_type) triple
        from sqlalchemy import or_

        clauses = [
            (KnowledgeGraphEdge.source_node_key == s)
            & (KnowledgeGraphEdge.target_node_key == t)
            & (KnowledgeGraphEdge.relation_type == r)
            for s, t, r in triples
        ]
        rows = list(
            (await session.scalars(select(KnowledgeGraphEdge).where(or_(*clauses)))).all()
        )
        result: dict[str, KnowledgeGraphEdge] = {}
        for edge in rows:
            key = self._edge_cache_key(edge.source_node_key, edge.target_node_key, edge.relation_type)
            result[key] = edge
        return result

    # ── Upsert helpers (cache-aware) ────────────────────────────────────────

    def _upsert_node_via_cache(
        self,
        session: AsyncSession,
        cache: dict[str, KnowledgeGraphNode],
        *,
        node_key: str,
        label: str,
        node_type: str,
        tenant_id: str | None,
        preset_id: str | None,
        source_table: str,
        source_id: str,
        metadata: dict,
    ) -> KnowledgeGraphNode:
        node = cache.get(node_key)
        normalized_label = normalize_text(label)[:500]
        if node is None:
            node = KnowledgeGraphNode(
                node_key=node_key, label=normalized_label, node_type=node_type,
                tenant_id=tenant_id, preset_id=preset_id,
                source_table=source_table, source_id=source_id,
                embedding=self._embed_text(f"{node_type} {label}", self.settings.graph_embedding_dimensions),
                embedding_model="hashing-v1", node_metadata=metadata,
            )
            session.add(node)
            cache[node_key] = node
            return node

        node.label = normalized_label
        node.node_type = node_type
        node.tenant_id = tenant_id
        node.preset_id = preset_id
        node.source_table = source_table
        node.source_id = source_id
        node.embedding = self._embed_text(f"{node_type} {label}", self.settings.graph_embedding_dimensions)
        node.embedding_model = "hashing-v1"
        node.node_metadata = metadata
        node.updated_at = utc_now()
        return node

    def _upsert_edge_via_cache(
        self,
        session: AsyncSession,
        cache: dict[str, KnowledgeGraphEdge],
        *,
        source_node_key: str,
        target_node_key: str,
        relation_type: str,
        tenant_id: str | None,
        preset_id: str | None,
        metadata: dict,
    ) -> KnowledgeGraphEdge:
        key = self._edge_cache_key(source_node_key, target_node_key, relation_type)
        edge = cache.get(key)
        if edge is None:
            edge = KnowledgeGraphEdge(
                source_node_key=source_node_key, target_node_key=target_node_key,
                relation_type=relation_type, tenant_id=tenant_id, preset_id=preset_id,
                edge_metadata=metadata,
            )
            session.add(edge)
            cache[key] = edge
            return edge

        edge.tenant_id = tenant_id
        edge.preset_id = preset_id
        edge.edge_metadata = metadata
        return edge

    def _edge_cache_key(self, source_node_key: str, target_node_key: str, relation_type: str) -> str:
        return f"{source_node_key}->{target_node_key}:{relation_type}"

    def _node_key(self, node_type: str, source_id: str) -> str:
        return f"{node_type}:{source_id}"

    def _embed_text(self, value: str, dimensions: int) -> list[float]:
        return embed_query(value, dimensions)


def embed_query(value: str, dimensions: int) -> list[float]:
    dims = max(8, dimensions)
    vector = [0.0 for _ in range(dims)]
    for token in re.findall(r"[a-z0-9一-鿿]+", normalize_text(value).lower()):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dims
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign
    norm = math.sqrt(sum(item * item for item in vector)) or 1.0
    return [round(item / norm, 6) for item in vector]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    size = min(len(left), len(right))
    return sum(left[i] * right[i] for i in range(size))


_PG_SIMILARITY_SQL = """
WITH expanded AS (
  SELECT n.id, n.node_key, n.label, n.node_type, n.node_metadata, n.embedding,
    SUM((a.elem)::float * (b.elem)::float) AS dot_product,
    SQRT(SUM((a.elem)::float * (a.elem)::float)) AS node_norm
  FROM knowledge_graph_nodes n,
    jsonb_array_elements(n.embedding::jsonb) WITH ORDINALITY a(elem, idx)
  CROSS JOIN unnest(:query_vector::float[]) WITH ORDINALITY b(elem, idx)
  WHERE a.idx = b.idx
  GROUP BY n.id
)
SELECT node_key, label, node_type, node_metadata,
       dot_product / GREATEST(node_norm * :query_norm, 1e-10) AS score
FROM expanded
ORDER BY score DESC
LIMIT :limit
"""


async def search_nodes_sql(
    session, query_vector: list[float], tenant_id: str | None, limit: int
) -> list[dict]:
    """Run similarity search in the database layer. Falls back to Python for SQLite."""
    from sqlalchemy import text
    from planagent.domain.models import KnowledgeGraphNode

    engine = session.get_bind()
    if engine.dialect.name == "postgresql":
        import json

        norm = math.sqrt(sum(v * v for v in query_vector)) or 1.0
        node_query = text(_PG_SIMILARITY_SQL).bindparams(
            query_vector=json.dumps(query_vector),
            query_norm=norm,
            limit=limit,
        )
        result = await session.execute(node_query)
        rows = list(result.mappings().all())
        return [
            {
                "node_id": row["node_key"],
                "label": row["label"],
                "node_type": row["node_type"],
                "score": round(float(row["score"]), 4),
                "metadata": row["node_metadata"] or {},
            }
            for row in rows
        ]

    node_query = select(KnowledgeGraphNode)
    if tenant_id is not None:
        node_query = node_query.where(KnowledgeGraphNode.tenant_id == tenant_id)
    nodes = list((await session.scalars(node_query.limit(500))).all())
    scored = sorted(
        [
            (cosine_similarity(query_vector, [float(v) for v in (node.embedding or [])]), node)
            for node in nodes
        ],
        key=lambda item: item[0],
        reverse=True,
    )
    return [
        {
            "node_id": node.node_key,
            "label": node.label,
            "node_type": node.node_type,
            "score": round(float(score), 4),
            "metadata": node.node_metadata or {},
        }
        for score, node in scored[:limit]
        if score > 0
    ]
