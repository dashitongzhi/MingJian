from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import subprocess
import sys


def test_sqlite_upgrade_head_keeps_portable_embedding_column(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    database_path = tmp_path / "community-migrations.db"
    env = os.environ.copy()
    env["PLANAGENT_DATABASE_URL"] = f"sqlite+aiosqlite:///{database_path.resolve().as_posix()}"

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    with sqlite3.connect(database_path) as connection:
        columns = {
            row[1]: row[2] for row in connection.execute("PRAGMA table_info(knowledge_graph_nodes)")
        }
        indexes = {row[1] for row in connection.execute("PRAGMA index_list(knowledge_graph_nodes)")}
        recommendation_unique_columns = {
            tuple(column[2] for column in connection.execute(f'PRAGMA index_info("{index[1]}")'))
            for index in connection.execute("PRAGMA index_list(recommendation_versions)")
            if index[2]
        }

    assert columns["embedding_vector"] == "TEXT"
    assert "ix_knowledge_graph_nodes_embedding_vector" not in indexes
    assert ("session_id", "version_number") in recommendation_unique_columns


def test_recommendation_integrity_migration_repairs_existing_duplicates(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    database_path = tmp_path / "community-existing-recommendations.db"
    env = os.environ.copy()
    env["PLANAGENT_DATABASE_URL"] = f"sqlite+aiosqlite:///{database_path.resolve().as_posix()}"

    before_constraint = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "0027_auth_token_version"],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert before_constraint.returncode == 0, before_constraint.stdout + before_constraint.stderr

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "INSERT INTO strategic_sessions "
            "(id, name, topic, domain_id, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                "session-1",
                "Migration repair",
                "Repair duplicate recommendation versions",
                "corporate",
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:00:00+00:00",
            ),
        )
        connection.executemany(
            "INSERT INTO recommendation_versions "
            "(id, session_id, version_number, trigger_type, recommendation_summary, generated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                (
                    "version-later",
                    "session-1",
                    1,
                    "scheduled_refresh",
                    "later",
                    "2026-01-02T00:00:00+00:00",
                ),
                (
                    "version-earlier",
                    "session-1",
                    1,
                    "initial_result",
                    "earlier",
                    "2026-01-01T00:00:00+00:00",
                ),
            ],
        )

    repaired = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert repaired.returncode == 0, repaired.stdout + repaired.stderr

    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            "SELECT id, version_number FROM recommendation_versions "
            "WHERE session_id = ? ORDER BY version_number",
            ("session-1",),
        ).fetchall()

    assert rows == [("version-earlier", 1), ("version-later", 2)]
