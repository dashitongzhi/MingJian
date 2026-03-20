from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from planagent.config import reset_settings_cache
from planagent.db import reset_database_cache
from planagent.main import create_app
from planagent.services.openai_client import resolve_openclaw_model_selector


def build_database_url(path: Path) -> str:
    return f"sqlite+aiosqlite:///{path.resolve().as_posix()}"


def test_inline_ingest_creates_review_queue_and_promotes_claims(monkeypatch, tmp_path: Path) -> None:
    database_path = tmp_path / "planagent-test.db"
    monkeypatch.setenv("PLANAGENT_DATABASE_URL", build_database_url(database_path))
    monkeypatch.setenv("PLANAGENT_EVENT_BUS_BACKEND", "memory")
    monkeypatch.setenv("PLANAGENT_INLINE_INGEST_DEFAULT", "true")
    reset_settings_cache()
    reset_database_cache()

    payload = {
        "requested_by": "test-analyst",
        "items": [
            {
                "source_type": "rss",
                "source_url": "https://example.com/acme-gpu",
                "title": "Acme ships new GPU orchestration service",
                "content_text": (
                    "Acme shipped a new GPU orchestration service across three regions and "
                    "reduced model training cost by 22 percent after a six-week rollout. "
                    "Costs increase."
                ),
                "published_at": "2026-03-16T08:00:00Z",
            }
        ],
    }

    with TestClient(create_app()) as client:
        ingest_response = client.post("/ingest/runs", json=payload)
        assert ingest_response.status_code == 201
        ingest_run = ingest_response.json()
        assert ingest_run["status"] == "COMPLETED"
        assert ingest_run["summary"]["processed_items"] == 1
        assert ingest_run["summary"]["accepted_claims"] >= 1
        assert ingest_run["summary"]["review_claims"] == 1

        evidence_response = client.get("/evidence")
        claims_response = client.get("/claims")
        events_response = client.get("/events")
        review_items_response = client.get("/review/items")

        assert evidence_response.status_code == 200
        assert len(evidence_response.json()) == 1
        assert claims_response.status_code == 200
        assert len(claims_response.json()) == 2
        assert events_response.status_code == 200
        assert len(events_response.json()) == 1
        assert review_items_response.status_code == 200
        review_items = review_items_response.json()
        assert len(review_items) == 1
        assert review_items[0]["status"] == "PENDING"

        accept_response = client.post(
            f"/review/items/{review_items[0]['id']}/accept",
            json={"reviewer_id": "qa", "note": "Promote the short metric claim."},
        )
        assert accept_response.status_code == 200
        assert accept_response.json()["status"] == "ACCEPTED"

        signal_response = client.get("/signals")
        assert signal_response.status_code == 200
        assert len(signal_response.json()) == 1


def test_root_and_openai_status_are_available_without_api_key(monkeypatch, tmp_path: Path) -> None:
    database_path = tmp_path / "planagent-root.db"
    monkeypatch.setenv("PLANAGENT_DATABASE_URL", build_database_url(database_path))
    monkeypatch.setenv("PLANAGENT_EVENT_BUS_BACKEND", "memory")
    monkeypatch.delenv("PLANAGENT_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    reset_settings_cache()
    reset_database_cache()

    with TestClient(create_app()) as client:
        root_response = client.get("/")
        assert root_response.status_code == 200
        assert root_response.json()["status"] == "ok"

        status_response = client.get("/admin/openai/status")
        assert status_response.status_code == 200
        payload = status_response.json()
        assert payload["configured"] is False
        assert payload["responses_api"] is True
        assert payload["primary_model"] == "openai/gpt-5.2"
        assert payload["resolved_primary_model"] == "gpt-5.2"
        assert payload["resolved_extraction_model"] == "gpt-5.2"

        test_response = client.post("/admin/openai/test", json={})
        assert test_response.status_code == 503
        assert "not configured" in test_response.json()["detail"].lower()


def test_openclaw_style_model_selector_is_normalized() -> None:
    assert resolve_openclaw_model_selector("openai/gpt-5.2") == "gpt-5.2"
    assert resolve_openclaw_model_selector("openai-codex/gpt-5.2") == "gpt-5.2"
    assert resolve_openclaw_model_selector("openai/gpt-5.4") == "gpt-5.4"
    assert resolve_openclaw_model_selector("gpt-5.2") == "gpt-5.2"
