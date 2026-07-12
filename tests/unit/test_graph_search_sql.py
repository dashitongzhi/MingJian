from __future__ import annotations

from types import SimpleNamespace

import pytest

from planagent.workers.graph import (
    _PGVECTOR_SIMILARITY_SQL,
    _PG_SIMILARITY_SQL,
    search_nodes_sql,
)


class _FakeMappings:
    def __init__(self, rows: list[dict]):
        self._rows = rows

    def all(self) -> list[dict]:
        return self._rows


class _FakeResult:
    def __init__(self, rows: list[dict]):
        self._rows = rows

    def mappings(self) -> _FakeMappings:
        return _FakeMappings(self._rows)


class _FakePostgresSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def get_bind(self):
        return SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

    async def execute(self, statement):
        compiled_sql = str(statement)
        params = dict(getattr(statement, "_bindparams", {}))
        self.calls.append((compiled_sql, params))
        if len(self.calls) == 1:
            raise RuntimeError("pgvector extension unavailable")
        return _FakeResult(
            [
                {
                    "node_key": "node-1",
                    "label": "Node 1",
                    "node_type": "claim",
                    "score": 0.9,
                    "node_metadata": {"source": "test"},
                }
            ]
        )


def test_postgres_vector_sql_uses_casted_bind_parameters() -> None:
    assert ":query_vector::" not in _PGVECTOR_SIMILARITY_SQL
    assert ":query_vector::" not in _PG_SIMILARITY_SQL
    assert "CAST(:query_vector AS vector)" in _PGVECTOR_SIMILARITY_SQL
    assert "CAST(:query_vector AS jsonb)" in _PG_SIMILARITY_SQL


@pytest.mark.asyncio
async def test_postgres_fallback_binds_tenant_id() -> None:
    session = _FakePostgresSession()

    rows = await search_nodes_sql(session, [0.25, 0.75], tenant_id="tenant-a", limit=5)

    assert rows == [
        {
            "node_id": "node-1",
            "label": "Node 1",
            "node_type": "claim",
            "score": 0.9,
            "metadata": {"source": "test"},
        }
    ]
    assert len(session.calls) == 2
    assert session.calls[0][1]["tenant_id"].value == "tenant-a"
    assert session.calls[1][1]["tenant_id"].value == "tenant-a"
