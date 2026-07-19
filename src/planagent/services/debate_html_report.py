from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from planagent.config.report_theme import get_theme
from planagent.domain.models import (
    DebateReliabilityScore,
    DebateRoundRecord,
    DebateSessionRecord,
    DebateStructuredDissent,
    DebateVerdictRecord,
)
from planagent.services.chart_generation import ChartGenerationService
from planagent.services.debate.roles import debate_record_sort_key


@dataclass(frozen=True)
class DebateReportRound:
    round_number: int
    role: str
    position: str
    position_kind: str
    confidence: float
    arguments: str
    rebuttals: str
    concessions: str


@dataclass(frozen=True)
class ReliabilityScoreView:
    argument_summary: str
    reliability_score: float
    evidence_strength: str
    bias_flags: tuple[str, ...]
    blind_spots: tuple[str, ...]
    auditor_role: str


@dataclass(frozen=True)
class StructuredDissentView:
    dissenter_role: str
    overall_dissent_strength: str
    claims: tuple[dict[str, Any], ...]
    evidence_gaps: tuple[str, ...]
    confidence_trajectory: tuple[float, ...]
    recommended_monitoring: tuple[str, ...]


@dataclass(frozen=True)
class PendingDebateVerdict:
    verdict: str = "PENDING"
    confidence: float = 0.0
    winning_arguments: tuple[str, ...] = ()
    decisive_evidence: tuple[str, ...] = ()
    conclusion_summary: str | None = None
    conditions: tuple[str, ...] = ()


def debate_position_kind(position: object) -> str:
    normalized = str(position or "").strip().upper()
    if normalized in {"SUPPORT", "ACCEPTED", "ADVOCATE"} or any(
        marker in normalized for marker in ("支持", "正方")
    ):
        return "support"
    if normalized in {"OPPOSE", "CHALLENGE", "REJECTED", "CHALLENGER"} or any(
        marker in normalized for marker in ("反对", "反方", "挑战")
    ):
        return "challenge"
    return "conditional"


def format_debate_items(items: object) -> str:
    if not items:
        return ""
    if not isinstance(items, list):
        return str(items)

    lines: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            lines.append(str(item))
            continue
        primary = item.get("claim") or item.get("counter") or item.get("reason")
        if primary is None:
            primary = item.get("summary") or item.get("content")
        text = str(primary or "").strip()
        reasoning = str(item.get("reasoning") or "").strip()
        if text and reasoning:
            lines.append(f"{text} — {reasoning}")
        elif text:
            lines.append(text)
    return "\n".join(lines)


def debate_report_rounds(records: list[DebateRoundRecord]) -> list[DebateReportRound]:
    return [
        DebateReportRound(
            round_number=record.round_number,
            role=record.role,
            position=record.position,
            position_kind=debate_position_kind(record.position),
            confidence=record.confidence,
            arguments=format_debate_items(record.arguments),
            rebuttals=format_debate_items(record.rebuttals),
            concessions=format_debate_items(record.concessions),
        )
        for record in records
    ]


def reliability_score_view(score: DebateReliabilityScore) -> ReliabilityScoreView:
    raw_score = float(score.reliability_score)
    normalized = raw_score / 5.0 if raw_score > 1.0 else raw_score
    return ReliabilityScoreView(
        argument_summary=score.argument_summary or "",
        reliability_score=max(0.0, min(normalized, 1.0)),
        evidence_strength=str(score.evidence_strength or "weak").lower(),
        bias_flags=tuple(str(item) for item in (score.bias_flags or [])),
        blind_spots=tuple(str(item) for item in (score.blind_spots or [])),
        auditor_role=score.auditor_role,
    )


def structured_dissent_view(
    dissent: DebateStructuredDissent | None,
) -> StructuredDissentView | None:
    if dissent is None:
        return None
    strength = float(dissent.overall_dissent_strength or 0.0)
    if strength >= 0.67:
        strength_label = "high"
    elif strength >= 0.34:
        strength_label = "medium"
    else:
        strength_label = "low"
    claims = tuple(_dissent_claim_view(item) for item in (dissent.claims or []))
    return StructuredDissentView(
        dissenter_role=dissent.dissenter_role,
        overall_dissent_strength=strength_label,
        claims=claims,
        evidence_gaps=tuple(str(item) for item in (dissent.evidence_gaps or [])),
        confidence_trajectory=tuple(float(item) for item in (dissent.confidence_trajectory or [])),
        recommended_monitoring=tuple(str(item) for item in (dissent.recommended_monitoring or [])),
    )


def chart_argument_view(item: object, fallback_label: str) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {"label": str(item) or fallback_label, "score": 0.5}
    label = str(item.get("claim") or item.get("label") or item.get("text") or fallback_label)
    return {"label": label, "score": _argument_strength(item.get("strength"))}


