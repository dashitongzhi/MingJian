from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from planagent.config import reset_settings_cache
from planagent.db import reset_database_cache
from planagent.main import create_app
from planagent.services.agent_registry import get_agent_registry, reset_agent_registry


def _configure(monkeypatch, path: Path) -> None:
    monkeypatch.setenv("PLANAGENT_DATABASE_URL", f"sqlite+aiosqlite:///{path.resolve().as_posix()}")
    monkeypatch.setenv("PLANAGENT_EVENT_BUS_BACKEND", "memory")
    monkeypatch.setenv("PLANAGENT_OPENAI_API_KEY", "")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    reset_settings_cache()
    reset_database_cache()
    reset_agent_registry()


def test_agent_configuration_rejects_credentialed_provider_url(monkeypatch, tmp_path: Path) -> None:
    _configure(monkeypatch, tmp_path / "agents-invalid-url.db")

    with TestClient(create_app()) as client:
        response = client.post(
            "/agents/configure",
            json={
                "keys": [
                    {
                        "api_key": "secret-key",
                        "provider_type": "openai",
                        "base_url": "https://user:password@example.com/v1",
                        "model": "model-a",
                    }
                ]
            },
        )

    assert response.status_code == 422
    assert get_agent_registry().get_status()["ready"] == 0


def test_agent_configuration_accepts_local_provider_and_returns_canonical_roles(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _configure(monkeypatch, tmp_path / "agents-valid-url.db")

    with TestClient(create_app()) as client:
        response = client.post(
            "/agents/configure",
            json={
                "keys": [
                    {
                        "api_key": "secret-key",
                        "provider_type": "openai",
                        "base_url": "http://127.0.0.1:11434/v1/",
                        "model": "local-model",
                    }
                ]
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ready"] == 9
    assert payload["agents"][3]["role_key"] == "intel_analyst"
    assert payload["agents"][3]["registry_role"] == "evidence_assessor"


def test_unknown_agent_role_returns_not_found(monkeypatch, tmp_path: Path) -> None:
    _configure(monkeypatch, tmp_path / "agents-unknown-role.db")

    with TestClient(create_app()) as client:
        response = client.post(
            "/agents/model",
            json={"role": "not-a-role", "model": "model-a"},
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "Unknown agent role"}
