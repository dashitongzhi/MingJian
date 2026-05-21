"""Export service — render analysis/debate/simulation results to Markdown, HTML, and PDF.

Provides full report export for:
- Strategic Assistant results (analysis + debate + simulation + workbench)
- Individual debate sessions
- Simulation run reports
- Analysis results
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any

from types import SimpleNamespace

import markdown2
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from planagent.config.report_theme import get_theme
from planagent.domain.models import (
    DebateReliabilityScore,
    DebateRoundRecord,
    DebateStructuredDissent,
    DebateVerdictRecord,
)
from planagent.services.chart_generation import ChartGenerationService
from planagent.services.debate.roles import debate_record_sort_key


_logger = logging.getLogger(__name__)


class ExportService:
    """Export reports to Markdown and PDF formats."""

    def __init__(self, output_dir: str | Path = "exports") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

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

        # Workflow Section
        workflow = result.get("workflow") or {}
        if isinstance(workflow, dict) and workflow:
            _append("## 工作流状态")
            _append("")
            _append(f"- **当前状态**: {workflow.get('status', 'unknown')}")
            _append(f"- **可辅助决策**: {'是' if workflow.get('user_can_decide') else '否'}")
            phases = workflow.get("phases") or []
            if phases:
                _append("")
                _append("### 阶段进度")
                _append("")
                for phase in phases:
                    if not isinstance(phase, dict):
                        continue
                    label = phase.get("label") or phase.get("key") or "阶段"
                    status = phase.get("status") or "unknown"
                    detail = []
                    if phase.get("count") is not None:
                        detail.append(f"数量: {phase.get('count')}")
                    if phase.get("next_poll_at"):
                        detail.append(f"下次更新: {phase.get('next_poll_at')}")
                    suffix = f" ({'; '.join(detail)})" if detail else ""
                    _append(f"- **{label}**: {status}{suffix}")
                _append("")

        monitoring = result.get("monitoring") or {}
        if isinstance(monitoring, dict) and monitoring:
            _append("## 监控状态")
            _append("")
            _append(f"- **版本**: {monitoring.get('edition', 'unknown')}")
            _append(f"- **模式**: {monitoring.get('mode', 'local')}")
            _append(f"- **状态**: {monitoring.get('status', 'unknown')}")
            if monitoring.get("watch_rule_id"):
                _append(f"- **监控规则**: {monitoring.get('watch_rule_id')}")
            if monitoring.get("poll_interval_minutes") is not None:
                _append(f"- **轮询间隔**: {monitoring.get('poll_interval_minutes')} 分钟")
            if monitoring.get("next_poll_at"):
                _append(f"- **下次更新**: {monitoring.get('next_poll_at')}")
            if monitoring.get("message"):
                _append(f"- **说明**: {monitoring.get('message')}")
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

            confidence = analysis.get("confidence_score")
            if isinstance(confidence, (int, float)):
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
            verdict_data = verdict if isinstance(verdict, dict) else {}
            if verdict_data:
                _append(f"**裁决结论**: {verdict_data.get('verdict', 'N/A')}")
                if verdict_data.get("conclusion_summary"):
                    _append("")
                    _append(str(verdict_data["conclusion_summary"]))
                verdict_confidence = verdict_data.get("confidence")
                if isinstance(verdict_confidence, (int, float)):
                    _append("")
                    _append(f"**裁决置信度**: {verdict_confidence:.1%}")
                _append("")
            elif verdict:
                _append(f"**裁决结论**: {verdict}")
                _append("")

            verdict_confidence = debate.get("verdict_confidence")
            if isinstance(verdict_confidence, (int, float)) and not verdict_data:
                _append(f"**裁决置信度**: {verdict_confidence:.1%}")
                _append("")

            rounds = debate.get("rounds", [])
            for rd in rounds:
                if not isinstance(rd, dict):
                    continue
                round_num = rd.get("round_number", "?")
                round_phase = rd.get("phase", "unknown")
                _append(f"### 第{round_num}轮 · {round_phase}")
                _append("")

                messages = rd.get("messages", [])
                for msg in messages:
                    if not isinstance(msg, dict):
                        continue
                    role = msg.get("role", "unknown")
                    stance = msg.get("stance", "")
                    content = msg.get("content", "")
                    _append(f"**[{role}]** ({stance})")
                    _append("")
                    _append(content)
                    _append("")

                if not messages and rd.get("position"):
                    _append(f"**[{rd.get('role', 'agent')}]**")
                    _append("")
                    _append(str(rd.get("position", "")))
                    _append("")

            recommendations = (
                debate.get("recommendations") or verdict_data.get("recommendations") or []
            )
            if recommendations:
                _append("### 辩论建议")
                _append("")
                for i, r in enumerate(recommendations, 1):
                    if isinstance(r, dict):
                        text = r.get("title") or r.get("summary") or r.get("text") or r
                    else:
                        text = r
                    _append(f"{i}. {text}")
                _append("")

            risk_factors = debate.get("risk_factors") or verdict_data.get("risk_factors") or []
            if risk_factors:
                _append("### 辩论风险提示")
                _append("")
                for rf in risk_factors:
                    _append(f"- {rf}")
                _append("")

            minority_opinion = verdict_data.get("minority_opinion")
            if minority_opinion:
                _append("### 少数意见")
                _append("")
                _append(str(minority_opinion))
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
            sections = latest_report.get("sections") if isinstance(latest_report, dict) else {}
            sections = sections if isinstance(sections, dict) else {}
            if report_body:
                _append(report_body)
                _append("")

            executive_summary = (
                latest_report.get("executive_summary", "")
                or sections.get("executive_summary", "")
                or latest_report.get("summary", "")
            )
            if executive_summary:
                _append("### 摘要")
                _append("")
                _append(executive_summary)
                _append("")

            strategy_recommendations = sections.get("strategy_recommendations") or []
            if strategy_recommendations:
                _append("### 报告建议")
                _append("")
                for i, item in enumerate(strategy_recommendations, 1):
                    _append(f"{i}. {item}")
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
                    name = m.get("name") or m.get("metric") or "Unknown"
                    start = m.get("start_value", m.get("start", "N/A"))
                    end = m.get("end_value", m.get("end", "N/A"))
                    delta = m.get("delta", "N/A")
                    _append(f"- **{name}**: {start} → {end} (变化: {delta})")
                _append("")

        recommendation_versions = result.get("recommendation_versions") or []
        if recommendation_versions:
            _append("---")
            _append("")
            _append("## 七、建议版本")
            _append("")
            for version in recommendation_versions[:10]:
                if not isinstance(version, dict):
                    continue
                number = version.get("version_number", "?")
                trigger = version.get("trigger_type", "update")
                significance = version.get("significance", "none")
                summary = version.get("recommendation_summary", "")
                _append(f"### v{number} · {trigger} · {significance}")
                _append("")
                if version.get("change_summary"):
                    _append(f"- 变化说明: {version.get('change_summary')}")
                if summary:
                    _append(str(summary))
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

            for msg in rd.get("messages", []):
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                _append(f"### {role}")
                _append("")
                _append(content)
                _append("")

        verdict = debate_data.get("verdict")
        if verdict:
            _append("---")
            _append("")
            _append("## 最终裁决")
            _append("")
            verdict_data = verdict if isinstance(verdict, dict) else {}
            if verdict_data:
                _append(str(verdict_data.get("verdict", "N/A")))
                if verdict_data.get("conclusion_summary"):
                    _append("")
                    _append(str(verdict_data["conclusion_summary"]))
                confidence = verdict_data.get("confidence")
                if isinstance(confidence, (int, float)):
                    _append("")
                    _append(f"**置信度**: {confidence:.1%}")
            else:
                _append(str(verdict))

            recommendations = debate_data.get("recommendations") or verdict_data.get(
                "recommendations"
            )
            if recommendations:
                _append("")
                _append("### 建议")
                _append("")
                for i, item in enumerate(recommendations, 1):
                    if isinstance(item, dict):
                        text = item.get("title") or item.get("summary") or item.get("text") or item
                    else:
                        text = item
                    _append(f"{i}. {text}")

            risk_factors = debate_data.get("risk_factors") or verdict_data.get("risk_factors")
            if risk_factors:
                _append("")
                _append("### 风险提示")
                _append("")
                for item in risk_factors:
                    _append(f"- {item}")

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

    def md_to_html(self, md_content: str, title: str = "PlanAgent Report") -> str:
        """Convert Markdown content to a self-contained HTML report."""
        html_content = markdown2.markdown(
            md_content,
            extras=[
                "tables",
                "fenced-code-blocks",
                "code-friendly",
                "header-ids",
                "toc",
                "metadata",
            ],
        )
        safe_title = escape(title)
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{safe_title}</title>
    <style>
        body {{
            margin: 0;
            background: #f8f4ed;
            color: #201a17;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans SC", "PingFang SC",
                         "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
            line-height: 1.72;
        }}
        main {{
            max-width: 920px;
            margin: 0 auto;
            padding: 44px 24px 72px;
        }}
        h1, h2, h3 {{ line-height: 1.25; }}
        h1 {{
            font-size: 32px;
            border-bottom: 1px solid #d7c7b7;
            padding-bottom: 16px;
        }}
        h2 {{
            margin-top: 34px;
            font-size: 22px;
            border-bottom: 1px solid #e5d8ca;
            padding-bottom: 8px;
        }}
        h3 {{ margin-top: 24px; font-size: 16px; }}
        a {{ color: #9a4f2f; }}
        blockquote {{
            margin: 16px 0;
            border-left: 3px solid #b8653f;
            padding: 8px 16px;
            background: #fffaf3;
        }}
        code, pre {{
            background: #241f1b;
            color: #f5eee5;
            border-radius: 6px;
        }}
        code {{ padding: 2px 5px; }}
        pre {{ padding: 14px; overflow-x: auto; }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 16px 0;
        }}
        th, td {{
            border: 1px solid #decec0;
            padding: 8px 10px;
            text-align: left;
        }}
        th {{ background: #efe3d5; }}
    </style>
</head>
<body>
<main>
{html_content}
</main>
</body>
</html>"""

    def md_to_pdf(self, md_content: str, title: str = "PlanAgent Report") -> bytes:
        """Convert Markdown content to PDF bytes using weasyprint."""
        import weasyprint

        # Convert MD to HTML
        html_content = markdown2.markdown(
            md_content,
            extras=[
                "tables",
                "fenced-code-blocks",
                "code-friendly",
                "header-ids",
                "toc",
                "metadata",
            ],
        )

        # Wrap in full HTML with styling
        full_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8">
    <title>{title}</title>
    <style>
        @page {{
            size: A4;
            margin: 2cm 2.5cm;
            @top-center {{
                content: "PlanAgent - {title}";
                font-size: 9px;
                color: #666;
            }}
            @bottom-center {{
                content: "第 " counter(page) " 页";
                font-size: 9px;
                color: #666;
            }}
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans SC", "PingFang SC",
                         "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
            font-size: 11pt;
            line-height: 1.7;
            color: #1a1a2e;
        }}
        h1 {{
            color: #0f3460;
            border-bottom: 3px solid #0f3460;
            padding-bottom: 8px;
            font-size: 20pt;
            margin-top: 30px;
        }}
        h2 {{
            color: #16213e;
            border-bottom: 1px solid #ddd;
            padding-bottom: 5px;
            font-size: 15pt;
            margin-top: 25px;
        }}
        h3 {{
            color: #1a1a2e;
            font-size: 12pt;
            margin-top: 18px;
        }}
        ul, ol {{
            padding-left: 25px;
        }}
        li {{
            margin-bottom: 4px;
        }}
        blockquote {{
            border-left: 4px solid #0f3460;
            margin: 12px 0;
            padding: 8px 16px;
            background: #f8f9fa;
            color: #333;
        }}
        table {{
            border-collapse: collapse;
            width: 100%;
            margin: 12px 0;
        }}
        th, td {{
            border: 1px solid #ddd;
            padding: 8px 12px;
            text-align: left;
        }}
        th {{
            background: #0f3460;
            color: white;
        }}
        tr:nth-child(even) {{
            background: #f8f9fa;
        }}
        code {{
            background: #f0f0f0;
            padding: 2px 6px;
            border-radius: 3px;
            font-size: 10pt;
        }}
        pre {{
            background: #1a1a2e;
            color: #e0e0e0;
            padding: 12px;
            border-radius: 6px;
            overflow-x: auto;
        }}
        pre code {{
            background: none;
            padding: 0;
            color: #e0e0e0;
        }}
        strong {{
            color: #0f3460;
        }}
        a {{
            color: #0f3460;
            text-decoration: none;
        }}
        hr {{
            border: none;
            border-top: 2px solid #eee;
            margin: 20px 0;
        }}
        em {{
            color: #555;
        }}
    </style>
