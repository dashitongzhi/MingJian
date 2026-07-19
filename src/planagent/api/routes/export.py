"""Export API routes — Markdown and PDF export endpoints."""

from __future__ import annotations

import logging
import os
import tempfile
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool

from planagent.db import get_session
from planagent.domain.models import (
    DebateSessionRecord,
    DebateVerdictRecord,
    GeneratedReport,
    SimulationRun,
    StrategicBriefRecord,
    StrategicRunSnapshot,
    StrategicSession,
    utc_now,
)
from planagent.services.export import ExportService, PdfPolicyViolation
from planagent.services.debate_replay import DebateReplayService

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/export", tags=["Export"])


async def _load_debate_export_data(
    session: AsyncSession,
    debate_id: str,
) -> dict[str, Any]:
    replay = await DebateReplayService().get_replay(session, debate_id)
    verdict = replay.verdict
    return {
        "topic": replay.topic,
        "status": replay.status,
        "rounds": [
            {
                "round_number": int(round_number),
                "phase": "debate",
                "messages": messages,
            }
            for round_number, messages in sorted(
                replay.rounds_by_number.items(), key=lambda item: int(item[0])
            )
        ],
        "verdict": verdict.verdict if verdict is not None else None,
        "verdict_confidence": verdict.confidence if verdict is not None else 0,
        "recommendations": verdict.recommendations if verdict is not None else [],
        "risk_factors": verdict.risk_factors if verdict is not None else [],
    }


def _get_export_service(request: Request) -> ExportService:
    if not hasattr(request.app.state, "export_service"):
        request.app.state.export_service = ExportService(output_dir="exports")
    return request.app.state.export_service  # type: ignore[no-any-return]  # app.state 动态属性


async def _render_pdf(
    export_service: ExportService,
    md_content: str,
    title: str,
) -> bytes:
    try:
        return await run_in_threadpool(export_service.md_to_pdf, md_content, title)
    except PdfPolicyViolation as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


# ── Export Assistant Result ───────────────────────────────────


