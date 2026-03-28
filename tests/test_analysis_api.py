from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from planagent.config import reset_settings_cache
from planagent.db import reset_database_cache
from planagent.domain.api import AnalysisRequest, AnalysisSourceRead, AnalysisStepRead
from planagent.main import create_app
from planagent.services.analysis import AutomatedAnalysisService, SourceFetchBundle


def build_database_url(path: Path) -> str:
    return f"sqlite+aiosqlite:///{path.resolve().as_posix()}"


def disable_openai(monkeypatch) -> None:
    monkeypatch.setenv("PLANAGENT_OPENAI_API_KEY", "")
    monkeypatch.setenv("PLANAGENT_OPENAI_BASE_URL", "")
    monkeypatch.setenv("PLANAGENT_OPENAI_PRIMARY_API_KEY", "")
    monkeypatch.setenv("PLANAGENT_OPENAI_PRIMARY_BASE_URL", "")
    monkeypatch.setenv("PLANAGENT_OPENAI_EXTRACTION_API_KEY", "")
    monkeypatch.setenv("PLANAGENT_OPENAI_EXTRACTION_BASE_URL", "")
    monkeypatch.setenv("PLANAGENT_OPENAI_REPORT_API_KEY", "")
    monkeypatch.setenv("PLANAGENT_OPENAI_REPORT_BASE_URL", "")
    monkeypatch.setenv("PLANAGENT_X_BEARER_TOKEN", "")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("X_BEARER_TOKEN", raising=False)


async def fake_fetch_related_sources(self, payload, query: str, domain_id: str):
    return SourceFetchBundle(
        sources=[
            AnalysisSourceRead(
                source_type="google_news_rss",
                title="GPU pricing pressure expands across cloud providers",
                url="https://example.com/gpu-pricing",
                summary="Cloud providers reported wider GPU cost pressure this week.",
                published_at="2026-03-20T09:00:00Z",
            ),
            AnalysisSourceRead(
                source_type="reddit_search",
                title="Founders discuss runway pressure after inference cost spike",
                url="https://www.reddit.com/r/artificial/comments/example",
                summary="r/artificial | Teams are revisiting pricing and infrastructure planning.",
                published_at="2026-03-20T10:00:00Z",
            ),
        ],
        steps=[
            AnalysisStepRead(
                stage="source_complete",
                message="Collected 1 item(s) from Google News.",
                detail="Requested 5; deduped total is now 1.",
            ),
            AnalysisStepRead(
                stage="source_skip",
                message="Skipped X.",
                detail="PLANAGENT_X_BEARER_TOKEN is not configured.",
            ),
        ],
    )


def test_analysis_endpoint_returns_reasoned_result(monkeypatch, tmp_path: Path) -> None:
    database_path = tmp_path / "planagent-analysis.db"
    monkeypatch.setenv("PLANAGENT_DATABASE_URL", build_database_url(database_path))
    monkeypatch.setenv("PLANAGENT_EVENT_BUS_BACKEND", "memory")
    disable_openai(monkeypatch)
    monkeypatch.setattr(AutomatedAnalysisService, "_fetch_related_sources", fake_fetch_related_sources)
    reset_settings_cache()
    reset_database_cache()

    with TestClient(create_app()) as client:
        response = client.post(
            "/analysis",
            json={
                "content": "分析 GPU 成本上涨对 AI 创业公司的影响",
                "domain_id": "corporate",
                "auto_fetch_news": True,
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "completed"
        assert payload["domain_id"] == "corporate"
        assert len(payload["sources"]) == 2
        assert payload["reasoning_steps"]
        assert payload["findings"]
        assert payload["recommendations"]
        assert any(step["stage"] == "source_skip" for step in payload["reasoning_steps"])


def test_analysis_stream_endpoint_emits_steps_sources_and_result(monkeypatch, tmp_path: Path) -> None:
    database_path = tmp_path / "planagent-analysis-stream.db"
    monkeypatch.setenv("PLANAGENT_DATABASE_URL", build_database_url(database_path))
    monkeypatch.setenv("PLANAGENT_EVENT_BUS_BACKEND", "memory")
    disable_openai(monkeypatch)
    monkeypatch.setattr(AutomatedAnalysisService, "_fetch_related_sources", fake_fetch_related_sources)
    reset_settings_cache()
    reset_database_cache()

    with TestClient(create_app()) as client:
        with client.stream(
            "POST",
            "/analysis/stream",
            json={
                "content": "分析东部战区补给线受阻之后的态势变化",
                "domain_id": "military",
                "auto_fetch_news": True,
            },
        ) as response:
            assert response.status_code == 200
            body = "".join(response.iter_text())

    assert "event: step" in body
    assert "event: source" in body
    assert "event: result" in body
    assert '"stage": "query"' in body
    assert '"stage": "source_skip"' in body
    assert "GPU pricing pressure expands across cloud providers" in body
    result_payload = None
    for chunk in body.split("\n\n"):
        if chunk.startswith("event: result"):
            data_line = next(line for line in chunk.splitlines() if line.startswith("data: "))
            result_payload = json.loads(data_line[6:])
            break
    assert result_payload is not None
    assert result_payload["status"] == "completed"


def test_analysis_request_accepts_source_toggles() -> None:
    payload = AnalysisRequest.model_validate(
        {
            "content": "Analyze AI infrastructure demand.",
            "include_google_news": True,
            "include_reddit": True,
            "include_hacker_news": False,
            "include_x": False,
            "max_news_items": 4,
            "max_reddit_items": 2,
            "max_x_items": 1,
        }
    )

    assert payload.include_reddit is True
    assert payload.include_hacker_news is False
    assert payload.include_x is False
    assert payload.max_reddit_items == 2
    assert payload.max_x_items == 1
