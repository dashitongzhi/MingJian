"""Export service — render analysis/debate/simulation results to Markdown, HTML, and PDF.

Provides full report export for:
- Strategic Assistant results (analysis + debate + simulation + workbench)
- Individual debate sessions
- Simulation run reports
- Analysis results
"""

from __future__ import annotations

import io
import logging
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from planagent.services.debate_html_report import DebateHtmlReportRenderer
from planagent.services.pdf_rendering import (
    DEFAULT_MAX_PDF_DATA_URI_BYTES,
    DEFAULT_MAX_PDF_INLINE_RESOURCES,
    DEFAULT_MAX_PDF_MARKDOWN_CHARS,
    DEFAULT_MAX_PDF_OUTPUT_BYTES,
    MarkdownPdfRenderer,
    PdfPolicyViolation as _PdfPolicyViolation,
    safe_pdf_url_fetcher as _safe_pdf_url_fetcher,
)


_logger = logging.getLogger(__name__)
MAX_PDF_DATA_URI_BYTES = DEFAULT_MAX_PDF_DATA_URI_BYTES
MAX_PDF_INLINE_RESOURCES = DEFAULT_MAX_PDF_INLINE_RESOURCES
MAX_PDF_MARKDOWN_CHARS = DEFAULT_MAX_PDF_MARKDOWN_CHARS
MAX_PDF_OUTPUT_BYTES = DEFAULT_MAX_PDF_OUTPUT_BYTES
PdfPolicyViolation = _PdfPolicyViolation


class UnsafeExportPathError(ValueError):
    pass


def _safe_output_path(output_dir: Path, filename: str) -> Path:
    base = output_dir.resolve()
    candidate = Path(filename)
    if candidate.is_absolute():
        raise UnsafeExportPathError("Export filename must be relative to the output directory")
    resolved = (base / candidate).resolve(strict=False)
    if not resolved.is_relative_to(base) or resolved == base:
        raise UnsafeExportPathError("Export filename escapes the output directory")
    return resolved


def safe_pdf_url_fetcher(
    url: str,
    timeout: int = 10,
    ssl_context: object | None = None,
) -> dict[str, Any]:
    return _safe_pdf_url_fetcher(
        url,
        timeout=timeout,
        ssl_context=ssl_context,
        max_data_uri_bytes=MAX_PDF_DATA_URI_BYTES,
    )


