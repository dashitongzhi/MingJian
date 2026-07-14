from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from planagent.config import reset_settings_cache
from planagent.db import reset_database_cache
from planagent.main import create_app


def _database_url(path: Path) -> str:
    return f"sqlite+aiosqlite:///{path.resolve().as_posix()}"


def _configure_remote_access(monkeypatch, database_path: Path) -> None:
    monkeypatch.setenv("PLANAGENT_DATABASE_URL", _database_url(database_path))
    monkeypatch.setenv("PLANAGENT_EVENT_BUS_BACKEND", "memory")
    monkeypatch.setenv("PLANAGENT_REMOTE_ACCESS_ENABLED", "true")
    monkeypatch.setenv("PLANAGENT_AUTH_SECRET_KEY", "test-secret-key-with-at-least-32-bytes")
    reset_settings_cache()
    reset_database_cache()


def test_notifications_reject_anonymous_remote_access(monkeypatch, tmp_path: Path) -> None:
    _configure_remote_access(monkeypatch, tmp_path / "anonymous.db")

    with TestClient(create_app(), client=("203.0.113.10", 50000)) as client:
        response = client.get("/notifications/stats")

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing Authorization header"


def test_notifications_accept_valid_remote_user(monkeypatch, tmp_path: Path) -> None:
    _configure_remote_access(monkeypatch, tmp_path / "authenticated.db")

    with TestClient(create_app(), client=("203.0.113.10", 50000)) as client:
        register = client.post(
            "/auth/register",
            json={
                "username": "remote-user",
                "email": "remote@example.com",
                "password": "safe-password",
            },
        )
        assert register.status_code == 201
        login = client.post(
            "/auth/login",
            json={"username": "remote-user", "password": "safe-password"},
        )
        assert login.status_code == 200

        response = client.get(
            "/notifications/stats",
            headers={"Authorization": f"Bearer {login.json()['access_token']}"},
        )

    assert response.status_code == 200


def test_notifications_allow_loopback_local_session(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PLANAGENT_DATABASE_URL", _database_url(tmp_path / "loopback.db"))
    monkeypatch.setenv("PLANAGENT_EVENT_BUS_BACKEND", "memory")
    monkeypatch.delenv("PLANAGENT_REMOTE_ACCESS_ENABLED", raising=False)
    reset_settings_cache()
    reset_database_cache()

    with TestClient(create_app(), client=("127.0.0.1", 50000)) as client:
        response = client.get("/notifications/stats")

    assert response.status_code == 200
