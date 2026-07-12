from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from planagent.config import reset_settings_cache
from planagent.db import reset_database_cache
from planagent.main import create_app


def test_stats_reports_no_prediction_accuracy_without_verified_samples(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(
        "PLANAGENT_DATABASE_URL",
        f"sqlite+aiosqlite:///{(tmp_path / 'stats.db').resolve().as_posix()}",
    )
    monkeypatch.setenv("PLANAGENT_EVENT_BUS_BACKEND", "memory")
    reset_settings_cache()
    reset_database_cache()

    with TestClient(create_app()) as client:
        response = client.get("/stats")

    assert response.status_code == 200
    payload = response.json()
    assert payload["prediction_accuracy"] is None
    assert payload["prediction_accuracy_sample_size"] == 0
    assert payload["prediction_accuracy_status"] == "no_verified_samples"
