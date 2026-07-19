from __future__ import annotations

from dataclasses import dataclass
import re

from planagent.domain.api import AnalysisResponse, PanelDiscussionMessageRead


@dataclass(frozen=True)
class DebateSuggestion:
    """Result of conflict detection over an analysis response."""

    warranted: bool
    confidence: float
    reasons: list[str]
    suggested_topic: str
    conflicting_signals: list[str]
    risk_score: float = 0.0
    opportunity_score: float = 0.0


_RISK_KEYWORDS = {
    "risk",
    "risks",
    "risky",
    "threat",
    "threats",
    "danger",
    "dangerous",
    "loss",
    "losses",
    "decline",
    "declining",
    "drop",
    "fall",
    "fell",
    "delay",
    "delayed",
    "cancel",
    "canceled",
    "disrupt",
    "disrupted",
    "downside",
    "volatile",
    "volatility",
    "uncertain",
    "uncertainty",
    "concern",
    "concerns",
    "warning",
    "caution",
    "cautionary",
    "challenge",
    "challenges",
    "headwind",
    "headwinds",
    "风险",
    "威胁",
    "危险",
    "损失",
    "下降",
    "衰退",
    "延迟",
    "中断",
    "波动",
    "不确定",
    "担忧",
    "警告",
    "挑战",
    "困境",
    "危机",
    "隐患",
    "制裁",
    "冲突",
    "战争",
    "对抗",
    "恶化",
    "下滑",
    "萎缩",
    "动荡",
    "陷阱",
    "瓶颈",
    "短板",
    "漏洞",
    "软肋",
}
_OPPORTUNITY_KEYWORDS = {
    "opportunity",
    "opportunities",
    "growth",
    "growing",
    "grow",
    "increase",
    "increased",
    "improve",
    "improved",
    "gain",
    "gains",
    "upside",
    "bullish",
    "optimistic",
    "positive",
    "strength",
    "strong",
    "launch",
    "launched",
    "expand",
    "expanding",
    "momentum",
    "catalyst",
    "catalysts",
    "tailwind",
    "tailwinds",
    "机遇",
    "机会",
    "增长",
    "提升",
    "改善",
    "突破",
    "创新",
    "发展",
    "扩张",
    "优势",
    "潜力",
    "红利",
    "赋能",
    "升级",
    "转型",
    "跃迁",
    "利好",
    "提振",
    "升温",
    "向好",
    "回暖",
    "复苏",
    "加速",
}
_UNCERTAINTY_KEYWORDS = {
    "uncertain",
    "uncertainty",
    "unclear",
    "ambiguous",
    "mixed",
    "conflicting",
    "conflict",
    "diverge",
    "divergent",
    "contested",
    "debate",
    "debated",
    "disputed",
    "controversial",
    "however",
    "although",
    "despite",
    "nevertheless",
    "on the other hand",
    "could go either",
    "high risk high reward",
    "volatile",
    "不确定",
    "模糊",
    "矛盾",
    "分歧",
    "争议",
    "两难",
    "博弈",
    "然而",
    "但是",
    "尽管",
    "虽然",
    "另一方面",
    "高风险高回报",
    "见仁见智",
    "众说纷纭",
    "尚不明朗",
    "有待观察",
    "变数",
}

_SOURCE_TYPE_DIVERSITY_THRESHOLD = 3
_LOW_CONFIDENCE_THRESHOLD = 0.55
_MODERATE_CONFIDENCE_THRESHOLD = 0.65


