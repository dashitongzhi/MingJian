from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from planagent.config import reset_settings_cache
from planagent.db import reset_database_cache
from planagent.main import create_app


def test_simulation_and_debate_limits_are_bounded(monkeypatch, tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'pagination.db').resolve().as_posix()}"
    monkeypatch.setenv("PLANAGENT_DATABASE_URL", database_url)
    monkeypatch.setenv("PLANAGENT_EVENT_BUS_BACKEND", "memory")
    monkeypatch.setenv("PLANAGENT_OPENAI_API_KEY", "")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    reset_settings_cache()
    reset_database_cache()

    with TestClient(create_app()) as client:
        responses = [
            client.get("/simulation/runs?limit=0"),
            client.get("/simulation/runs?limit=101"),
            client.get("/debates?limit=-1"),
            client.get("/debates?limit=201"),
        ]

    assert [response.status_code for response in responses] == [422, 422, 422, 422]