</head>
<body>
{html_content}
</body>
</html>"""

        # Generate PDF
        pdf_bytes = weasyprint.HTML(string=full_html).write_pdf()
        return pdf_bytes

    # ── Jinja2 Environment ─────────────────────────────────

    @staticmethod
    def _get_jinja_env() -> Environment:
        """Return a Jinja2 environment pointed at the project templates dir."""
        template_dir = Path(__file__).parent.parent / "templates"
        return Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=select_autoescape(["html"]),
        )

    # ── HTML Export ────────────────────────────────────────

    async def export_debate_html(self, debate_id: str, db: AsyncSession) -> str:
        """Export a full debate report as a self-contained HTML string.

        Queries all debate artefacts from the database, generates charts,
        and renders the ``debate_report.html`` Jinja2 template.

        Args:
            debate_id: The debate session ID.
            db: An async SQLAlchemy session.

        Returns:
            Complete HTML document as a string.
        """
        # ── Query artefacts ─────────────────────────────────
        verdict: DebateVerdictRecord | None = await db.get(DebateVerdictRecord, debate_id)

        reliability_scores: list[DebateReliabilityScore] = list(
            (
                await db.scalars(
                    select(DebateReliabilityScore)
                    .where(DebateReliabilityScore.debate_id == debate_id)
                    .order_by(
                        DebateReliabilityScore.round_number.asc(),
                        DebateReliabilityScore.role.asc(),
                    )
                )
            ).all()
        )

        dissent: DebateStructuredDissent | None = (
            await db.scalars(
                select(DebateStructuredDissent).where(
                    DebateStructuredDissent.debate_id == debate_id
                )
            )
        ).first()

        round_records: list[DebateRoundRecord] = list(
            (
                await db.scalars(
                    select(DebateRoundRecord)
                    .where(DebateRoundRecord.debate_id == debate_id)
                    .order_by(
                        DebateRoundRecord.round_number.asc(),
                        DebateRoundRecord.created_at.asc(),
                    )
                )
            ).all()
        )
        round_records.sort(key=debate_record_sort_key)

        # ── Build debate_data for chart generation ──────────
        rounds_by_number: dict[int, dict] = {}
        for rec in round_records:
            rn = rec.round_number
            if rn not in rounds_by_number:
                rounds_by_number[rn] = {
                    "round_number": rn,
                    "phase": "debate",
                    "messages": [],
                }
            rounds_by_number[rn]["messages"].append(
                {
                    "role": rec.role,
                    "position": rec.position,
                    "confidence": rec.confidence,
                    "arguments": rec.arguments,
                }
            )

        sorted_rounds = [rounds_by_number[k] for k in sorted(rounds_by_number)]

        # ── Aggregate confidence_data per round for chart format [{round, roles: {role: val}}]
        conf_by_round: dict[int, dict[str, float]] = defaultdict(dict)
        for rec in round_records:
            conf_by_round[rec.round_number][rec.role] = rec.confidence
        confidence_data = [
            {"round": rn, "roles": roles} for rn, roles in sorted(conf_by_round.items())
        ]

        # ── Build evidence_matrix grouped by argument_summary [{argument, sources: {role: score}}]
        ev_matrix: dict[str, dict[str, float]] = {}
        for score in reliability_scores:
            key = (score.argument_summary or "")[:50]
            ev_matrix.setdefault(key, {})[score.auditor_role] = score.reliability_score / 5.0
        evidence_matrix = [{"argument": k, "sources": v} for k, v in ev_matrix.items()]

        # ── Build role_scores for radar chart: flat {dimension: score} in [0,1]
        # The radar chart expects {dimension_name: score, ...} — aggregate across roles
        dim_sums: dict[str, list[float]] = defaultdict(list)
        for score in reliability_scores:
            dim_sums["reliability"].append(score.reliability_score / 5.0)
            if score.evidence_strength == "strong":
                dim_sums["evidence"].append(0.8)
            elif score.evidence_strength == "moderate":
                dim_sums["evidence"].append(0.5)
            else:
                dim_sums["evidence"].append(0.3)
            bias_penalty = len(score.bias_flags or []) * 0.15
            dim_sums["logic"].append(max(0.0, 1.0 - bias_penalty))
            dim_sums["adaptability"].append(0.6)
        role_scores = {
            dim: sum(vals) / len(vals) if vals else 0.0 for dim, vals in dim_sums.items()
        }

        debate_data: dict[str, Any] = {
            "confidence_data": confidence_data,
            "support_args": [
                a
                for rec in round_records
                if rec.position == "support"
                for a in (rec.arguments if isinstance(rec.arguments, list) else [])
            ],
            "challenge_args": [
                a
                for rec in round_records
                if rec.position == "challenge"
                for a in (rec.arguments if isinstance(rec.arguments, list) else [])
            ],
            "evidence_matrix": evidence_matrix,
            "role_scores": dict(role_scores),
        }

        charts = ChartGenerationService.generate_all_charts(debate_data)

        theme = get_theme()

        chart_names = {
            "confidence_trajectory": "置信度趋势",
            "argument_comparison": "论点对比",
            "evidence_heatmap": "证据热力图",
            "role_radar": "角色雷达图",
        }

        topic = verdict.topic if verdict else "未知主题"
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        env = self._get_jinja_env()
        template = env.get_template("debate_report.html")
        return template.render(
            debate=SimpleNamespace(
                topic=topic,
                id=debate_id,
                created_at=now,
            ),
            status="completed" if verdict else "in_progress",
            generated_at=now,
            rounds=sorted_rounds,
            verdict=verdict,
            reliability_scores=reliability_scores,
            structured_dissent=dissent,
            charts=charts,
            chart_names=chart_names,
            theme=theme,
        )

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
        filepath = dest / f"debate_{debate_id}.html"
        filepath.write_text(html, encoding="utf-8")
        return str(filepath.resolve())

    # ── File Output ───────────────────────────────────────────

    def save_markdown(self, content: str, filename: str) -> Path:
        """Save markdown content to file."""
        filepath = self.output_dir / filename
        filepath.write_text(content, encoding="utf-8")
        return filepath

    def save_pdf(self, pdf_bytes: bytes, filename: str) -> Path:
        """Save PDF bytes to file."""
        filepath = self.output_dir / filename
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