def _argument_strength(value: object) -> float:
    if isinstance(value, int | float):
        return max(0.0, min(float(value), 1.0))
    normalized = str(value or "").strip().upper()
    return {"STRONG": 0.85, "MODERATE": 0.6, "WEAK": 0.35}.get(normalized, 0.5)


def _dissent_claim_view(item: object) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {"summary": str(item), "details": "", "evidence": ""}
    summary = str(item.get("claim") or item.get("summary") or "").strip()
    details_parts = [
        str(item.get("details") or item.get("reasoning") or "").strip(),
        str(item.get("category") or "").strip(),
    ]
    confidence = item.get("confidence")
    if isinstance(confidence, int | float):
        details_parts.append(f"置信度 {float(confidence):.0%}")
    evidence = item.get("evidence") or item.get("evidence_ids") or []
    if isinstance(evidence, list):
        evidence_text = "；".join(str(entry) for entry in evidence)
    else:
        evidence_text = str(evidence or "")
    return {
        "summary": summary,
        "details": " · ".join(part for part in details_parts if part),
        "evidence": evidence_text,
    }


class DebateHtmlReportRenderer:
    def __init__(self) -> None:
        template_dir = Path(__file__).parent.parent / "templates"
        self.env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=select_autoescape(["html"]),
        )

    async def render(self, debate_id: str, db: AsyncSession) -> str:
        debate_session = await db.get(DebateSessionRecord, debate_id)
        if debate_session is None:
            raise LookupError(f"Debate {debate_id} was not found.")
        verdict: DebateVerdictRecord | None = await db.get(DebateVerdictRecord, debate_id)
        reliability_records = list(
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
        dissent = (
            await db.scalars(
                select(DebateStructuredDissent).where(
                    DebateStructuredDissent.debate_id == debate_id
                )
            )
        ).first()
        round_records = list(
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
        report_rounds = debate_report_rounds(round_records)
        reliability_scores = [reliability_score_view(score) for score in reliability_records]
        charts = ChartGenerationService.generate_all_charts(
            self._chart_data(round_records, reliability_scores)
        )
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        template = self.env.get_template("debate_report.html")
        return template.render(
            debate=SimpleNamespace(topic=debate_session.topic, id=debate_id, created_at=now),
            status=debate_session.status.lower(),
            generated_at=now,
            rounds=report_rounds,
            verdict=verdict or PendingDebateVerdict(),
            reliability_scores=reliability_scores,
            structured_dissent=structured_dissent_view(dissent),
            charts=charts,
            chart_names={
                "confidence_trajectory": "置信度趋势",
                "argument_comparison": "论点对比",
                "evidence_heatmap": "证据热力图",
                "role_radar": "角色雷达图",
            },
            theme=get_theme(),
        )

    def _chart_data(
        self,
        round_records: list[DebateRoundRecord],
        reliability_scores: list[ReliabilityScoreView],
    ) -> dict[str, Any]:
        conf_by_round: dict[int, dict[str, float]] = defaultdict(dict)
        for record in round_records:
            conf_by_round[record.round_number][record.role] = record.confidence

        evidence_matrix: dict[str, dict[str, float]] = {}
        for score in reliability_scores:
            key = score.argument_summary[:50]
            evidence_matrix.setdefault(key, {})[score.auditor_role] = score.reliability_score

        dim_sums: dict[str, list[float]] = defaultdict(list)
        for score in reliability_scores:
            dim_sums["reliability"].append(score.reliability_score)
            dim_sums["evidence"].append(
                {"strong": 0.8, "moderate": 0.5}.get(score.evidence_strength, 0.3)
            )
            dim_sums["logic"].append(max(0.0, 1.0 - len(score.bias_flags) * 0.15))
            dim_sums["adaptability"].append(0.6)

        support_args: list[dict[str, Any]] = []
        challenge_args: list[dict[str, Any]] = []
        for record in round_records:
            target = (
                support_args
                if debate_position_kind(record.position) == "support"
                else challenge_args
                if debate_position_kind(record.position) == "challenge"
                else None
            )
            if target is None:
                continue
            for index, argument in enumerate(
                record.arguments if isinstance(record.arguments, list) else []
            ):
                target.append(chart_argument_view(argument, f"{record.role}-{index + 1}"))

        return {
            "confidence_data": [
                {"round": round_number, "roles": roles}
                for round_number, roles in sorted(conf_by_round.items())
            ],
            "support_args": support_args,
            "challenge_args": challenge_args,
            "evidence_matrix": [
                {"argument": argument, "sources": sources}
                for argument, sources in evidence_matrix.items()
            ],
            "role_scores": {
                dimension: sum(values) / len(values) if values else 0.0
                for dimension, values in dim_sums.items()
            },
        }