class AssistantConflictDetector:
    """Detect whether evidence tension warrants a structured debate."""

    def detect(
        self,
        analysis: AnalysisResponse,
        domain_id: str,
        subject_name: str,
        panel_messages: list[PanelDiscussionMessageRead] | None = None,
    ) -> DebateSuggestion:
        reasons: list[str] = []
        conflicting_signals: list[str] = []

        confidence = self._derive_analysis_confidence(analysis)
        if confidence < _LOW_CONFIDENCE_THRESHOLD:
            reasons.append(
                f"Analysis confidence is critically low ({confidence:.0%}), "
                "suggesting the evidence is thin or ambiguous."
            )
            conflicting_signals.append("low_confidence")
        elif confidence < _MODERATE_CONFIDENCE_THRESHOLD:
            reasons.append(
                f"Analysis confidence is moderate ({confidence:.0%}), "
                "indicating room for deeper investigation."
            )
            conflicting_signals.append("moderate_confidence")

        if panel_messages:
            stances = {message.stance for message in panel_messages}
            if "support" in stances and "challenge" in stances:
                reasons.append(
                    "Panel agents disagree on stance: some support while others challenge the direction."
                )
                conflicting_signals.append("panel_disagreement")
            average_confidence = sum(message.confidence for message in panel_messages) / len(
                panel_messages
            )
            if average_confidence < 0.60:
                reasons.append(
                    f"Average panel confidence is low ({average_confidence:.0%}), "
                    "indicating broad uncertainty."
                )
                conflicting_signals.append("low_panel_confidence")

        risk_score, opportunity_score = self._compute_risk_opportunity_scores(analysis)
        if risk_score >= 0.35 and opportunity_score >= 0.35:
            reasons.append(
                f"Both risk signals ({risk_score:.0%}) and opportunity signals "
                f"({opportunity_score:.0%}) are strong."
            )
            conflicting_signals.append("risk_opportunity_tension")

        finding_conflicts = self._detect_per_finding_conflicts(analysis)
        if finding_conflicts:
            reasons.append(
                f"{len(finding_conflicts)} finding(s) contain both risk and opportunity signals, "
                "suggesting mixed assessments."
            )
            conflicting_signals.append("finding_level_conflict")

        if self._detect_source_contradiction(analysis):
            reasons.append(
                "Multiple data sources present divergent signals, indicating cross-source contradiction."
            )
            conflicting_signals.append("source_contradiction")

        uncertainty_density = self._compute_uncertainty_density(analysis)
        if uncertainty_density >= 0.3:
            reasons.append(
                f"Summary contains high uncertainty language density ({uncertainty_density:.0%}), "
                "suggesting the situation is fluid or contested."
            )
            conflicting_signals.append("high_uncertainty_language")

        warranted = bool(reasons)
        if warranted:
            tension_label = conflicting_signals[0].replace("_", " ")
            suggested_topic = (
                f"Given {tension_label} around {subject_name}, "
                "should the current strategy be revised?"
            )
        else:
            suggested_topic = self._default_debate_topic(domain_id, subject_name)

        return DebateSuggestion(
            warranted=warranted,
            confidence=confidence,
            reasons=reasons,
            suggested_topic=suggested_topic,
            conflicting_signals=conflicting_signals,
            risk_score=risk_score,
            opportunity_score=opportunity_score,
        )

    @staticmethod
    def _default_debate_topic(domain_id: str, subject_name: str) -> str:
        if domain_id == "military":
            return f"Should {subject_name} adjust its current operational posture?"
        return f"Should {subject_name} change its current business posture?"

    @staticmethod
    def _derive_analysis_confidence(analysis: AnalysisResponse) -> float:
        score = 0.5
        source_count = len(analysis.sources)
        score += min(source_count / 15.0, 0.2)
        score += min(len(analysis.findings) / 6.0, 0.15)
        score += min(len(analysis.recommendations) / 5.0, 0.1)
        summary_length = len(analysis.summary)
        if summary_length > 200:
            score += 0.05
        elif summary_length < 50:
            score -= 0.1
        uncertainty_hits = sum(
            1 for keyword in _UNCERTAINTY_KEYWORDS if keyword in analysis.summary.lower()
        )
        score -= min(uncertainty_hits * 0.05, 0.2)
        if source_count == 0:
            score -= 0.15
        return max(0.0, min(1.0, score))

    @staticmethod
    def _compute_risk_opportunity_scores(analysis: AnalysisResponse) -> tuple[float, float]:
        text_pool = " ".join(
            [analysis.summary, *analysis.findings, *analysis.recommendations]
        ).lower()
        words = set(re.findall(r"[a-z]+", text_pool))
        risk_hits = len(words & _RISK_KEYWORDS)
        risk_hits += sum(
            1 for keyword in _RISK_KEYWORDS if len(keyword) > 2 and keyword in text_pool
        )
        opportunity_hits = len(words & _OPPORTUNITY_KEYWORDS)
        opportunity_hits += sum(
            1 for keyword in _OPPORTUNITY_KEYWORDS if len(keyword) > 2 and keyword in text_pool
        )
        risk_hits = min(risk_hits, len(_RISK_KEYWORDS))
        opportunity_hits = min(opportunity_hits, len(_OPPORTUNITY_KEYWORDS))
        if not words and risk_hits == 0 and opportunity_hits == 0:
            return 0.0, 0.0
        return min(risk_hits / 4.0, 1.0), min(opportunity_hits / 4.0, 1.0)

    @staticmethod
    def _detect_per_finding_conflicts(analysis: AnalysisResponse) -> list[str]:
        return [
            finding
            for finding in analysis.findings
            if any(keyword in finding.lower() for keyword in _RISK_KEYWORDS)
            and any(keyword in finding.lower() for keyword in _OPPORTUNITY_KEYWORDS)
        ]

    @staticmethod
    def _detect_source_contradiction(analysis: AnalysisResponse) -> bool:
        if not analysis.sources:
            return False
        source_types = {source.source_type for source in analysis.sources}
        source_risk_count = sum(
            any(keyword in source.summary.lower() for keyword in _RISK_KEYWORDS)
            for source in analysis.sources
        )
        source_opportunity_count = sum(
            any(keyword in source.summary.lower() for keyword in _OPPORTUNITY_KEYWORDS)
            for source in analysis.sources
        )
        has_mixed_signals = source_risk_count > 0 and source_opportunity_count > 0
        if len(source_types) >= _SOURCE_TYPE_DIVERSITY_THRESHOLD and has_mixed_signals:
            return True
        return source_risk_count >= 2 and source_opportunity_count >= 2

    @staticmethod
    def _compute_uncertainty_density(analysis: AnalysisResponse) -> float:
        summary = analysis.summary.lower()
        if not summary:
            return 0.0
        words = set(re.findall(r"[a-z]+", summary))
        uncertainty_hits = len(words & _UNCERTAINTY_KEYWORDS)
        uncertainty_hits += sum(
            1 for keyword in _UNCERTAINTY_KEYWORDS if len(keyword) > 2 and keyword in summary
        )
        total_words = len(words) + len(re.findall(r"[\u4e00-\u9fff]+", summary))
        if total_words == 0:
            return 0.0
        return min(uncertainty_hits / max(total_words * 0.1, 1.0), 1.0)
