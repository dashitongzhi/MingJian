from datetime import datetime, timezone

from planagent.domain.api import AnalysisResponse, AnalysisSourceRead
from planagent.services.assistant_conflicts import AssistantConflictDetector


def _analysis(
    *,
    summary: str,
    findings: list[str] | None = None,
    recommendations: list[str] | None = None,
    sources: list[AnalysisSourceRead] | None = None,
) -> AnalysisResponse:
    return AnalysisResponse(
        query="Should we change strategy?",
        domain_id="corporate",
        status="completed",
        summary=summary,
        findings=findings or [],
        recommendations=recommendations or [],
        sources=sources or [],
        generated_at=datetime.now(timezone.utc),
    )


def test_detect_returns_default_topic_when_evidence_is_stable() -> None:
    analysis = _analysis(
        summary="Evidence remains consistent across the current operating review. " * 5,
        findings=["Execution remains aligned with the approved plan."] * 4,
        recommendations=["Continue the current measured rollout."] * 3,
        sources=[
            AnalysisSourceRead(
                source_type="report",
                title="Quarterly review",
                url="https://example.com/review",
                summary="Execution remains aligned with plan.",
            )
        ],
    )

    result = AssistantConflictDetector().detect(analysis, "corporate", "Acme")

    assert result.warranted is False
    assert result.suggested_topic == "Should Acme change its current business posture?"
    assert result.conflicting_signals == []


def test_detect_concentrates_cross_source_and_finding_tension() -> None:
    analysis = _analysis(
        summary="The launch creates growth opportunity, however security risk remains uncertain.",
        findings=["Rapid growth improves reach but increases outage risk."],
        recommendations=["Expand carefully while reducing security risk."],
        sources=[
            AnalysisSourceRead(
                source_type=source_type,
                title=f"{source_type} update",
                url=f"https://example.com/{source_type}",
                summary=summary,
            )
            for source_type, summary in (
                ("news", "Demand growth creates a strong opportunity."),
                ("report", "Security risk may disrupt the launch."),
                ("social", "Users report both growth and outage risk."),
            )
        ],
    )

    result = AssistantConflictDetector().detect(analysis, "corporate", "Acme")

    assert result.warranted is True
    assert "risk_opportunity_tension" in result.conflicting_signals
    assert "finding_level_conflict" in result.conflicting_signals
    assert "source_contradiction" in result.conflicting_signals
    assert result.risk_score > 0
    assert result.opportunity_score > 0
