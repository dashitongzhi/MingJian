from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from planagent.config import reset_settings_cache
from planagent.db import reset_database_cache
from planagent.main import create_app


def _database_url(path: Path) -> str:
    return f"sqlite+aiosqlite:///{path.resolve().as_posix()}"


def _configure_remote_access(
    monkeypatch,
    database_path: Path,
    *,
    registration_enabled: bool = False,
) -> None:
    monkeypatch.setenv("PLANAGENT_DATABASE_URL", _database_url(database_path))
    monkeypatch.setenv("PLANAGENT_EVENT_BUS_BACKEND", "memory")
    monkeypatch.setenv("PLANAGENT_REMOTE_ACCESS_ENABLED", "true")
    monkeypatch.setenv(
        "PLANAGENT_REMOTE_REGISTRATION_ENABLED",
        "true" if registration_enabled else "false",
    )
    monkeypatch.setenv("PLANAGENT_AUTH_SECRET_KEY", "test-secret-key-with-at-least-32-bytes")
    reset_settings_cache()
    reset_database_cache()


def _register_and_login(client: TestClient, username: str = "remote-user") -> str:
    _, token = _register_and_login_user(client, username=username)
    return token


def _register_and_login_user(
    client: TestClient,
    username: str,
) -> tuple[str, str]:
    register = client.post(
        "/auth/register",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": "safe-password",
        },
    )
    assert register.status_code == 201
    user_id = str(register.json()["id"])
    login = client.post(
        "/auth/login",
        json={"username": username, "password": "safe-password"},
    )
    assert login.status_code == 200
    return user_id, str(login.json()["access_token"])


def test_notifications_reject_anonymous_remote_access(monkeypatch, tmp_path: Path) -> None:
    _configure_remote_access(monkeypatch, tmp_path / "anonymous.db")

    with TestClient(create_app(), client=("203.0.113.10", 50000)) as client:
        response = client.get("/notifications/stats")

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing Authorization header"


