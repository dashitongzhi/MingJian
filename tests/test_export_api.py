from __future__ import annotations

import asyncio
import io
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from planagent.config import reset_settings_cache
from planagent.db import get_database, reset_database_cache
from planagent.domain.models import (
    DebateRoundRecord,
    DebateSessionRecord,
    DebateVerdictRecord,
    StrategicRunSnapshot,
    StrategicSession,
)
from planagent.main import create_app
from planagent.services.export import ExportService, PdfPolicyViolation


def _database_url(path: Path) -> str:
    return f"sqlite+aiosqlite:///{path.resolve().as_posix()}"


async def _seed_export_records() -> None:
    async with get_database().session() as session:
        session.add(
            StrategicSession(
                id="session-export",
                name="Export session",
                topic="Should we expand?",
                domain_id="corporate",
            )
        )
        session.add(
            DebateSessionRecord(
                id="debate-export",
                topic="Expansion debate",
                trigger_type="manual",
                status="COMPLETED",
                target_type="run",
            )
        )
        session.add(
            DebateRoundRecord(
                debate_id="debate-export",
                round_number=1,
                role="advocate",
                position="support",
                confidence=0.8,
                arguments=[{"claim": "Round claim", "reasoning": "Grounded reasoning"}],
                rebuttals=[],
                concessions=[],
            )
        )
        session.add(
            DebateVerdictRecord(
                debate_id="debate-export",
                topic="Expansion debate",
                trigger_type="manual",
                rounds_completed=1,
                verdict="CONDITIONAL",
                confidence=0.8,
                winning_arguments=["Round claim"],
                decisive_evidence=["source-1"],
            )
        )
        session.add(
            StrategicRunSnapshot(
                id="snapshot-export",
                session_id="session-export",
                debate_id="debate-export",
                result_payload={
                    "topic": "Should we expand?",
                    "domain_id": "corporate",
                    "subject_name": "Expansion",
                    "analysis": {
                        "findings": ["Evidence-backed finding"],
                        "recommendations": ["Proceed conditionally"],
                        "confidence_score": 0.75,
                    },
                },
            )
        )
        await session.commit()


def test_assistant_both_export_uses_persisted_payload_and_returns_zip(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("PLANAGENT_DATABASE_URL", _database_url(tmp_path / "export.db"))
    monkeypatch.setenv("PLANAGENT_EVENT_BUS_BACKEND", "memory")
    monkeypatch.setenv("PLANAGENT_OPENAI_API_KEY", "")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(ExportService, "md_to_pdf", lambda *_args, **_kwargs: b"%PDF-test")
    reset_settings_cache()
    reset_database_cache()

    with TestClient(create_app()) as client:
        asyncio.run(_seed_export_records())
        response = client.get("/export/assistant/session/session-export?format=both")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/zip")
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert archive.namelist() == ["planagent_session-.md", "planagent_session-.pdf"]
        markdown = archive.read("planagent_session-.md").decode("utf-8")
        assert "Evidence-backed finding" in markdown
        assert "Round claim" in markdown
        assert archive.read("planagent_session-.pdf") == b"%PDF-test"


def test_debate_export_includes_persisted_rounds(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PLANAGENT_DATABASE_URL", _database_url(tmp_path / "debate-export.db"))
    monkeypatch.setenv("PLANAGENT_EVENT_BUS_BACKEND", "memory")
    monkeypatch.setenv("PLANAGENT_OPENAI_API_KEY", "")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    reset_settings_cache()
    reset_database_cache()

    with TestClient(create_app()) as client:
        asyncio.run(_seed_export_records())
        response = client.get("/export/debate/debate-export")
        html_response = client.get("/export/debate/debate-export/html")
        missing_html = client.get("/export/debate/debate-missing/html")

    assert response.status_code == 200
    assert "Round claim" in response.text
    assert html_response.status_code == 200
    assert "Round claim" in html_response.text
    assert "advocate" in html_response.text
    assert missing_html.status_code == 404


def test_custom_export_rejects_non_object_payload(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PLANAGENT_DATABASE_URL", _database_url(tmp_path / "custom-export.db"))
    monkeypatch.setenv("PLANAGENT_EVENT_BUS_BACKEND", "memory")
    monkeypatch.setenv("PLANAGENT_OPENAI_API_KEY", "")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    reset_settings_cache()
    reset_database_cache()

    with TestClient(create_app()) as client:
        response = client.post("/export/custom", json=["not", "an", "object"])

    assert response.status_code == 422


def test_custom_pdf_export_maps_policy_violation_to_client_error(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("PLANAGENT_DATABASE_URL", _database_url(tmp_path / "custom-pdf-policy.db"))
    monkeypatch.setenv("PLANAGENT_EVENT_BUS_BACKEND", "memory")
    monkeypatch.setenv("PLANAGENT_OPENAI_API_KEY", "")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    def reject_pdf(*_args, **_kwargs) -> bytes:
        raise PdfPolicyViolation("PDF Markdown exceeds the size limit", status_code=413)

    monkeypatch.setattr(ExportService, "md_to_pdf", reject_pdf)
    reset_settings_cache()
    reset_database_cache()

    with TestClient(create_app()) as client:
        response = client.post(
            "/export/custom?format=pdf",
            json={"topic": "Oversized export"},
        )

    assert response.status_code == 413
    assert response.json()["detail"] == "PDF Markdown exceeds the size limit"
