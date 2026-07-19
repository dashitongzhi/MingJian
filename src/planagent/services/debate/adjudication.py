from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from planagent.domain.api import DebateTriggerRequest

from .branch_assessment import BranchDebateAssessmentStrategy
from .claim_assessment import ClaimDebateAssessmentStrategy
from .contracts import DebateAssessment
from .quality import DebateQualityMixin
from .run_assessment import RunDebateAssessmentStrategy


class DebateAdjudicationMixin(
    BranchDebateAssessmentStrategy,
    ClaimDebateAssessmentStrategy,
    RunDebateAssessmentStrategy,
    DebateQualityMixin,
):
    def _generate_adjudication(
        self,
        support_confidence: float,
        challenge_confidence: float,
        arbitrator_rounds: list[dict[str, Any]],
    ) -> str:
        if arbitrator_rounds:
            arb_position = arbitrator_rounds[-1].get("position", "CONDITIONAL")
            return {"SUPPORT": "ACCEPTED", "OPPOSE": "REJECTED"}.get(arb_position, "CONDITIONAL")
        if support_confidence >= challenge_confidence + 0.1 and support_confidence >= 0.65:
            return "ACCEPTED"
        if challenge_confidence >= support_confidence + 0.1 and challenge_confidence >= 0.65:
            return "REJECTED"
        return "CONDITIONAL"

    def _build_assessment_from_llm_rounds(
        self,
        rounds: list[dict[str, Any]],
        evidence_ids: list[str],
        payload: DebateTriggerRequest,
        *,
        run_id: str | None = None,
        claim_id: str | None = None,
        report_id: str | None = None,
        latest_decision_id: str | None = None,
        final_state: dict[str, float] | None = None,
        evidence_statements: list[str] | None = None,
        claim_statement: str | None = None,
        claim_confidence: float | None = None,
    ) -> DebateAssessment:
        advocate_rounds = [
            r
            for r in rounds
            if r["role"]
            in {
                "advocate",
                "strategist",
                "geo_expert",
                "econ_analyst",
                "military_strategist",
                "tech_foresight",
                "social_impact",
            }
        ]
        challenger_rounds = [
            r for r in rounds if r["role"] in {"challenger", "risk_analyst", "intel_analyst"}
        ]
        arbitrator_rounds = [r for r in rounds if r["role"] in {"arbitrator", "opportunist"}]

        support_confidence = max(
            (r["confidence"] for r in advocate_rounds),
            default=0.5,
        )
        challenge_confidence = max(
            (r["confidence"] for r in challenger_rounds),
            default=0.5,
        )

        if arbitrator_rounds:
            arb = arbitrator_rounds[-1]
            arb_position = arb.get("position", "CONDITIONAL")
            verdict = {"SUPPORT": "ACCEPTED", "OPPOSE": "REJECTED"}.get(arb_position, "CONDITIONAL")
        elif support_confidence >= challenge_confidence + 0.1 and support_confidence >= 0.65:
            verdict = "ACCEPTED"
        elif challenge_confidence >= support_confidence + 0.1 and challenge_confidence >= 0.65:
            verdict = "REJECTED"
        else:
            verdict = "CONDITIONAL"

        winning_arguments: list[str] = []
        for r in advocate_rounds:
            winning_arguments.extend(a.get("claim", "") for a in r.get("arguments", []))
        winning_arguments = winning_arguments[:3] or ["LLM advocate provided supporting reasoning."]

        minority_opinion: str | None = None
        for r in challenger_rounds:
            if r.get("arguments"):
                minority_opinion = r["arguments"][-1].get("claim", None)
                break

        conditions = None
        if verdict == "CONDITIONAL":
            if arbitrator_rounds:
                arb_concessions = arbitrator_rounds[-1].get("concessions", [])
                conditions = [
                    c.get("reason", "Condition attached by arbitrator.") for c in arb_concessions
                ] or ["The LLM arbitrator issued a conditional verdict."]
            else:
                conditions = [
                    "Retain the current conclusion, but keep analyst review attached to the next report cycle."
                ]

        context_payload: dict[str, Any] = {
            "debate_method": "llm",
            "user_context": payload.context_lines,
        }
        if run_id is not None:
            context_payload.update(
                {
                    "run_id": run_id,
                    "report_id": report_id,
                    "latest_decision_id": latest_decision_id,
                    "final_state": final_state or {},
                    "evidence_statements": evidence_statements or [],
                }
            )
        if claim_id is not None:
            context_payload.update(
                {
                    "claim_statement": claim_statement,
                    "claim_confidence": claim_confidence,
                }
            )

        # Generate planning recommendations from debate outcomes
        recommendations = self._generate_recommendations(
            verdict=verdict,
            winning_arguments=winning_arguments,
            minority_opinion=minority_opinion,
            conditions=conditions,
            support_confidence=support_confidence,
            challenge_confidence=challenge_confidence,
        )
        risk_factors = self._generate_risk_factors(
            challenger_rounds=challenger_rounds,
            verdict=verdict,
            minority_opinion=minority_opinion,
        )
        alternative_scenarios = self._generate_alternative_scenarios(
            advocate_rounds=advocate_rounds,
            challenger_rounds=challenger_rounds,
            verdict=verdict,
        )
        conclusion_summary = self._generate_conclusion_summary(
            verdict=verdict,
            support_confidence=support_confidence,
            challenge_confidence=challenge_confidence,
            recommendations=recommendations,
        )

        return DebateAssessment(
            support_confidence=support_confidence,
            challenge_confidence=challenge_confidence,
            verdict=verdict,
            winning_arguments=winning_arguments,
            decisive_evidence=evidence_ids[:5],
            conditions=conditions,
            minority_opinion=minority_opinion,
            context_payload=context_payload,
            rounds=rounds,
            recommendations=recommendations,
            risk_factors=risk_factors,
            alternative_scenarios=alternative_scenarios,
            conclusion_summary=conclusion_summary,
        )

    async def _assess_debate(
        self,
        session: AsyncSession,
        payload: DebateTriggerRequest,
    ) -> DebateAssessment:
        if payload.claim_id is not None:
            return await self._assess_claim_debate(session, payload)
        if payload.target_type == "branch":
            return await self._assess_branch_debate(session, payload)
        assert payload.run_id is not None
        return await self._assess_run_debate(session, payload)

    def _generate_recommendations(
        self,
        verdict: str,
        winning_arguments: list[str],
        minority_opinion: str | None,
        conditions: list[str] | None,
        support_confidence: float,
        challenge_confidence: float,
    ) -> list[dict[str, Any]]:
        """Generate actionable planning recommendations from debate outcomes."""
        recommendations: list[dict[str, Any]] = []

        if verdict == "ACCEPTED":
            recommendations.append(
                {
                    "title": "Proceed with current strategy",
                    "priority": "high",
                    "rationale": f"Strong support confidence ({support_confidence:.0%}) indicates favorable conditions.",
                    "action_items": [arg for arg in winning_arguments[:2]],
                }
            )
            if minority_opinion:
                recommendations.append(
                    {
                        "title": "Monitor identified risks",
                        "priority": "medium",
                        "rationale": f"While accepted, the risk analyst noted: {minority_opinion[:200]}",
                        "action_items": [
                            "Set up monitoring for risk factors",
                            "Schedule periodic reassessment",
                        ],
                    }
                )
        elif verdict == "REJECTED":
            recommendations.append(
                {
                    "title": "Revise strategy before proceeding",
                    "priority": "high",
                    "rationale": f"Challenge confidence ({challenge_confidence:.0%}) indicates significant concerns.",
                    "action_items": [arg for arg in winning_arguments[:2]],
                }
            )
            recommendations.append(
                {
                    "title": "Explore alternative approaches",
                    "priority": "high",
                    "rationale": "Current approach carries too much risk. Consider pivoting strategy.",
                    "action_items": [
                        "Conduct scenario analysis for alternatives",
                        "Gather additional evidence",
                    ],
                }
            )
        else:
            recommendations.append(
                {
                    "title": "Proceed with conditions",
                    "priority": "medium",
                    "rationale": "Mixed signals suggest proceeding cautiously with monitoring.",
                    "action_items": (conditions or ["Continue monitoring key indicators"])[:2],
                }
            )

        if conditions:
            recommendations.append(
                {
                    "title": "Address conditional requirements",
                    "priority": "medium",
                    "rationale": "Conditions must be met before full commitment.",
                    "action_items": conditions[:3],
                }
            )

        return recommendations

    def _generate_risk_factors(
        self,
        challenger_rounds: list[dict[str, Any]],
        verdict: str,
        minority_opinion: str | None,
    ) -> list[str]:
        """Extract risk factors from challenger arguments."""
        risks: list[str] = []
        for r in challenger_rounds:
            for arg in r.get("arguments", []):
                claim = arg.get("claim", "")
                if claim and claim not in risks:
                    risks.append(claim)
        if minority_opinion and minority_opinion not in risks:
            risks.append(minority_opinion)
        if verdict == "REJECTED":
            risks.insert(
                0, "Current strategy was rejected — high risk of failure if pursued unchanged."
            )
        return risks[:5]

    def _generate_alternative_scenarios(
        self,
        advocate_rounds: list[dict[str, Any]],
        challenger_rounds: list[dict[str, Any]],
        verdict: str,
    ) -> list[dict[str, Any]]:
        """Generate alternative scenario suggestions."""
        scenarios: list[dict[str, Any]] = []
        if verdict == "REJECTED":
            scenarios.append(
                {
                    "name": "Pivot Strategy",
                    "description": "Abandon current approach and adopt the challenger's recommended path.",
                    "expected_outcome": "Reduced risk exposure, potentially slower progress.",
                }
            )
        elif verdict == "CONDITIONAL":
            scenarios.append(
                {
                    "name": "Incremental Approach",
                    "description": "Implement recommendations in phases with checkpoints.",
                    "expected_outcome": "Balanced risk-reward with built-in course correction.",
                }
            )
        else:
            scenarios.append(
                {
                    "name": "Accelerated Execution",
                    "description": "Fast-track implementation given strong support signals.",
                    "expected_outcome": "Faster results but requires active monitoring for emergent risks.",
                }
            )
        return scenarios

    def _generate_conclusion_summary(
        self,
        verdict: str,
        support_confidence: float,
        challenge_confidence: float,
        recommendations: list[dict[str, Any]],
    ) -> str:
        """Generate a concise conclusion summary."""
        top_recs = [r["title"] for r in recommendations[:2]]
        rec_text = "; ".join(top_recs) if top_recs else "continue monitoring"
        return (
            f"Assessment result: {verdict}. "
            f"Support confidence: {support_confidence:.0%}, Challenge confidence: {challenge_confidence:.0%}. "
            f"Key recommendations: {rec_text}."
        )

    def _verdict_position(self, verdict: str) -> str:
        if verdict == "ACCEPTED":
            return "SUPPORT"
        if verdict == "REJECTED":
            return "OPPOSE"
        return "CONDITIONAL"
