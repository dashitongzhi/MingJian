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

from planagent.db import get_session
from planagent.domain.models import (
    DebateRoundRecord,
    DebateSessionRecord,
    DebateVerdictRecord,
    GeneratedReport,
    SimulationRun,
    StrategicBriefRecord,
    StrategicRunSnapshot,
    StrategicSession,
    utc_now,
)
from planagent.services.export import ExportService

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/export", tags=["Export"])


def _get_export_service(request: Request) -> ExportService:
    if not hasattr(request.app.state, "export_service"):
        request.app.state.export_service = ExportService(output_dir="exports")
    return request.app.state.export_service  # type: ignore[no-any-return]  # app.state 动态属性


def _iso(value: datetime | None) -> str:
    return value.isoformat() if value else utc_now().isoformat()


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _round_item_text(item: Any) -> str:
    if isinstance(item, dict):
        return str(
            item.get("title")
            or item.get("claim")
            or item.get("summary")
            or item.get("text")
            or item.get("content")
            or item
        )
    return str(item)


def _round_content(round_record: DebateRoundRecord) -> str:
    sections: list[str] = []
    for title, items in (
        ("论点", round_record.arguments or []),
        ("质询/反驳", round_record.rebuttals or []),
        ("修正/让步", round_record.concessions or []),
    ):
        if items:
            body = "\n".join(f"- {_round_item_text(item)}" for item in items)
            sections.append(f"**{title}**\n{body}")
    if not sections:
        return round_record.position
    return "\n\n".join(sections)


def _report_data(report: GeneratedReport | None) -> dict[str, Any] | None:
    if report is None:
        return None
    return {
        "id": report.id,
        "title": report.title,
        "summary": report.summary,
        "sections": report.sections or {},
        "created_at": _iso(report.created_at),
    }


def _verdict_data(verdict: DebateVerdictRecord | None) -> dict[str, Any] | None:
    if verdict is None:
        return None
    return {
        "verdict": verdict.verdict,
        "confidence": verdict.confidence,
        "winning_arguments": verdict.winning_arguments or [],
        "decisive_evidence": verdict.decisive_evidence or [],
        "conditions": verdict.conditions or [],
        "minority_opinion": verdict.minority_opinion,
        "recommendations": verdict.recommendations or [],
        "risk_factors": verdict.risk_factors or [],
        "alternative_scenarios": verdict.alternative_scenarios or [],
        "conclusion_summary": verdict.conclusion_summary,
        "created_at": _iso(verdict.created_at),
    }


async def _debate_export_data(
    db: AsyncSession,
    debate: DebateSessionRecord,
) -> dict[str, Any]:
    run = await db.get(SimulationRun, debate.run_id) if debate.run_id else None
    context = _safe_dict(debate.context_payload)
    domain_id = run.domain_id if run else context.get("domain_id", "unknown")

    rounds = (
        await db.scalars(
            select(DebateRoundRecord)
            .where(DebateRoundRecord.debate_id == debate.id)
            .order_by(DebateRoundRecord.round_number.asc(), DebateRoundRecord.created_at.asc())
        )
    ).all()
    verdict = (
        await db.scalars(
            select(DebateVerdictRecord)
            .where(DebateVerdictRecord.debate_id == debate.id)
            .order_by(DebateVerdictRecord.created_at.desc())
            .limit(1)
        )
    ).first()

    verdict_payload = _verdict_data(verdict)
    data: dict[str, Any] = {
        "id": debate.id,
        "topic": debate.topic,
        "domain_id": domain_id,
        "status": debate.status,
        "trigger_type": debate.trigger_type,
        "rounds": [
            {
                "round_number": round_record.round_number,
                "phase": round_record.position,
                "role": round_record.role,
                "position": round_record.position,
                "confidence": round_record.confidence,
                "arguments": round_record.arguments or [],
                "rebuttals": round_record.rebuttals or [],
                "concessions": round_record.concessions or [],
                "messages": [
                    {
                        "role": round_record.role,
                        "stance": round_record.position,
                        "content": _round_content(round_record),
                    }
                ],
            }
            for round_record in rounds
        ],
    }
    if verdict_payload:
        data["verdict"] = verdict_payload
        data["verdict_confidence"] = verdict_payload["confidence"]
        data["recommendations"] = verdict_payload["recommendations"]
        data["risk_factors"] = verdict_payload["risk_factors"]
    return data