def test_notifications_accept_valid_remote_user(monkeypatch, tmp_path: Path) -> None:
    _configure_remote_access(
        monkeypatch,
        tmp_path / "authenticated.db",
        registration_enabled=True,
    )

    with TestClient(create_app(), client=("203.0.113.10", 50000)) as client:
        access_token = _register_and_login(client)
        response = client.get(
            "/notifications/stats",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    assert response.status_code == 200


def test_remote_user_cannot_read_another_users_notification_history(
    monkeypatch, tmp_path: Path
) -> None:
    _configure_remote_access(
        monkeypatch,
        tmp_path / "notification-objects.db",
        registration_enabled=True,
    )

    with TestClient(create_app(), client=("203.0.113.10", 50000)) as client:
        _, first_token = _register_and_login_user(client, username="first-user")
        second_user_id, _ = _register_and_login_user(client, username="second-user")
        response = client.get(
            f"/notifications/history/{second_user_id}",
            headers={"Authorization": f"Bearer {first_token}"},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "Notification access is limited to the current user"


def test_remote_analyst_cannot_broadcast_notifications(monkeypatch, tmp_path: Path) -> None:
    _configure_remote_access(
        monkeypatch,
        tmp_path / "notification-broadcast.db",
        registration_enabled=True,
    )

    with TestClient(create_app(), client=("203.0.113.10", 50000)) as client:
        token = _register_and_login(client, username="broadcast-user")
        response = client.post(
            "/notifications/broadcast",
            headers={"Authorization": f"Bearer {token}"},
            json={"title": "Unsafe", "body": "Should not broadcast"},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "Notification administration requires admin role"


def test_remote_user_cannot_send_notification_as_another_user(monkeypatch, tmp_path: Path) -> None:
    _configure_remote_access(
        monkeypatch,
        tmp_path / "notification-send.db",
        registration_enabled=True,
    )

    with TestClient(create_app(), client=("203.0.113.10", 50000)) as client:
        _, first_token = _register_and_login_user(client, username="sender-user")
        second_user_id, _ = _register_and_login_user(client, username="target-user")
        response = client.post(
            "/notifications/send",
            headers={"Authorization": f"Bearer {first_token}"},
            json={
                "user_id": second_user_id,
                "title": "Impersonated",
                "body": "Should not send",
            },
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "Notification access is limited to the current user"


def test_remote_user_can_use_own_notification_channel(monkeypatch, tmp_path: Path) -> None:
    _configure_remote_access(
        monkeypatch,
        tmp_path / "notification-own-channel.db",
        registration_enabled=True,
    )

    with TestClient(create_app(), client=("203.0.113.10", 50000)) as client:
        user_id, token = _register_and_login_user(client, username="own-channel-user")
        headers = {"Authorization": f"Bearer {token}"}
        sent = client.post(
            "/notifications/send",
            headers=headers,
            json={
                "user_id": user_id,
                "title": "Own notification",
                "body": "Allowed",
            },
        )
        history = client.get(f"/notifications/history/{user_id}", headers=headers)
        with client.websocket_connect(
            f"/notifications/ws/{user_id}",
            headers=headers,
        ) as websocket:
            websocket.send_json({"type": "ping"})
            pong = websocket.receive_json()

    assert sent.status_code == 200
    assert history.status_code == 200
    assert len(history.json()) == 1
    assert pong == {"type": "pong"}


def test_notifications_allow_local_session_behind_container_proxy(
    monkeypatch, tmp_path: Path
) -> None:
    proxy_secret = "container-proxy-secret-with-at-least-32-bytes"
    monkeypatch.setenv("PLANAGENT_DATABASE_URL", _database_url(tmp_path / "loopback.db"))
    monkeypatch.setenv("PLANAGENT_EVENT_BUS_BACKEND", "memory")
    monkeypatch.setenv("PLANAGENT_LOCAL_PROXY_SECRET", proxy_secret)
    monkeypatch.delenv("PLANAGENT_REMOTE_ACCESS_ENABLED", raising=False)
    reset_settings_cache()
    reset_database_cache()

    with TestClient(create_app(), client=("172.20.0.10", 50000)) as client:
        response = client.get(
            "/notifications/stats",
            headers={"X-MingJian-Local-Proxy": proxy_secret},
        )

    assert response.status_code == 200


def test_local_mode_rejects_non_loopback_peer_without_proxy_secret(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PLANAGENT_DATABASE_URL", _database_url(tmp_path / "exposed-local.db"))
    monkeypatch.setenv("PLANAGENT_EVENT_BUS_BACKEND", "memory")
    monkeypatch.delenv("PLANAGENT_REMOTE_ACCESS_ENABLED", raising=False)
    monkeypatch.delenv("PLANAGENT_LOCAL_PROXY_SECRET", raising=False)
    reset_settings_cache()
    reset_database_cache()

    with TestClient(create_app(), client=("203.0.113.10", 50000)) as client:
        response = client.get("/notifications/stats")

    assert response.status_code == 403
    assert response.json()["detail"] == "Local Community access requires a loopback connection"


def test_local_mode_does_not_expose_auth_routes_to_non_loopback_peers(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PLANAGENT_DATABASE_URL", _database_url(tmp_path / "local-auth.db"))
    monkeypatch.setenv("PLANAGENT_EVENT_BUS_BACKEND", "memory")
    monkeypatch.delenv("PLANAGENT_REMOTE_ACCESS_ENABLED", raising=False)
    monkeypatch.delenv("PLANAGENT_LOCAL_PROXY_SECRET", raising=False)
    reset_settings_cache()
    reset_database_cache()

    with TestClient(create_app(), client=("203.0.113.10", 50000)) as client:
        response = client.post(
            "/auth/register",
            json={
                "username": "exposed-user",
                "email": "exposed@example.com",
                "password": "safe-password",
            },
        )

    assert response.status_code == 403


def test_admin_business_routes_reject_anonymous_remote_access(monkeypatch, tmp_path: Path) -> None:
    _configure_remote_access(monkeypatch, tmp_path / "admin-anonymous.db")

    with TestClient(create_app(), client=("203.0.113.10", 50000)) as client:
        response = client.get("/watch/rules")

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing Authorization header"


def test_admin_business_routes_allow_loopback_local_session(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PLANAGENT_DATABASE_URL", _database_url(tmp_path / "admin-local.db"))
    monkeypatch.setenv("PLANAGENT_EVENT_BUS_BACKEND", "memory")
    monkeypatch.delenv("PLANAGENT_REMOTE_ACCESS_ENABLED", raising=False)
    reset_settings_cache()
    reset_database_cache()

    with TestClient(create_app(), client=("127.0.0.1", 50000)) as client:
        response = client.get("/watch/rules")

    assert response.status_code == 200


def test_admin_only_routes_allow_loopback_local_admin_session(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PLANAGENT_DATABASE_URL", _database_url(tmp_path / "admin-role.db"))
    monkeypatch.setenv("PLANAGENT_EVENT_BUS_BACKEND", "memory")
    monkeypatch.delenv("PLANAGENT_REMOTE_ACCESS_ENABLED", raising=False)
    reset_settings_cache()
    reset_database_cache()

    with TestClient(create_app(), client=("127.0.0.1", 50000)) as client:
        response = client.get("/admin/analysis/cache")

    assert response.status_code == 200


def test_expired_watch_rule_cannot_be_triggered_manually(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PLANAGENT_DATABASE_URL", _database_url(tmp_path / "expired-watch.db"))
    monkeypatch.setenv("PLANAGENT_EVENT_BUS_BACKEND", "memory")
    monkeypatch.delenv("PLANAGENT_REMOTE_ACCESS_ENABLED", raising=False)
    reset_settings_cache()
    reset_database_cache()

    with TestClient(create_app(), client=("127.0.0.1", 50000)) as client:
        created = client.post(
            "/watch/rules",
            json={
                "name": "24 hour rule",
                "domain_id": "corporate",
                "query": "Track a local decision for one day",
                "source_types": [],
            },
        )
        assert created.status_code == 201
        rule = created.json()
        created_at = datetime.fromisoformat(rule["created_at"])
        monkeypatch.setattr(
            "planagent.api.routes.admin.utc_now",
            lambda: created_at + timedelta(hours=24),
        )

        response = client.post(f"/watch/rules/{rule['id']}/trigger")

    assert response.status_code == 409
    assert response.json()["detail"] == "Community monitoring window expired after 24 hours"


def test_all_business_routes_reject_anonymous_remote_access(monkeypatch, tmp_path: Path) -> None:
    _configure_remote_access(monkeypatch, tmp_path / "global-gate.db")
    payload = {
        "content": "Assess a local planning decision",
        "auto_fetch_news": False,
    }

    with TestClient(create_app(), client=("203.0.113.10", 50000)) as client:
        direct = client.post(
            "/analysis",
            json=payload,
            headers={"Origin": "http://localhost:3000"},
        )
        api_mirror = client.post(
            "/api/analysis",
            json=payload,
            headers={"Origin": "http://localhost:3000"},
        )

    for response in (direct, api_mirror):
        assert response.status_code == 401
        assert response.json()["detail"] == "Missing Authorization header"
        assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_global_gate_accepts_authenticated_remote_business_request(
    monkeypatch, tmp_path: Path
) -> None:
    _configure_remote_access(
        monkeypatch,
        tmp_path / "global-gate-user.db",
        registration_enabled=True,
    )

    with TestClient(create_app(), client=("203.0.113.10", 50000)) as client:
        access_token = _register_and_login(client, username="analysis-user")
        response = client.post(
            "/analysis",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "content": "Assess a local planning decision",
                "auto_fetch_news": False,
            },
        )

    assert response.status_code == 200


def test_remote_registration_is_disabled_by_default(monkeypatch, tmp_path: Path) -> None:
    _configure_remote_access(monkeypatch, tmp_path / "registration-disabled.db")

    with TestClient(create_app(), client=("203.0.113.10", 50000)) as client:
        response = client.post(
            "/auth/register",
            json={
                "username": "unapproved-user",
                "email": "unapproved@example.com",
                "password": "safe-password",
            },
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "Remote user registration is disabled"


def test_remote_health_and_docs_remain_public(monkeypatch, tmp_path: Path) -> None:
    _configure_remote_access(monkeypatch, tmp_path / "public-endpoints.db")

    with TestClient(create_app(), client=("203.0.113.10", 50000)) as client:
        responses = [
            client.get("/health/live"),
            client.get("/api/health/live"),
            client.get("/docs"),
            client.get("/openapi.json"),
        ]

    assert all(response.status_code == 200 for response in responses)


def test_remote_notification_websocket_rejects_anonymous_connection(
    monkeypatch, tmp_path: Path
) -> None:
    _configure_remote_access(monkeypatch, tmp_path / "websocket-anonymous.db")

    with TestClient(create_app(), client=("203.0.113.10", 50000)) as client:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/notifications/ws/remote-user"):
                pass

    assert exc_info.value.code == 1008


def test_remote_notification_websocket_rejects_another_users_identity(
    monkeypatch, tmp_path: Path
) -> None:
    _configure_remote_access(
        monkeypatch,
        tmp_path / "websocket-subject.db",
        registration_enabled=True,
    )

    with TestClient(create_app(), client=("203.0.113.10", 50000)) as client:
        _, first_token = _register_and_login_user(client, username="socket-first")
        second_user_id, _ = _register_and_login_user(client, username="socket-second")
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(
                f"/notifications/ws/{second_user_id}",
                headers={"Authorization": f"Bearer {first_token}"},
            ):
                pass

    assert exc_info.value.code == 1008


def test_remote_analyst_cannot_open_global_notification_stream(monkeypatch, tmp_path: Path) -> None:
    _configure_remote_access(
        monkeypatch,
        tmp_path / "websocket-global.db",
        registration_enabled=True,
    )

    with TestClient(create_app(), client=("203.0.113.10", 50000)) as client:
        token = _register_and_login(client, username="global-stream-user")
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(
                "/ws/notifications",
                headers={"Authorization": f"Bearer {token}"},
            ):
                pass

    assert exc_info.value.code == 1008


def test_local_notification_websocket_uses_local_session_behind_proxy(
    monkeypatch, tmp_path: Path
) -> None:
    proxy_secret = "websocket-proxy-secret-with-at-least-32-bytes"
    monkeypatch.setenv("PLANAGENT_DATABASE_URL", _database_url(tmp_path / "websocket-local.db"))
    monkeypatch.setenv("PLANAGENT_EVENT_BUS_BACKEND", "memory")
    monkeypatch.setenv("PLANAGENT_LOCAL_PROXY_SECRET", proxy_secret)
    monkeypatch.delenv("PLANAGENT_REMOTE_ACCESS_ENABLED", raising=False)
    reset_settings_cache()
    reset_database_cache()

    with TestClient(create_app(), client=("172.20.0.10", 50000)) as client:
        with client.websocket_connect(
            "/notifications/ws/local-user",
            headers={"X-MingJian-Local-Proxy": proxy_secret},
        ) as websocket:
            websocket.send_json({"type": "ping"})
            assert websocket.receive_json() == {"type": "pong"}


def test_local_session_reaches_routes_with_explicit_auth_dependencies(
    monkeypatch, tmp_path: Path
) -> None:
    proxy_secret = "dependency-proxy-secret-with-at-least-32-bytes"
    monkeypatch.setenv("PLANAGENT_DATABASE_URL", _database_url(tmp_path / "local-deps.db"))
    monkeypatch.setenv("PLANAGENT_EVENT_BUS_BACKEND", "memory")
    monkeypatch.setenv("PLANAGENT_LOCAL_PROXY_SECRET", proxy_secret)
    monkeypatch.delenv("PLANAGENT_REMOTE_ACCESS_ENABLED", raising=False)
    reset_settings_cache()
    reset_database_cache()

    with TestClient(create_app(), client=("172.20.0.10", 50000)) as client:
        headers = {"X-MingJian-Local-Proxy": proxy_secret}
        agents = client.get("/agents", headers=headers)
        missing_export = client.get("/export/assistant/session/missing", headers=headers)

    assert agents.status_code == 200
    assert missing_export.status_code == 404