@router.get("/assistant/session/{session_id}")
async def export_assistant_session(
    session_id: str,
    request: Request,
    format: Literal["md", "pdf", "both"] = "md",
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Export a strategic assistant session to Markdown or PDF.

    Gathers the latest run snapshot + debate + report for the session
    and renders it into a downloadable document.
    """
    export_service = _get_export_service(request)

    # Load session
    strategic_session = await session.get(StrategicSession, session_id)
    if strategic_session is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    # Load latest run snapshot
    snapshot = (
        await session.scalars(
            select(StrategicRunSnapshot)
            .where(StrategicRunSnapshot.session_id == session_id)
            .order_by(StrategicRunSnapshot.generated_at.desc())
            .limit(1)
        )
    ).first()

    # Load latest brief
    brief = (
        await session.scalars(
            select(StrategicBriefRecord)
            .where(StrategicBriefRecord.session_id == session_id)
            .order_by(StrategicBriefRecord.generated_at.desc())
            .limit(1)
        )
    ).first()

    # Start from the persisted response payload instead of stale ORM field aliases.
    data: dict[str, Any] = dict(snapshot.result_payload) if snapshot is not None else {}
    defaults: dict[str, Any] = {
        "topic": strategic_session.topic,
        "domain_id": strategic_session.domain_id or "auto",
        "subject_name": strategic_session.subject_name or strategic_session.topic,
        "generated_at": (snapshot.generated_at if snapshot else utc_now()).isoformat(),
    }
    for key, value in defaults.items():
        data.setdefault(key, value)

    if brief is not None and not data.get("analysis"):
        data["analysis"] = brief.analysis_payload
    if snapshot is not None and snapshot.debate_id:
        data["debate"] = await _load_debate_export_data(session, snapshot.debate_id)

    # Generate export
    if format == "md":
        md_content = export_service.export_assistant_result_md(data)
        return Response(
            content=md_content.encode("utf-8"),
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="planagent_{session_id[:8]}.md"'
            },
        )
    elif format == "pdf":
        md_content = export_service.export_assistant_result_md(data)
        pdf_bytes = await _render_pdf(
            export_service,
            md_content,
            str(data.get("topic", "Report")),
        )
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="planagent_{session_id[:8]}.pdf"'
            },
        )
    else:  # both
        md_content = export_service.export_assistant_result_md(data)
        pdf_bytes = await _render_pdf(
            export_service,
            md_content,
            str(data.get("topic", "Report")),
        )
        basename = f"planagent_{session_id[:8]}"
        bundle = export_service.build_document_bundle(md_content, pdf_bytes, basename)
        return Response(
            content=bundle,
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{basename}.zip"',
            },
        )


# ── Compare Debates (static path BEFORE parameterized) ──────


@router.get("/debate/compare")
async def compare_debates(
    ids: str = Query(..., description="Comma-separated debate IDs (max 3)"),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Compare verdict data from up to three debates side-by-side."""
    debate_ids = [d.strip() for d in ids.split(",") if d.strip()]
    if not debate_ids:
        raise HTTPException(status_code=400, detail="No debate IDs provided")
    if len(debate_ids) > 3:
        raise HTTPException(status_code=400, detail="Maximum 3 debate IDs allowed")

    debates: list[dict[str, Any]] = []
    for did in debate_ids:
        debate = await session.get(DebateSessionRecord, did)
        if debate is None:
            raise HTTPException(status_code=404, detail=f"Debate {did} not found")

        verdict = (
            await session.scalars(
                select(DebateVerdictRecord).where(DebateVerdictRecord.debate_id == did).limit(1)
            )
        ).first()

        entry: dict[str, Any] = {
            "id": did,
            "topic": debate.topic,
            "verdict": verdict.verdict if verdict else None,
            "confidence": verdict.confidence if verdict else None,
            "winning_arguments": verdict.winning_arguments if verdict else [],
        }
        debates.append(entry)

    # Build a simple differences summary
    verdicts = [d["verdict"] for d in debates if d["verdict"]]
    confidences = [d["confidence"] for d in debates if d["confidence"] is not None]
    differences: dict[str, Any] = {
        "verdicts_match": len(set(verdicts)) <= 1 if verdicts else None,
        "confidence_range": (min(confidences), max(confidences)) if confidences else None,
        "unique_verdicts": list(set(verdicts)),
    }

    return {"debates": debates, "differences": differences}


# ── Export Debate ─────────────────────────────────────────────


@router.get("/debate/{session_id}")
async def export_debate(
    session_id: str,
    request: Request,
    format: Literal["md", "pdf"] = "md",
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Export a debate session to Markdown or PDF."""
    export_service = _get_export_service(request)

    try:
        debate_data = await _load_debate_export_data(session, session_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Debate session not found") from exc

    md_content = export_service.export_debate_md(debate_data)

    if format == "pdf":
        pdf_bytes = await _render_pdf(
            export_service,
            md_content,
            f"Debate: {debate_data['topic']}",
        )
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="debate_{session_id[:8]}.pdf"'},
        )
    else:
        return Response(
            content=md_content.encode("utf-8"),
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="debate_{session_id[:8]}.md"'},
        )


# ── Export Debate HTML ───────────────────────────────────────


@router.get("/debate/{debate_id}/html")
async def export_debate_html(
    debate_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    """Export a full debate report as a self-contained HTML page."""
    export_service = _get_export_service(request)

    try:
        html_content = await export_service.export_debate_html(debate_id, session)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=f"Debate {debate_id} not found") from exc
    except Exception:
        _logger.exception("Failed to export debate HTML for %s", debate_id)
        raise HTTPException(status_code=500, detail="Debate report generation failed")

    return HTMLResponse(
        content=html_content,
        media_type="text/html; charset=utf-8",
    )


# ── Download Debate HTML ────────────────────────────────────


def _cleanup_temp_file(path: str) -> None:
    """Remove a temporary file, ignoring errors if already deleted."""
    try:
        os.unlink(path)
    except OSError:
        pass


@router.get("/debate/{debate_id}/download")
async def download_debate_html(
    debate_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> FileResponse:
    """Generate a debate HTML report and return it as a downloadable file."""
    export_service = _get_export_service(request)

    try:
        html_content = await export_service.export_debate_html(debate_id, session)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=f"Debate {debate_id} not found") from exc
    except Exception:
        _logger.exception("Failed to download debate HTML for %s", debate_id)
        raise HTTPException(status_code=500, detail="Debate report generation failed")

    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    filename = f"debate_{debate_id[:8]}_{date_str}.html"

    tmp = tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w", encoding="utf-8")
    tmp.write(html_content)
    tmp.close()

    return FileResponse(
        path=tmp.name,
        media_type="text/html; charset=utf-8",
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        background=BackgroundTask(_cleanup_temp_file, tmp.name),
    )


# ── Export Simulation Report ─────────────────────────────────


@router.get("/simulation/{run_id}")
async def export_simulation(
    run_id: str,
    request: Request,
    format: Literal["md", "pdf"] = "md",
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Export a simulation run report to Markdown or PDF."""
    export_service = _get_export_service(request)

    run = await session.get(SimulationRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Simulation run {run_id} not found")

    report = (
        await session.scalars(
            select(GeneratedReport)
            .where(GeneratedReport.run_id == run_id)
            .order_by(GeneratedReport.created_at.desc())
            .limit(1)
        )
    ).first()

    data: dict[str, Any] = {
        "topic": f"Simulation Report: {run.domain_id}",
        "domain_id": run.domain_id,
        "subject_name": run.domain_id,
        "generated_at": run.created_at.isoformat(),
        "simulation_run": {
            "id": run.id,
            "status": run.status,
            "domain_id": run.domain_id,
        },
    }

    if report:
        data["latest_report"] = {
            "report_body": report.report_body or "",
            "executive_summary": report.executive_summary or "",
        }

    md_content = export_service.export_assistant_result_md(data)

    if format == "pdf":
        pdf_bytes = await _render_pdf(
            export_service,
            md_content,
            f"Simulation: {run.domain_id}",
        )
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="simulation_{run_id[:8]}.pdf"'},
        )
    else:
        return Response(
            content=md_content.encode("utf-8"),
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="simulation_{run_id[:8]}.md"'},
        )


# ── Export via POST (arbitrary data) ─────────────────────────


@router.post("/custom")
async def export_custom(
    request: Request,
    data: dict[str, Any],
    format: Literal["md", "pdf", "both"] = "md",
    report_type: Literal["assistant", "debate", "analysis"] = "assistant",
) -> Response:
    """Export arbitrary JSON data to Markdown or PDF.

    POST your data as JSON body, get back a rendered document.
    """
    export_service = _get_export_service(request)
    if format == "md":
        if report_type == "assistant":
            md = export_service.export_assistant_result_md(data)
        elif report_type == "debate":
            md = export_service.export_debate_md(data)
        else:
            md = export_service.export_analysis_md(data)
        return Response(
            content=md.encode("utf-8"),
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="custom_report.md"'},
        )
    else:
        if report_type == "assistant":
            md = export_service.export_assistant_result_md(data)
        elif report_type == "debate":
            md = export_service.export_debate_md(data)
        else:
            md = export_service.export_analysis_md(data)

        pdf_bytes = await _render_pdf(
            export_service,
            md,
            str(data.get("topic", "Custom Report")),
        )
        if format == "both":
            bundle = export_service.build_document_bundle(md, pdf_bytes, "custom_report")
            return Response(
                content=bundle,
                media_type="application/zip",
                headers={"Content-Disposition": 'attachment; filename="custom_report.zip"'},
            )
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="custom_report.pdf"'},
        )