async def _assistant_export_data(
    db: AsyncSession,
    strategic_session: StrategicSession,
    snapshot: StrategicRunSnapshot | None,
    brief: StrategicBriefRecord | None,
) -> dict[str, Any]:
    data = (
        dict(snapshot.result_payload)
        if snapshot and isinstance(snapshot.result_payload, dict)
        else {}
    )
    data.setdefault("topic", strategic_session.topic)
    data.setdefault("domain_id", strategic_session.domain_id or "auto")
    data.setdefault("subject_name", strategic_session.subject_name or strategic_session.topic)
    data.setdefault("generated_at", _iso(snapshot.generated_at if snapshot else utc_now()))

    if brief and not data.get("analysis"):
        data["analysis"] = brief.analysis_payload or {}

    if snapshot and snapshot.generated_report_id and not data.get("latest_report"):
        data["latest_report"] = _report_data(
            await db.get(GeneratedReport, snapshot.generated_report_id)
        )

    debate: DebateSessionRecord | None = None
    if snapshot and snapshot.debate_id:
        debate = await db.get(DebateSessionRecord, snapshot.debate_id)
    if debate is None:
        debate = (
            await db.scalars(
                select(DebateSessionRecord)
                .where(DebateSessionRecord.topic.ilike(f"%{strategic_session.topic[:50]}%"))
                .order_by(DebateSessionRecord.created_at.desc())
                .limit(1)
            )
        ).first()
    if debate:
        data["debate"] = await _debate_export_data(db, debate)

    return data


def _markdown_response(content: str, filename: str) -> Response:
    return Response(
        content=content.encode("utf-8"),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _html_response(content: str, filename: str) -> Response:
    return Response(
        content=content.encode("utf-8"),
        media_type="text/html; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Export Assistant Result ───────────────────────────────────


@router.get("/assistant/session/{session_id}")
async def export_assistant_session(
    session_id: str,
    request: Request,
    format: Literal["md", "html"] = "md",
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Export a strategic assistant session to Markdown or HTML.

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

    data = await _assistant_export_data(session, strategic_session, snapshot, brief)

    # Generate export
    md_content = export_service.export_assistant_result_md(data)
    if format == "md":
        return _markdown_response(md_content, f"planagent_{session_id[:8]}.md")
    html_content = export_service.md_to_html(md_content, title=data.get("topic", "Report"))
    return _html_response(html_content, f"planagent_{session_id[:8]}.html")


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
    format: Literal["md", "html"] = "md",
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Export a debate session to Markdown or HTML."""
    export_service = _get_export_service(request)

    debate = await session.get(DebateSessionRecord, session_id)
    if debate is None:
        raise HTTPException(status_code=404, detail=f"Debate session {session_id} not found")

    debate_data = await _debate_export_data(session, debate)
    md_content = export_service.export_debate_md(debate_data)

    if format == "md":
        return _markdown_response(md_content, f"debate_{session_id[:8]}.md")
    html_content = export_service.md_to_html(md_content, title=f"Debate: {debate.topic}")
    return _html_response(html_content, f"debate_{session_id[:8]}.html")


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
    except Exception:
        _logger.exception("Failed to export debate HTML for %s", debate_id)
        raise HTTPException(status_code=404, detail=f"Debate {debate_id} not found")

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
    except Exception:
        _logger.exception("Failed to download debate HTML for %s", debate_id)
        raise HTTPException(status_code=404, detail=f"Debate {debate_id} not found")

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
    format: Literal["md", "html"] = "md",
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Export a simulation run report to Markdown or HTML."""
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
        data["latest_report"] = _report_data(report)

    md_content = export_service.export_assistant_result_md(data)

    if format == "md":
        return _markdown_response(md_content, f"simulation_{run_id[:8]}.md")
    html_content = export_service.md_to_html(md_content, title=f"Simulation: {run.domain_id}")
    return _html_response(html_content, f"simulation_{run_id[:8]}.html")


# ── Export via POST (arbitrary data) ─────────────────────────


@router.post("/custom")
async def export_custom(
    request: Request,
    format: Literal["md", "html"] = "md",
    report_type: Literal["assistant", "debate", "analysis"] = "assistant",
) -> Response:
    """Export arbitrary JSON data to Markdown or HTML.

    POST your data as JSON body, get back a rendered document.
    """
    export_service = _get_export_service(request)
    data = await request.json()

    if format == "md":
        if report_type == "assistant":
            md = export_service.export_assistant_result_md(data)
        elif report_type == "debate":
            md = export_service.export_debate_md(data)
        else:
            md = export_service.export_analysis_md(data)
        return _markdown_response(md, "custom_report.md")
    else:
        if report_type == "assistant":
            md = export_service.export_assistant_result_md(data)
        elif report_type == "debate":
            md = export_service.export_debate_md(data)
        else:
            md = export_service.export_analysis_md(data)

        html_content = export_service.md_to_html(md, title=data.get("topic", "Custom Report"))
        return _html_response(html_content, "custom_report.html")
