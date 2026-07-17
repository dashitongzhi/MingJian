from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from planagent.config import reset_settings_cache
from planagent.db import reset_database_cache
from planagent.main import create_app
from planagent.services.auth import UserRole


def _database_url(path: Path) -> str:
    return f"sqlite+aiosqlite:///{path.resolve().as_posix()}"


def _configure_remote_access(
    monkeypatch: pytest.MonkeyPatch,
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
    monkeypatch.setenv(
        "PLANAGENT_BOOTSTRAP_ADMIN_PASSWORD",
        "test-bootstrap-admin-password",
    )
    reset_settings_cache()
    reset_database_cache()


def _register_and_login(client: TestClient, username: str = "remote-user") -> str:
    _, token = _register_and_login_user(client, username=username)
    return token


def _register_and_login_user(
    client: TestClient,
    username: str,
) -> tuple[str, str]:
    user = client.app.state.auth_service.create_user(
        username=username,
        email=f"{username}@example.com",
        password="safe-password",
    )
    tokens = client.app.state.auth_service._create_token_pair(user)
    return user.id, tokens.access_token


def test_notifications_reject_anonymous_remote_access(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_remote_access(monkeypatch, tmp_path / "anonymous.db")

    with TestClient(create_app(), client=("203.0.113.10", 50000)) as client:
        response = client.get("/notifications/stats")

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing Authorization header"


def test_notification_stats_accept_remote_admin(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_remote_access(monkeypatch, tmp_path / "admin-stats.db")

    with TestClient(create_app(), client=("203.0.113.10", 50000)) as client:
        login = client.post(
            "/auth/login",
            json={
                "username": "admin",
                "password": "test-bootstrap-admin-password",
            },
        )
        assert login.status_code == 200
        response = client.get(
            "/notifications/stats",
            headers={"Authorization": f"Bearer {login.json()['access_token']}"},
        )

    assert response.status_code == 200


def test_notification_stats_reject_remote_analyst(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_remote_access(
        monkeypatch,
        tmp_path / "analyst-stats.db",
        registration_enabled=True,
    )

    with TestClient(create_app(), client=("203.0.113.10", 50000)) as client:
        access_token = _register_and_login(client, username="stats-analyst")
        response = client.get(
            "/notifications/stats",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "Notification administration requires admin role"


def test_remote_user_cannot_read_another_users_notification_history(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
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


def test_remote_analyst_cannot_broadcast_notifications(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
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


def test_remote_analyst_cannot_reset_global_agent_configuration(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_remote_access(monkeypatch, tmp_path / "agent-admin-boundary.db")

    with TestClient(create_app(), client=("203.0.113.10", 50000)) as client:
        token = _register_and_login(client, username="agent-analyst")
        response = client.post(
            "/agents/reset",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "Requires role: admin"


def test_remote_viewer_is_read_only_across_business_routes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_remote_access(monkeypatch, tmp_path / "viewer-read-only.db")

    with TestClient(create_app(), client=("203.0.113.10", 50000)) as client:
        viewer = client.app.state.auth_service.create_user(
            username="read-only-viewer",
            email="read-only-viewer@example.com",
            password="safe-password",
            role=UserRole.VIEWER,
        )
        token = client.app.state.auth_service._create_token_pair(viewer).access_token
        headers = {"Authorization": f"Bearer {token}"}

        read_response = client.get("/stats", headers=headers)
        write_response = client.post(
            "/export/custom",
            headers=headers,
            json={"topic": "viewer must not create exports"},
        )
        logout_response = client.post("/auth/logout", headers=headers)

    assert read_response.status_code == 200
    assert write_response.status_code == 403
    assert write_response.json()["detail"] == "Viewer role is read-only"
    assert logout_response.status_code == 200


def test_remote_login_throttles_repeated_password_guessing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_remote_access(monkeypatch, tmp_path / "login-throttle.db")

    with TestClient(create_app(), client=("203.0.113.10", 50000)) as client:
        client.app.state.auth_service.create_user(
            username="throttle-target",
            email="throttle-target@example.com",
            password="safe-password",
        )
        for _ in range(5):
            failed = client.post(
                "/auth/login",
                json={"username": "throttle-target", "password": "wrong-password"},
            )
            assert failed.status_code in {401, 429}

        blocked = client.post(
            "/auth/login",
            json={"username": "throttle-target", "password": "safe-password"},
        )

    assert blocked.status_code == 429
    assert blocked.headers["Retry-After"]
    assert blocked.json()["detail"] == "Too many failed login attempts"


def test_remote_mode_rejects_non_admin_login_and_refresh(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_remote_access(monkeypatch, tmp_path / "admin-only-remote-auth.db")

    with TestClient(create_app(), client=("203.0.113.10", 50000)) as client:
        user = client.app.state.auth_service.create_user(
            username="community-analyst",
            email="community-analyst@example.com",
            password="safe-password",
        )
        direct_tokens = client.app.state.auth_service._create_token_pair(user)
        refresh_response = client.post(
            "/auth/refresh",
            json={"refresh_token": direct_tokens.refresh_token},
        )
        login_response = client.post(
            "/auth/login",
            json={"username": "community-analyst", "password": "safe-password"},
        )

    assert login_response.status_code == 403
    assert refresh_response.status_code == 403
    assert login_response.json()["detail"] == "Community remote access is administrator-only"
    assert refresh_response.json()["detail"] == "Community remote access is administrator-only"


def test_remote_authentication_responses_disable_caching(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_remote_access(monkeypatch, tmp_path / "auth-cache-control.db")

    with TestClient(create_app(), client=("203.0.113.10", 50000)) as client:
        response = client.post(
            "/auth/login",
            json={
                "username": "admin",
                "password": "test-bootstrap-admin-password",
            },
        )

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Pragma"] == "no-cache"


def test_remote_login_rejects_passwords_beyond_bcrypt_limit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_remote_access(monkeypatch, tmp_path / "auth-password-limit.db")

    with TestClient(
        create_app(),
        client=("203.0.113.10", 50000),
        raise_server_exceptions=False,
    ) as client:
        response = client.post(
            "/auth/login",
            json={"username": "admin", "password": "x" * 73},
        )

    assert response.status_code == 422


def test_remote_requests_reject_oversized_chunked_body(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PLANAGENT_MAX_REQUEST_BODY_BYTES", "64")
    _configure_remote_access(monkeypatch, tmp_path / "request-body-limit.db")

    with TestClient(create_app(), client=("203.0.113.10", 50000)) as client:
        token = _register_and_login(client, username="body-limit-user")
        response = client.post(
            "/export/custom",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            content=iter([b'{"topic":"', b"x" * 80, b'"}']),
        )

    assert response.status_code == 413
    assert response.json()["detail"] == "Request body too large"


def test_remote_user_cannot_send_notification_as_another_user(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
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


def test_remote_user_can_use_own_notification_channel(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
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
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
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
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
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
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
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


def test_admin_business_routes_reject_anonymous_remote_access(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_remote_access(monkeypatch, tmp_path / "admin-anonymous.db")

    with TestClient(create_app(), client=("203.0.113.10", 50000)) as client:
        response = client.get("/watch/rules")

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing Authorization header"


def test_admin_business_routes_allow_loopback_local_session(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PLANAGENT_DATABASE_URL", _database_url(tmp_path / "admin-local.db"))
    monkeypatch.setenv("PLANAGENT_EVENT_BUS_BACKEND", "memory")
    monkeypatch.delenv("PLANAGENT_REMOTE_ACCESS_ENABLED", raising=False)
    reset_settings_cache()
    reset_database_cache()

    with TestClient(create_app(), client=("127.0.0.1", 50000)) as client:
        response = client.get("/watch/rules")

    assert response.status_code == 200


def test_admin_only_routes_allow_loopback_local_admin_session(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PLANAGENT_DATABASE_URL", _database_url(tmp_path / "admin-role.db"))
    monkeypatch.setenv("PLANAGENT_EVENT_BUS_BACKEND", "memory")
    monkeypatch.delenv("PLANAGENT_REMOTE_ACCESS_ENABLED", raising=False)
    reset_settings_cache()
    reset_database_cache()

    with TestClient(create_app(), client=("127.0.0.1", 50000)) as client:
        response = client.get("/admin/analysis/cache")

    assert response.status_code == 200


def test_expired_watch_rule_cannot_be_triggered_manually(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
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


def test_all_business_routes_reject_anonymous_remote_access(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
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
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
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


@pytest.mark.parametrize("registration_enabled", [False, True])
def test_remote_registration_is_always_disabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, registration_enabled: bool
) -> None:
    _configure_remote_access(
        monkeypatch,
        tmp_path / f"registration-disabled-{registration_enabled}.db",
        registration_enabled=registration_enabled,
    )

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


def test_remote_mode_has_an_explicit_bootstrap_admin_login(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_remote_access(monkeypatch, tmp_path / "bootstrap-admin.db")

    with TestClient(create_app(), client=("203.0.113.10", 50000)) as client:
        response = client.post(
            "/auth/login",
            json={
                "username": "admin",
                "password": "test-bootstrap-admin-password",
            },
        )

    assert response.status_code == 200


def test_remote_admin_can_rotate_bootstrap_password(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_remote_access(monkeypatch, tmp_path / "rotate-bootstrap-admin.db")

    with TestClient(create_app(), client=("203.0.113.10", 50000)) as client:
        login = client.post(
            "/auth/login",
            json={
                "username": "admin",
                "password": "test-bootstrap-admin-password",
            },
        )
        assert login.status_code == 200
        bootstrap_refresh_token = login.json()["refresh_token"]
        changed = client.post(
            "/auth/change-password",
            headers={"Authorization": f"Bearer {login.json()['access_token']}"},
            json={
                "current_password": "test-bootstrap-admin-password",
                "new_password": "rotated-admin-password-strong",
            },
        )
        old_login = client.post(
            "/auth/login",
            json={
                "username": "admin",
                "password": "test-bootstrap-admin-password",
            },
        )
        new_login = client.post(
            "/auth/login",
            json={
                "username": "admin",
                "password": "rotated-admin-password-strong",
            },
        )
        old_refresh = client.post(
            "/auth/refresh",
            json={"refresh_token": bootstrap_refresh_token},
        )
        old_access = client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {login.json()['access_token']}"},
        )

    assert changed.status_code == 200
    assert old_login.status_code == 401
    assert new_login.status_code == 200
    assert old_refresh.status_code == 401
    assert old_access.status_code == 401


def test_remote_logout_revokes_the_users_refresh_session(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_remote_access(monkeypatch, tmp_path / "logout-refresh.db")

    with TestClient(create_app(), client=("203.0.113.10", 50000)) as client:
        login = client.post(
            "/auth/login",
            json={
                "username": "admin",
                "password": "test-bootstrap-admin-password",
            },
        )
        assert login.status_code == 200

        logout = client.post(
            "/auth/logout",
            headers={"Authorization": f"Bearer {login.json()['access_token']}"},
        )
        refreshed = client.post(
            "/auth/refresh",
            json={"refresh_token": login.json()["refresh_token"]},
        )

    assert logout.status_code == 200
    assert refreshed.status_code == 401


def test_remote_health_and_docs_remain_public(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
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
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_remote_access(monkeypatch, tmp_path / "websocket-anonymous.db")

    with TestClient(create_app(), client=("203.0.113.10", 50000)) as client:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/notifications/ws/remote-user"):
                pass

    assert exc_info.value.code == 1008


def test_remote_notification_websocket_rejects_access_token_in_query_string(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_remote_access(
        monkeypatch,
        tmp_path / "websocket-query-token.db",
        registration_enabled=True,
    )

    with TestClient(create_app(), client=("203.0.113.10", 50000)) as client:
        user_id, token = _register_and_login_user(client, username="socket-query-token")
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(f"/notifications/ws/{user_id}?token={token}"):
                pass

    assert exc_info.value.code == 1008


def test_remote_notification_websocket_accepts_browser_jwt_subprotocol(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_remote_access(monkeypatch, tmp_path / "websocket-subprotocol.db")

    with TestClient(create_app(), client=("203.0.113.10", 50000)) as client:
        user_id, token = _register_and_login_user(client, username="socket-subprotocol")
        with client.websocket_connect(
            f"/notifications/ws/{user_id}",
            subprotocols=["mingjian.jwt", token],
        ) as websocket:
            assert websocket.accepted_subprotocol == "mingjian.jwt"
            websocket.send_json({"type": "ping"})
            assert websocket.receive_json() == {"type": "pong"}


def test_remote_notification_websocket_rejects_another_users_identity(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
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


def test_remote_analyst_cannot_open_global_notification_stream(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
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
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
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
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
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
