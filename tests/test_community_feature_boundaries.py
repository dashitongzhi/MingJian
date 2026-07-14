from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from planagent.config import reset_settings_cache
from planagent.db import reset_database_cache
from planagent.main import create_app


COMMERCIAL_FEATURE_DETAIL = {
    "code": "commercial_edition_required",
    "edition": "community",
    "available_in": ["cloud", "enterprise"],
}


def _configure_local_community(monkeypatch, database_path: Path) -> None:
    monkeypatch.setenv(
        "PLANAGENT_DATABASE_URL",
        f"sqlite+aiosqlite:///{database_path.resolve().as_posix()}",
    )
    monkeypatch.setenv("PLANAGENT_EVENT_BUS_BACKEND", "memory")
    monkeypatch.delenv("PLANAGENT_REMOTE_ACCESS_ENABLED", raising=False)
    monkeypatch.delenv("PLANAGENT_LOCAL_PROXY_SECRET", raising=False)
    reset_settings_cache()
    reset_database_cache()


@pytest.mark.parametrize(
    ("method", "path", "feature"),
    [
        ("get", "/monitoring/calibration", "prediction_calibration"),
        ("get", "/monitoring/calibration/history", "prediction_calibration"),
        ("get", "/calibration", "prediction_calibration"),
        ("post", "/calibration/compute", "prediction_calibration"),
        ("get", "/predictions/backtests", "prediction_backtesting"),
        (
            "post",
            "/predictions/missing/versions/missing/verify",
            "prediction_backtesting",
        ),
    ],
)
def test_community_rejects_commercial_prediction_operations(
    monkeypatch,
    tmp_path: Path,
    method: str,
    path: str,
    feature: str,
) -> None:
    _configure_local_community(monkeypatch, tmp_path / f"{feature}-{method}.db")

    with TestClient(create_app(), client=("127.0.0.1", 50000)) as client:
        response = client.request(method.upper(), path, json={"domain_id": "corporate"})

    assert response.status_code == 403
    assert response.json()["detail"] == {
        **COMMERCIAL_FEATURE_DETAIL,
        "feature": feature,
        "message": "This feature is available in MingJian Cloud or Enterprise.",
    }


def test_community_dashboard_omits_commercial_calibration_and_backtest_metrics(
    monkeypatch, tmp_path: Path
) -> None:
    _configure_local_community(monkeypatch, tmp_path / "monitoring-dashboard.db")

    with TestClient(create_app(), client=("127.0.0.1", 50000)) as client:
        response = client.get("/monitoring/dashboard")

    assert response.status_code == 200
    body = response.json()
    assert "calibration" not in body
    assert "verified" not in body["predictions"]
    assert body["edition_features"] == {
        "monitoring_window": "community_24h",
        "prediction_calibration": False,
        "prediction_backtesting": False,
        "notification_channels": ["websocket"],
    }


@pytest.mark.parametrize("channel", ["email", "webhook"])
def test_community_notification_delivery_is_websocket_only(
    monkeypatch,
    tmp_path: Path,
    channel: str,
) -> None:
    _configure_local_community(monkeypatch, tmp_path / f"notification-{channel}.db")

    with TestClient(create_app(), client=("127.0.0.1", 50000)) as client:
        response = client.post(
            "/notifications/send",
            json={
                "user_id": "community-local",
                "title": "Commercial delivery",
                "body": "Must not leave the local Community process.",
                "channel": channel,
            },
        )

    assert response.status_code == 403
    assert response.json()["detail"] == {
        **COMMERCIAL_FEATURE_DETAIL,
        "feature": "notification_channels",
        "message": "This feature is available in MingJian Cloud or Enterprise.",
    }


def test_community_rejects_notification_broadcasts(monkeypatch, tmp_path: Path) -> None:
    _configure_local_community(monkeypatch, tmp_path / "notification-broadcast.db")

    with TestClient(create_app(), client=("127.0.0.1", 50000)) as client:
        response = client.post(
            "/notifications/broadcast",
            json={"title": "Commercial broadcast", "body": "Not in Community."},
        )

    assert response.status_code == 403
    assert response.json()["detail"]["feature"] == "notification_broadcast"


def test_community_does_not_expose_global_notification_stream(monkeypatch, tmp_path: Path) -> None:
    _configure_local_community(monkeypatch, tmp_path / "global-notification-stream.db")

    with TestClient(create_app(), client=("127.0.0.1", 50000)) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws/notifications"):
                pass