class ExportService:
    """Export reports to Markdown and PDF formats."""

    def __init__(self, output_dir: str | Path = "exports") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.debate_html_renderer = DebateHtmlReportRenderer()

    # ── Markdown Export ───────────────────────────────────────

    def export_assistant_result_md(self, result: dict[str, Any]) -> str:
        """Export a StrategicAssistantResult to Markdown."""
        lines: list[str] = []
        _append = lines.append

        topic = result.get("topic", "Unknown Topic")
        domain = result.get("domain_id", "unknown")
        subject = result.get("subject_name", "Unknown")
        generated_at = result.get("generated_at", "")

        _append(f"# 战略决策报告：{topic}")
        _append("")
        _append(f"- **领域**: {domain}")
        _append(f"- **主题**: {subject}")
        _append(f"- **生成时间**: {generated_at}")
        _append("")
        _append("---")
        _append("")

        # Analysis Section
        analysis = result.get("analysis", {})
        if analysis:
            _append("## 一、情报分析")
            _append("")

            findings = analysis.get("findings", [])
            if findings:
                _append("### 关键发现")
                _append("")
                for i, f in enumerate(findings, 1):
                    _append(f"{i}. {f}")
                _append("")

            recommendations = analysis.get("recommendations", [])
            if recommendations:
                _append("### 建议")
                _append("")
                for i, r in enumerate(recommendations, 1):
                    _append(f"{i}. {r}")
                _append("")

            risk_factors = analysis.get("risk_factors", [])
            if risk_factors:
                _append("### 风险因素")
                _append("")
                for rf in risk_factors:
                    _append(f"- {rf}")
                _append("")

            confidence = analysis.get("confidence_score", 0)
            _append(f"**综合置信度**: {confidence:.1%}")
            _append("")

            sources = analysis.get("sources", [])
            if sources:
                _append("### 数据来源")
                _append("")
                for s in sources:
                    title = s.get("title", "Untitled")
                    url = s.get("url", "")
                    source_type = s.get("source_type", "unknown")
                    _append(f"- **[{title}]({url})** ({source_type})")
                _append("")

        # Debate Section
        debate = result.get("debate")
        if debate:
            _append("---")
            _append("")
            _append("## 二、多角色辩论")
            _append("")

            verdict = debate.get("verdict")
            if verdict:
                _append(f"**裁决结论**: {verdict}")
                _append("")

            verdict_confidence = debate.get("verdict_confidence", 0)
            _append(f"**裁决置信度**: {verdict_confidence:.1%}")
            _append("")

            rounds = debate.get("rounds", [])
            for rd in rounds:
                round_num = rd.get("round_number", "?")
                round_phase = rd.get("phase", "unknown")
                _append(f"### 第{round_num}轮 · {round_phase}")
                _append("")

                messages = rd.get("messages", [])
                for msg in messages:
                    role = msg.get("role", "unknown")
                    stance = msg.get("position") or msg.get("stance") or ""
                    content = msg.get("content", "")
                    _append(f"**[{role}]** ({stance})")
                    _append("")
                    if content:
                        _append(content)
                    for argument in msg.get("arguments", []):
                        claim = argument.get("claim") or argument.get("summary") or str(argument)
                        reasoning = argument.get("reasoning")
                        _append(f"- {claim}" + (f" — {reasoning}" if reasoning else ""))
                    for rebuttal in msg.get("rebuttals", []):
                        _append(f"- 反驳：{rebuttal.get('counter') or rebuttal}")
                    for concession in msg.get("concessions", []):
                        _append(f"- 让步：{concession.get('reason') or concession}")
                    _append("")

            recommendations = debate.get("recommendations", [])
            if recommendations:
                _append("### 辩论建议")
                _append("")
                for i, r in enumerate(recommendations, 1):
                    _append(f"{i}. {r}")
                _append("")

            risk_factors = debate.get("risk_factors", [])
            if risk_factors:
                _append("### 辩论风险提示")
                _append("")
                for rf in risk_factors:
                    _append(f"- {rf}")
                _append("")

        # Simulation Section
        simulation_run = result.get("simulation_run", {})
        if simulation_run:
            _append("---")
            _append("")
            _append("## 三、推演结果")
            _append("")
            _append(f"- **推演ID**: {simulation_run.get('id', 'N/A')}")
            _append(f"- **状态**: {simulation_run.get('status', 'N/A')}")
            _append(f"- **领域**: {simulation_run.get('domain_id', 'N/A')}")
            _append("")

        # Report Section
        latest_report = result.get("latest_report")
        if latest_report:
            _append("---")
            _append("")
            _append("## 四、详细报告")
            _append("")

            report_body = latest_report.get("report_body", "")
            if report_body:
                _append(report_body)
                _append("")

            executive_summary = latest_report.get("executive_summary", "")
            if executive_summary:
                _append("### 摘要")
                _append("")
                _append(executive_summary)
                _append("")

        # Panel Discussion
        panel = result.get("panel_discussion", [])
        if panel:
            _append("---")
            _append("")
            _append("## 五、专家讨论")
            _append("")
            for msg in panel:
                participant = msg.get("participant_id", "Unknown")
                label = msg.get("label", "")
                summary = msg.get("summary", "")
                recommendation = msg.get("recommendation", "")
                confidence = msg.get("confidence", 0)
                _append(f"### {label} ({participant})")
                _append("")
                _append(f"> {summary}")
                _append("")
                _append(f"**建议**: {recommendation} (置信度: {confidence:.1%})")
                _append("")

        # Workbench KPI
        workbench = result.get("workbench", {})
        if workbench:
            kpi = workbench.get("kpi_comparator", {})
            if kpi:
                _append("---")
                _append("")
                _append("## 六、KPI 对比")
                _append("")
                metrics = kpi.get("metrics", [])
                for m in metrics:
                    name = m.get("name", "Unknown")
                    start = m.get("start_value", "N/A")
                    end = m.get("end_value", "N/A")
                    delta = m.get("delta", "N/A")
                    _append(f"- **{name}**: {start} → {end} (变化: {delta})")
                _append("")

        _append("---")
        _append("")
        _append(f"*本报告由 PlanAgent 自动生成于 {generated_at}*")

        return "\n".join(lines)

    def export_debate_md(self, debate_data: dict[str, Any]) -> str:
        """Export a standalone debate session to Markdown."""
        lines: list[str] = []
        _append = lines.append

        topic = debate_data.get("topic", "Unknown Topic")
        _append(f"# 辩论报告：{topic}")
        _append("")
        _append(f"- **领域**: {debate_data.get('domain_id', 'unknown')}")
        _append(f"- **状态**: {debate_data.get('status', 'unknown')}")
        _append(f"- **轮次数**: {len(debate_data.get('rounds', []))}")
        _append("")
        _append("---")
        _append("")

        rounds = debate_data.get("rounds", [])
        for rd in rounds:
            round_num = rd.get("round_number", "?")
            phase = rd.get("phase", "unknown")
            _append(f"## 第{round_num}轮 · {phase}")
            _append("")

            messages = rd.get("messages") or [rd]
            for msg in messages:
                role = msg.get("role", "unknown")
                position = msg.get("position") or msg.get("stance") or ""
                content = msg.get("content", "")
                _append(f"### {role}" + (f" · {position}" if position else ""))
                _append("")
                if content:
                    _append(content)
                for argument in msg.get("arguments", []):
                    claim = argument.get("claim") or argument.get("summary") or str(argument)
                    reasoning = argument.get("reasoning")
                    _append(f"- {claim}" + (f" — {reasoning}" if reasoning else ""))
                for rebuttal in msg.get("rebuttals", []):
                    _append(f"- 反驳：{rebuttal.get('counter') or rebuttal}")
                for concession in msg.get("concessions", []):
                    _append(f"- 让步：{concession.get('reason') or concession}")
                _append("")

        verdict = debate_data.get("verdict")
        if verdict:
            _append("---")
            _append("")
            _append("## 最终裁决")
            _append("")
            _append(verdict)

        return "\n".join(lines)

    def export_analysis_md(self, analysis: dict[str, Any]) -> str:
        """Export an analysis result to Markdown."""
        lines: list[str] = []
        _append = lines.append

        _append("# 情报分析报告")
        _append("")

        domain = analysis.get("domain_id", "unknown")
        _append(f"- **领域**: {domain}")
        _append(f"- **生成时间**: {analysis.get('generated_at', 'N/A')}")
        _append("")
        _append("---")
        _append("")

        findings = analysis.get("findings", [])
        if findings:
            _append("## 关键发现")
            _append("")
            for i, f in enumerate(findings, 1):
                _append(f"{i}. {f}")
            _append("")

        recommendations = analysis.get("recommendations", [])
        if recommendations:
            _append("## 建议")
            _append("")
            for i, r in enumerate(recommendations, 1):
                _append(f"{i}. {r}")
            _append("")

        risk_factors = analysis.get("risk_factors", [])
        if risk_factors:
            _append("## 风险因素")
            _append("")
            for rf in risk_factors:
                _append(f"- {rf}")
            _append("")

        sources = analysis.get("sources", [])
        if sources:
            _append("## 数据来源")
            _append("")
            for s in sources:
                _append(
                    f"- [{s.get('title', 'Untitled')}]({s.get('url', '')}) ({s.get('source_type', '')})"
                )
            _append("")

        confidence = analysis.get("confidence_score", 0)
        _append(f"**综合置信度**: {confidence:.1%}")

        return "\n".join(lines)

    # ── PDF Export ────────────────────────────────────────────

    def md_to_pdf(self, md_content: str, title: str = "PlanAgent Report") -> bytes:
        """Convert Markdown content to PDF bytes using the restricted renderer."""
        renderer = MarkdownPdfRenderer(
            max_markdown_chars=MAX_PDF_MARKDOWN_CHARS,
            max_inline_resources=MAX_PDF_INLINE_RESOURCES,
            max_output_bytes=MAX_PDF_OUTPUT_BYTES,
            url_fetcher=safe_pdf_url_fetcher,
        )
        return renderer.render(md_content, title=title)

    # ── Jinja2 Environment ─────────────────────────────────

    async def export_debate_html(self, debate_id: str, db: AsyncSession) -> str:
        """Render a self-contained debate report from persisted debate artefacts."""
        return await self.debate_html_renderer.render(debate_id, db)

    @staticmethod
    def build_document_bundle(
        markdown: str,
        pdf_bytes: bytes,
        basename: str,
    ) -> bytes:
        """Package Markdown and PDF into a real ``format=both`` response."""
        safe_basename = re.sub(r"[^A-Za-z0-9._-]+", "_", basename).strip("._") or "report"
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(f"{safe_basename}.md", markdown.encode("utf-8"))
            archive.writestr(f"{safe_basename}.pdf", pdf_bytes)
        return buffer.getvalue()

    async def export_debate_html_file(
        self,
        debate_id: str,
        db: AsyncSession,
        output_dir: str | Path | None = None,
    ) -> str:
        """Export a debate HTML report and write it to disk.

        Args:
            debate_id: The debate session ID.
            db: An async SQLAlchemy session.
            output_dir: Directory to write the file. Defaults to ``self.output_dir``.

        Returns:
            Absolute path to the written HTML file.
        """
        html = await self.export_debate_html(debate_id, db)
        dest = Path(output_dir) if output_dir else self.output_dir
        dest.mkdir(parents=True, exist_ok=True)
        filepath = _safe_output_path(dest, f"debate_{debate_id}.html")
        filepath.write_text(html, encoding="utf-8")
        return str(filepath.resolve())

    # ── File Output ───────────────────────────────────────────

    def save_markdown(self, content: str, filename: str) -> Path:
        """Save markdown content to file."""
        filepath = _safe_output_path(self.output_dir, filename)
        filepath.write_text(content, encoding="utf-8")
        return filepath

    def save_pdf(self, pdf_bytes: bytes, filename: str) -> Path:
        """Save PDF bytes to file."""
        filepath = _safe_output_path(self.output_dir, filename)
        filepath.write_bytes(pdf_bytes)
        return filepath

    def export_and_save(
        self,
        data: dict[str, Any],
        format: str = "both",
        report_type: str = "assistant",
        filename_prefix: str = "planagent_report",
    ) -> dict[str, Path | str]:
        """Export data and save to files.

        Args:
            data: The data dict to export
            format: "md", "pdf", or "both"
            report_type: "assistant", "debate", or "analysis"
            filename_prefix: Prefix for output filenames

        Returns:
            Dict with file paths and/or content
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

        # Generate markdown
        if report_type == "assistant":
            md_content = self.export_assistant_result_md(data)
        elif report_type == "debate":
            md_content = self.export_debate_md(data)
        elif report_type == "analysis":
            md_content = self.export_analysis_md(data)
        else:
            raise ValueError(f"Unknown report_type: {report_type}")

        result: dict[str, Any] = {"markdown": md_content}

        if format in ("md", "both"):
            md_path = self.save_markdown(md_content, f"{filename_prefix}_{timestamp}.md")
            result["md_path"] = str(md_path)

        if format in ("pdf", "both"):
            title = data.get("topic", "PlanAgent Report")
            pdf_bytes = self.md_to_pdf(md_content, title=title)
            pdf_path = self.save_pdf(pdf_bytes, f"{filename_prefix}_{timestamp}.pdf")
            result["pdf_path"] = str(pdf_path)
            result["pdf_bytes"] = pdf_bytes

        return result
