from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from planagent.domain.api import DebateTriggerRequest
from planagent.domain.enums import ClaimStatus
from planagent.domain.models import (
    Claim,
    CompanyProfile,
    DebateReliabilityScore,
    DebateStructuredDissent,
    DecisionRecordRecord,
    EvidenceItem,
    ExternalShockRecord,
    ForceProfile,
    GeneratedReport,
    ScenarioBranchRecord,
    SimulationRun,
)
from planagent.services.pipeline import normalize_text

from .contracts import ClaimRelationContext, DebateAssessment
from .engines import HeuristicDebateAdapter
from .roles import debate_role_label

_HEURISTIC_DEBATE_ADAPTER = HeuristicDebateAdapter()

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_CLAIM_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "this",
    "that",
    "from",
    "after",
    "before",
    "into",
    "across",
    "over",
    "under",
    "still",
    "remain",
    "remained",
    "during",
    "through",
    "their",
    "there",
    "about",
}
_POSITIVE_CLAIM_KEYWORDS = {
    "increase",
    "increased",
    "improve",
    "improved",
    "grow",
    "grew",
    "growing",
    "gain",
    "gained",
    "ship",
    "shipped",
    "launch",
    "launched",
    "deploy",
    "deployed",
    "restore",
    "restored",
    "rise",
    "rose",
    "support",
    "supported",
    "open",
    "opened",
}
_NEGATIVE_CLAIM_KEYWORDS = {
    "decrease",
    "decreased",
    "decline",
    "declined",
    "drop",
    "dropped",
    "fall",
    "fell",
    "delay",
    "delayed",
    "cancel",
    "canceled",
    "block",
    "blocked",
    "disrupt",
    "disrupted",
    "reduce",
    "reduced",
    "damage",
    "damaged",
    "loss",
    "losses",
    "reject",
    "rejected",
    "withdraw",
    "withdrew",
}


_BIAS_PATTERNS: dict[str, list[str]] = {
    "confirmation_bias": [
        "confirms",
        "as expected",
        "proves",
        "clearly shows",
        "undeniable",
        "without doubt",
        "obvious that",
        "always leads to",
        "inevitably",
    ],
    "cherry_picking": [
        "for example",
        "one case where",
        "specific instance of",
        "in one study",
        "a single case",
        "ignore the rest",
        "only evidence that",
        "selectively citing",
        "hand-picked",
    ],
    "hand_waving": [
        "roughly",
        "approximately",
        "about",
        "more or less",
        "in the ballpark",
        "general sense",
        "broadly speaking",
        "in theory",
        "should be fine",
    ],
    "excessive_pessimism": [
        "catastrophic",
        "disaster",
        "collapse",
        "unrecoverable",
        "fatal",
        "doomed",
        "point of no return",
        "irreversible damage",
        "total failure",
    ],
}

_RISK_DIMENSIONS = {
    "financial": {
        "budget",
        "cost",
        "revenue",
        "margin",
        "runway",
        "cash",
        "funding",
        "profit",
        "loss",
        "spend",
        "expense",
    },
    "operational": {
        "delivery",
        "velocity",
        "pipeline",
        "throughput",
        "capacity",
        "load",
        "efficiency",
        "bottleneck",
        "latency",
    },
    "strategic": {
        "market",
        "share",
        "competition",
        "positioning",
        "growth",
        "expansion",
        "pivot",
        "acquisition",
    },
    "technical": {
        "reliability",
        "debt",
        "infrastructure",
        "architecture",
        "scalability",
        "security",
        "vulnerability",
        "outage",
    },
    "human_capital": {
        "retention",
        "churn",
        "attrition",
        "hiring",
        "morale",
        "burnout",
        "talent",
        "skill",
    },
    "geopolitical": {
        "sanctions",
        "alliance",
        "treaty",
        "sovereignty",
        "territory",
        "escalation",
        "deterrence",
        "nuclear",
    },
    "logistics": {
        "supply",
        "logistics",
        "transport",
        "inventory",
        "stockpile",
        "distribution",
        "procurement",
    },
    "intelligence": {
        "isr",
        "surveillance",
        "reconnaissance",
        "intelligence",
        "sigint",
        "osint",
        "indicator",
    },
    "civilian_impact": {
        "civilian",
        "humanitarian",
        "refugee",
        "collateral",
        "population",
        "displacement",
    },
    "environmental": {
        "climate",
        "environment",
        "pollution",
        "sustainability",
        "carbon",
        "emission",
    },
}


class DebateAdjudicationMixin:
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

    async def _assess_branch_debate(
        self,
        session: AsyncSession,
        payload: DebateTriggerRequest,
    ) -> DebateAssessment:
        assert payload.target_id is not None
        branch = await session.get(ScenarioBranchRecord, payload.target_id)
        if branch is None:
            raise LookupError(f"Scenario branch {payload.target_id} was not found.")

        branch_run = await session.get(SimulationRun, branch.run_id)
        if branch_run is None:
            raise LookupError(f"Simulation run {branch.run_id} was not found.")
        baseline_run = await session.get(SimulationRun, branch.parent_run_id)
        if baseline_run is None:
            raise LookupError(f"Baseline simulation run {branch.parent_run_id} was not found.")

        branch_report = (
            await session.scalars(
                select(GeneratedReport)
                .where(GeneratedReport.scenario_id == branch.id)
                .order_by(GeneratedReport.created_at.desc())
                .limit(1)
            )
        ).first()
        baseline_report = (
            await session.scalars(
                select(GeneratedReport)
                .where(GeneratedReport.run_id == baseline_run.id)
                .order_by(GeneratedReport.created_at.desc())
                .limit(1)
            )
        ).first()

        branch_final_state = {
            key: float(value) for key, value in branch_run.summary.get("final_state", {}).items()
        }
        baseline_final_state = {
            key: float(value) for key, value in baseline_run.summary.get("final_state", {}).items()
        }
        evidence_ids = [str(value) for value in branch_run.summary.get("evidence_ids", [])]

        positives: list[str] = []
        risks: list[str] = []
        net_branch_score = 0.0
        for item in branch.kpi_trajectory:
            metric = str(item.get("metric"))
            baseline_end = float(item.get("baseline_end", 0.0))
            scenario_end = float(item.get("scenario_end", 0.0))
            metric_score = self._branch_metric_score(
                branch_run.domain_id, metric, baseline_end, scenario_end
            )
            net_branch_score += metric_score
            if metric_score > 0.08:
                positives.append(
                    self._branch_metric_summary(metric, baseline_end, scenario_end, better=True)
                )
            elif metric_score < -0.08:
                risks.append(
                    self._branch_metric_summary(metric, baseline_end, scenario_end, better=False)
                )

        positives.extend(str(item) for item in branch.decision_deltas[:2])
        recommendations = (
            branch_report.sections.get("strategy_recommendations", [])
            if branch_report is not None
            else []
        )
        risks.extend(str(item) for item in recommendations[:1] if str(item) not in risks)

        support_confidence = self._clamp(
            0.5 + (0.12 * len(positives)) + max(net_branch_score, 0.0) * 0.08 - (0.05 * len(risks)),
            minimum=0.2,
            maximum=0.94,
        )
        challenge_confidence = self._clamp(
            0.44
            + (0.12 * len(risks))
            + max(-net_branch_score, 0.0) * 0.08
            - (0.04 * len(positives)),
            minimum=0.15,
            maximum=0.9,
        )

        if support_confidence >= challenge_confidence + 0.1 and support_confidence >= 0.65:
            verdict = "ACCEPTED"
            conditions = None
        elif challenge_confidence >= support_confidence + 0.1 and challenge_confidence >= 0.65:
            verdict = "REJECTED"
            conditions = None
        else:
            verdict = "CONDITIONAL"
            conditions = [
                "Keep the branch visible in compare view until the next evidence refresh resolves the tradeoffs."
            ]

        winning_arguments = (
            positives or ["The branch presents a plausible alternative action path."]
        )[:3]
        minority_opinion = (
            risks or ["The branch does not clearly dominate the baseline outcome."]
        )[0]
        subject_name = await self._run_subject_name(session, branch_run)

        branch_risk_claim = (
            risks or ["The branch does not yet beat baseline on the highest-value metrics."]
        )[0]
        rounds = _HEURISTIC_DEBATE_ADAPTER.build_full_panel(
            subject_name=subject_name,
            support_confidence=support_confidence,
            challenge_confidence=challenge_confidence,
            verdict=verdict,
            decisive_evidence=evidence_ids[:3],
            winning_arguments=winning_arguments,
            minority_opinion=minority_opinion,
            conditions=conditions,
            focus="the scenario branch",
            role_claims={
                "advocate": (
                    winning_arguments[0],
                    f"The branch for {subject_name} improves part of the scenario surface versus baseline.",
                ),
                "challenger": (
                    branch_risk_claim,
                    "The alternative branch still carries meaningful tradeoffs against the baseline.",
                ),
                "econ_analyst": (
                    positives[0] if positives else winning_arguments[0],
                    "The economic view compares KPI deltas, opportunity cost, and resource tradeoffs.",
                ),
                "military_strategist": (
                    positives[1] if len(positives) > 1 else winning_arguments[0],
                    "The military view compares readiness, tempo, and operational feasibility versus baseline.",
                ),
                "social_impact": (
                    branch_risk_claim,
                    "The social view inspects collateral, legitimacy, and stakeholder effects in the branch path.",
                ),
            },
            custom_agents=self._get_custom_agents(),
        )

        # Generate planning recommendations
        branch_recommendations = self._generate_recommendations(
            verdict=verdict,
            winning_arguments=winning_arguments,
            minority_opinion=minority_opinion,
            conditions=conditions,
            support_confidence=support_confidence,
            challenge_confidence=challenge_confidence,
        )
        branch_risk_factors = self._generate_risk_factors(
            challenger_rounds=[
                r for r in rounds if r["role"] in {"risk_analyst", "challenger", "intel_analyst"}
            ],
            verdict=verdict,
            minority_opinion=minority_opinion,
        )
        branch_alternative_scenarios = self._generate_alternative_scenarios(
            advocate_rounds=[
                r
                for r in rounds
                if r["role"]
                in {
                    "strategist",
                    "advocate",
                    "geo_expert",
                    "econ_analyst",
                    "military_strategist",
                    "tech_foresight",
                    "social_impact",
                }
            ],
            challenger_rounds=[
                r for r in rounds if r["role"] in {"risk_analyst", "challenger", "intel_analyst"}
            ],
            verdict=verdict,
        )
        branch_conclusion = self._generate_conclusion_summary(
            verdict=verdict,
            support_confidence=support_confidence,
            challenge_confidence=challenge_confidence,
            recommendations=branch_recommendations,
        )

        return DebateAssessment(
            support_confidence=support_confidence,
            challenge_confidence=challenge_confidence,
            verdict=verdict,
            winning_arguments=winning_arguments,
            decisive_evidence=evidence_ids[:3],
            conditions=conditions,
            minority_opinion=minority_opinion,
            context_payload={
                "branch_id": branch.id,
                "branch_run_id": branch.run_id,
                "baseline_run_id": baseline_run.id,
                "domain_id": branch_run.domain_id,
                "kpi_trajectory": branch.kpi_trajectory,
                "decision_deltas": branch.decision_deltas,
                "branch_report_id": branch_report.id if branch_report is not None else None,
                "baseline_report_id": baseline_report.id if baseline_report is not None else None,
                "baseline_final_state": baseline_final_state,
                "branch_final_state": branch_final_state,
                "user_context": payload.context_lines,
            },
            rounds=rounds,
            recommendations=branch_recommendations,
            risk_factors=branch_risk_factors,
            alternative_scenarios=branch_alternative_scenarios,
            conclusion_summary=branch_conclusion,
        )

    def _branch_metric_score(
        self,
        domain_id: str,
        metric: str,
        baseline_end: float,
        scenario_end: float,
    ) -> float:
        if domain_id == "corporate":
            preferred = {
                "runway_weeks": "increase",
                "delivery_velocity": "increase",
                "pipeline": "increase",
                "support_load": "decrease",
                "reliability_debt": "decrease",
                "gross_margin": "increase",
                "nrr": "increase",
                "churn_risk": "decrease",
                "market_share": "increase",
            }
        else:
            preferred = {
                "readiness": "increase",
                "logistics_throughput": "increase",
                "supply_network": "increase",
                "objective_control": "increase",
                "recovery_capacity": "increase",
                "attrition_rate": "decrease",
                "enemy_readiness": "decrease",
                "enemy_pressure": "decrease",
                "isr_coverage": "increase",
                "air_defense": "increase",
                "civilian_risk": "decrease",
                "escalation_index": "decrease",
            }
        direction = preferred.get(metric, "increase")
        delta = scenario_end - baseline_end
        if direction == "decrease":
            delta = baseline_end - scenario_end
        span = max(abs(baseline_end) * 0.2, 0.05)
        return delta / span

    def _branch_metric_summary(
        self,
        metric: str,
        baseline_end: float,
        scenario_end: float,
        *,
        better: bool,
    ) -> str:
        direction = "improved" if better else "degraded"
        return (
            f"{metric} {direction} from {baseline_end:.3f} to {scenario_end:.3f} "
            f"against the baseline."
        )

    async def _assess_claim_debate(
        self,
        session: AsyncSession,
        payload: DebateTriggerRequest,
    ) -> DebateAssessment:
        assert payload.claim_id is not None
        claim = await session.get(Claim, payload.claim_id)
        if claim is None:
            raise LookupError(f"Claim {payload.claim_id} was not found.")
        evidence = await session.get(EvidenceItem, claim.evidence_item_id)
        relations = await self.find_claim_relations(session, claim)

        # Try LLM-powered debate first
        decisive_evidence_pre = list(
            dict.fromkeys(
                [
                    claim.evidence_item_id,
                    *[item.evidence_item_id for item in relations.supportive_claims[:2]],
                    *[item.evidence_item_id for item in relations.conflicting_claims[:2]],
                ]
            )
        )
        context_parts = [
            f"Claim: {claim.statement}",
            f"Claim confidence: {claim.confidence}",
            f"Evidence title: {evidence.title if evidence is not None else 'unknown'}",
            f"Supporting claims: {len(relations.supportive_claims)}",
            f"Conflicting claims: {len(relations.conflicting_claims)}",
        ]
        if payload.context_lines:
            context_parts.append("Trigger context:\n" + "\n".join(payload.context_lines))
        if relations.supportive_claims:
            context_parts.append(
                f"Strongest support: {relations.supportive_claims[0].statement[:200]}"
            )
        if relations.conflicting_claims:
            context_parts.append(
                f"Strongest conflict: {relations.conflicting_claims[0].statement[:200]}"
            )
        llm_context = "\n".join(context_parts)
        llm_rounds = await self._llm_debate_rounds(
            topic=payload.topic,
            trigger_type=payload.trigger_type,
            context=llm_context,
            evidence_ids=decisive_evidence_pre,
            debate_mode=payload.debate_mode,
            domain_id=payload.domain_id,
        )
        if llm_rounds is not None:
            return self._build_assessment_from_llm_rounds(
                llm_rounds,
                decisive_evidence_pre,
                payload,
                claim_id=claim.id,
                claim_statement=claim.statement,
                claim_confidence=float(claim.confidence),
            )

        # Fallback: heuristic debate
        strongest_support = relations.supportive_claims[0] if relations.supportive_claims else None
        strongest_conflict = (
            relations.conflicting_claims[0] if relations.conflicting_claims else None
        )
        support_confidence = self._clamp(
            float(claim.confidence)
            + (0.12 * len(relations.supportive_claims))
            + ((strongest_support.confidence * 0.18) if strongest_support is not None else 0.0)
            - ((strongest_conflict.confidence * 0.20) if strongest_conflict is not None else 0.0),
            minimum=0.2,
            maximum=0.95,
        )
        challenge_confidence = self._clamp(
            max(0.2, 1.0 - float(claim.confidence))
            + (0.12 * len(relations.conflicting_claims))
            + ((strongest_conflict.confidence * 0.20) if strongest_conflict is not None else 0.0)
            - ((strongest_support.confidence * 0.12) if strongest_support is not None else 0.0),
            minimum=0.15,
            maximum=0.95,
        )
        if (
            strongest_conflict is not None
            and strongest_conflict.status == ClaimStatus.ACCEPTED.value
            and strongest_conflict.confidence >= claim.confidence + 0.08
            and challenge_confidence >= support_confidence
        ):
            verdict = "REJECTED"
        elif (
            strongest_support is not None
            and strongest_support.status == ClaimStatus.ACCEPTED.value
            and strongest_support.confidence >= claim.confidence
            and support_confidence >= challenge_confidence + 0.05
        ):
            verdict = "ACCEPTED"
        elif support_confidence >= 0.7 and support_confidence >= challenge_confidence + 0.08:
            verdict = "ACCEPTED"
        elif challenge_confidence >= 0.7 and challenge_confidence >= support_confidence + 0.08:
            verdict = "REJECTED"
        else:
            verdict = "CONDITIONAL"
        decisive_evidence = [
            claim.evidence_item_id,
            *[item.evidence_item_id for item in relations.supportive_claims[:2]],
            *[item.evidence_item_id for item in relations.conflicting_claims[:2]],
        ]
        decisive_evidence = list(dict.fromkeys(decisive_evidence))
        winning_arguments = [
            f"Claim confidence moved to {support_confidence:.2f} after weighing related evidence.",
            (
                f"Found {len(relations.supportive_claims)} corroborating claims and "
                f"{len(relations.conflicting_claims)} conflicting claims."
            ),
        ]
        conditions = (
            ["Escalate to analyst review before admitting the claim into the simulation chain."]
            if verdict == "CONDITIONAL"
            else None
        )
        minority_opinion = (
            "The challenger argued that the conflict set still leaves too much ambiguity for automatic promotion."
            if verdict != "REJECTED"
            else "The advocate argued the statement still deserves retention for audit and search."
        )
        support_block = self._claim_argument_block(
            primary_claim=claim,
            related_claims=relations.supportive_claims,
            default_reasoning="The statement is directly grounded in the linked evidence item.",
            confidence=support_confidence,
        )[0]
        challenge_block = self._claim_argument_block(
            primary_claim=claim,
            related_claims=relations.conflicting_claims,
            default_reasoning="The confidence band alone does not establish that this claim wins against the conflict set.",
            confidence=challenge_confidence,
            opposing=True,
        )[0]
        rounds = _HEURISTIC_DEBATE_ADAPTER.build_full_panel(
            subject_name=claim.subject,
            support_confidence=support_confidence,
            challenge_confidence=challenge_confidence,
            verdict=verdict,
            decisive_evidence=decisive_evidence,
            winning_arguments=winning_arguments,
            minority_opinion=minority_opinion,
            conditions=conditions,
            focus="the evidence claim",
            role_claims={
                "advocate": (
                    str(support_block.get("claim", claim.statement)),
                    str(support_block.get("reasoning", "")),
                ),
                "challenger": (
                    str(
                        challenge_block.get("claim", "The current claim still faces conflict risk.")
                    ),
                    str(challenge_block.get("reasoning", "")),
                ),
                "intel_analyst": (
                    f"Evidence title: {evidence.title if evidence is not None else 'unknown'}.",
                    "The evidence assessor checks the source trail, related claims, and conflict set before promotion.",
                ),
                "econ_analyst": (
                    winning_arguments[0],
                    "The economic view treats this claim as an input whose downstream cost depends on confidence quality.",
                ),
                "social_impact": (
                    str(
                        challenge_block.get(
                            "claim", "The claim needs human review before downstream adoption."
                        )
                    ),
                    "The social view considers reputational and decision-quality impact if an uncertain claim is promoted.",
                ),
            },
            custom_agents=self._get_custom_agents(),
        )

        # Generate planning recommendations
        claim_recommendations = self._generate_recommendations(
            verdict=verdict,
            winning_arguments=winning_arguments,
            minority_opinion=minority_opinion,
            conditions=conditions,
            support_confidence=support_confidence,
            challenge_confidence=challenge_confidence,
        )
        claim_risk_factors = self._generate_risk_factors(
            challenger_rounds=[
                r for r in rounds if r["role"] in {"risk_analyst", "challenger", "intel_analyst"}
            ],
            verdict=verdict,
            minority_opinion=minority_opinion,
        )
        claim_alternative_scenarios = self._generate_alternative_scenarios(
            advocate_rounds=[
                r
                for r in rounds
                if r["role"]
                in {
                    "strategist",
                    "advocate",
                    "geo_expert",
                    "econ_analyst",
                    "military_strategist",
                    "tech_foresight",
                    "social_impact",
                }
            ],
            challenger_rounds=[
                r for r in rounds if r["role"] in {"risk_analyst", "challenger", "intel_analyst"}
            ],
            verdict=verdict,
        )
        claim_conclusion = self._generate_conclusion_summary(
            verdict=verdict,
            support_confidence=support_confidence,
            challenge_confidence=challenge_confidence,
            recommendations=claim_recommendations,
        )

        return DebateAssessment(
            support_confidence=support_confidence,
            challenge_confidence=challenge_confidence,
            verdict=verdict,
            winning_arguments=winning_arguments,
            decisive_evidence=decisive_evidence,
            conditions=conditions,
            minority_opinion=minority_opinion,
            context_payload={
                "claim_statement": claim.statement,
                "claim_confidence": claim.confidence,
                "evidence_id": claim.evidence_item_id,
                "supporting_claim_ids": [item.id for item in relations.supportive_claims],
                "conflicting_claim_ids": [item.id for item in relations.conflicting_claims],
                "user_context": payload.context_lines,
            },
            rounds=rounds,
            recommendations=claim_recommendations,
            risk_factors=claim_risk_factors,
            alternative_scenarios=claim_alternative_scenarios,
            conclusion_summary=claim_conclusion,
        )

    async def _assess_run_debate(
        self,
        session: AsyncSession,
        payload: DebateTriggerRequest,
    ) -> DebateAssessment:
        assert payload.run_id is not None
        run = await session.get(SimulationRun, payload.run_id)
        if run is None:
            raise LookupError(f"Simulation run {payload.run_id} was not found.")

        report = (
            await session.scalars(
                select(GeneratedReport)
                .where(GeneratedReport.run_id == run.id)
                .order_by(GeneratedReport.created_at.desc())
                .limit(1)
            )
        ).first()
        latest_decision = (
            await session.scalars(
                select(DecisionRecordRecord)
                .where(DecisionRecordRecord.run_id == run.id)
                .order_by(DecisionRecordRecord.tick.desc(), DecisionRecordRecord.sequence.desc())
                .limit(1)
            )
        ).first()
        shocks = list(
            (
                await session.scalars(
                    select(ExternalShockRecord)
                    .where(ExternalShockRecord.run_id == run.id)
                    .order_by(ExternalShockRecord.tick.asc())
                )
            ).all()
        )
        final_state = {
            key: float(value) for key, value in run.summary.get("final_state", {}).items()
        }
        evidence_ids = [str(value) for value in run.summary.get("evidence_ids", [])]
        evidence_statements = [str(value) for value in run.summary.get("evidence_statements", [])]
        matched_rules = [str(value) for value in run.summary.get("matched_rules", [])]
        subject_name = await self._run_subject_name(session, run)

        # Try LLM-powered debate first
        context_parts = [
            f"Domain: {run.domain_id}",
            f"Subject: {subject_name}",
            f"Final state: {final_state}",
            f"Matched rules: {matched_rules[:5]}",
            f"Shocks: {[s.shock_type for s in shocks[:5]]}",
        ] + [f"Evidence: {e}" for e in evidence_statements[:3]]
        if payload.context_lines:
            context_parts.append("Trigger context:\n" + "\n".join(payload.context_lines))
        if report is not None:
            context_parts.append(f"Report summary: {report.summary[:500]}")
        llm_context = "\n".join(context_parts)
        llm_rounds = await self._llm_debate_rounds(
            topic=payload.topic,
            trigger_type=payload.trigger_type,
            context=llm_context,
            evidence_ids=evidence_ids[:5],
            debate_mode=payload.debate_mode,
            domain_id=payload.domain_id or run.domain_id,
        )
        if llm_rounds is not None:
            return self._build_assessment_from_llm_rounds(
                llm_rounds,
                evidence_ids,
                payload,
                run_id=run.id,
                report_id=report.id if report is not None else None,
                latest_decision_id=latest_decision.id if latest_decision is not None else None,
                final_state=final_state,
                evidence_statements=evidence_statements[:3],
            )

        # Fallback: heuristic debate
        positives: list[str] = []
        risks: list[str] = []
        if run.domain_id == "corporate":
            if final_state.get("runway_weeks", 0.0) >= 40:
                positives.append("Runway remains above the stress threshold.")
            else:
                risks.append("Runway closed toward the stress threshold.")
            if final_state.get("pipeline", 0.0) >= 0.95:
                positives.append("Qualified pipeline stayed above the wedge threshold.")
            else:
                risks.append("Qualified pipeline weakened.")
            if final_state.get("market_share", 0.0) >= 0.06:
                positives.append("Market share improved over the run.")
            if final_state.get("infra_cost_index", 1.0) > 1.1:
                risks.append("Infrastructure cost remained elevated.")
            if final_state.get("delivery_velocity", 1.0) < 0.95:
                risks.append("Delivery velocity degraded.")
            if final_state.get("support_load", 0.0) > 0.55:
                risks.append("Support load remained above the operating comfort zone.")
            if final_state.get("reliability_debt", 0.0) <= 0.3:
                positives.append("Reliability debt stayed under control.")
            if final_state.get("nrr", 0.0) < 1.0 or final_state.get("churn_risk", 1.0) > 0.18:
                risks.append("Retention quality remained fragile.")
        else:
            if final_state.get("readiness", 0.0) >= 1.0:
                positives.append("Readiness held at or above baseline.")
            else:
                risks.append("Readiness ended below baseline.")
            if final_state.get("logistics_throughput", 0.0) >= 0.8:
                positives.append("Logistics throughput stayed above the danger zone.")
            else:
                risks.append("Logistics throughput stayed under the recovery threshold.")
            if final_state.get("civilian_risk", 0.0) > 0.55:
                risks.append("Civilian risk remained elevated.")
            if final_state.get("escalation_index", 0.0) > 0.75:
                risks.append("Escalation pressure remained high.")

        positives.extend(f"Rule matched: {rule_id}." for rule_id in matched_rules[:2])
        risks.extend(f"External shock persisted: {shock.shock_type}." for shock in shocks[:2])

        support_confidence = self._clamp(
            0.55 + 0.08 * len(positives) - 0.05 * len(risks),
            minimum=0.2,
            maximum=0.92,
        )
        challenge_confidence = self._clamp(
            0.45 + 0.08 * len(risks) - 0.04 * len(positives),
            minimum=0.15,
            maximum=0.9,
        )

        if support_confidence >= challenge_confidence + 0.1 and support_confidence >= 0.65:
            verdict = "ACCEPTED"
            conditions = None
        elif challenge_confidence >= support_confidence + 0.1 and challenge_confidence >= 0.65:
            verdict = "REJECTED"
            conditions = None
        else:
            verdict = "CONDITIONAL"
            conditions = [
                "Retain the current conclusion, but keep analyst review attached to the next report cycle."
            ]

        winning_arguments = (positives or ["The baseline decision sequence remained coherent."])[:3]
        decisive_evidence = evidence_ids[:3]
        minority_opinion = (risks or ["The challenger found limited contradictory evidence."])[0]

        subject_name = await self._run_subject_name(session, run)

        def make_round(
            round_number: int,
            role: str,
            position: str,
            confidence: float,
            claim: str,
            reasoning: str,
            *,
            strength: str = "MODERATE",
            rebuttals: list[dict[str, Any]] | None = None,
            concessions: list[dict[str, Any]] | None = None,
        ) -> dict[str, Any]:
            return {
                "round_number": round_number,
                "role": role,
                "position": position,
                "confidence": confidence,
                "arguments": [
                    {
                        "claim": claim,
                        "evidence_ids": decisive_evidence,
                        "reasoning": reasoning,
                        "strength": strength,
                    }
                ],
                "rebuttals": rebuttals or [],
                "concessions": concessions or [],
            }

        support_claim = winning_arguments[0]
        risk_claim = minority_opinion
        role_claims = {
            "advocate": (
                support_claim,
                f"The run for {subject_name} closed with supportive signals in the final state.",
            ),
            "intel_analyst": (
                evidence_statements[0]
                if evidence_statements
                else "The evidence set is sufficient for a provisional intelligence read.",
                "The evidence assessor cross-checks source statements and flags remaining information gaps.",
            ),
            "geo_expert": (
                positives[1] if len(positives) > 1 else support_claim,
                "The geopolitical view connects the run outcome to theater posture and alliance constraints.",
            ),
            "econ_analyst": (
                positives[2] if len(positives) > 2 else support_claim,
                "The economic view weighs resource cost, throughput, and opportunity cost in the final state.",
            ),
            "military_strategist": (
                positives[0] if positives else support_claim,
                "The military view evaluates readiness, logistics, and operational feasibility.",
            ),
            "tech_foresight": (
                matched_rules[0]
                if matched_rules
                else "Technical assumptions did not overturn the run path.",
                "The technical view checks whether infrastructure and capability assumptions remain plausible.",
            ),
            "social_impact": (
                risks[0] if risks else "Civilian and social impact remain within the review band.",
                "The social view keeps civilian, legitimacy, and public response constraints visible.",
            ),
        }
        rounds = [
            make_round(
                1,
                role,
                "SUPPORT" if role != "social_impact" else "CONDITIONAL",
                support_confidence
                if role != "social_impact"
                else (support_confidence + challenge_confidence) / 2,
                role_claims[role][0],
                role_claims[role][1],
                strength="STRONG" if role == "advocate" else "MODERATE",
            )
            for role in (
                "advocate",
                "intel_analyst",
                "geo_expert",
                "econ_analyst",
                "military_strategist",
                "tech_foresight",
                "social_impact",
            )
        ]
        rounds.extend(
            [
                make_round(
                    2,
                    "challenger",
                    "OPPOSE" if verdict == "REJECTED" else "CONDITIONAL",
                    challenge_confidence,
                    risk_claim,
                    "The challenger pressure-tests the full expert panel and keeps unresolved downside visible.",
                    strength="STRONG" if risks else "MODERATE",
                    rebuttals=[
                        {
                            "target_argument_idx": 0,
                            "counter": winning_arguments[0],
                            "evidence_ids": decisive_evidence,
                        }
                    ],
                ),
                make_round(
                    2,
                    "intel_analyst",
                    "CONDITIONAL",
                    self._clamp((support_confidence + challenge_confidence) / 2, 0.2, 0.9),
                    "Fact check: the cited evidence supports a provisional verdict but should stay attached to the next refresh.",
                    "The evidence assessor revisits the first-round claims and marks what needs source refresh.",
                    strength="MODERATE",
                ),
            ]
        )
        for role in (
            "advocate",
            "geo_expert",
            "econ_analyst",
            "military_strategist",
            "tech_foresight",
            "social_impact",
        ):
            label = debate_role_label(role)
            rounds.append(
                make_round(
                    3,
                    role,
                    "SUPPORT" if role != "social_impact" else "CONDITIONAL",
                    self._clamp(support_confidence - 0.03, 0.2, 0.92),
                    f"{label} revised view: the main conclusion remains supportable with explicit monitoring.",
                    f"{label} responds to challenger pressure by preserving the strongest evidence and narrowing weaker claims.",
                    rebuttals=[
                        {
                            "target_argument_idx": 0,
                            "counter": risk_claim,
                            "evidence_ids": decisive_evidence,
                        }
                    ],
                )
            )

        for custom_agent in self._get_custom_agents():
            role_key = str(custom_agent.get("role_key", "custom_agent"))
            name = str(custom_agent.get("name", role_key))
            description = str(custom_agent.get("description", ""))[:180]
            rounds.append(
                make_round(
                    1,
                    role_key,
                    "CONDITIONAL",
                    self._clamp((support_confidence + challenge_confidence) / 2, 0.2, 0.9),
                    f"{name} participated in the expert panel.",
                    description
                    or "The custom agent contributed a specialized perspective to the debate.",
                )
            )
            rounds.append(
                make_round(
                    3,
                    role_key,
                    "CONDITIONAL",
                    self._clamp((support_confidence + challenge_confidence) / 2 - 0.02, 0.2, 0.9),
                    f"{name} revised its view after challenger pressure.",
                    "The custom agent acknowledged the shared debate history and preserved its key monitoring point.",
                    rebuttals=[
                        {
                            "target_argument_idx": 0,
                            "counter": risk_claim,
                            "evidence_ids": decisive_evidence,
                        }
                    ],
                )
            )

        rounds.append(
            make_round(
                4,
                "arbitrator",
                self._verdict_position(verdict),
                max(support_confidence, challenge_confidence),
                f"Final verdict: {verdict}.",
                "The arbitrator weighted all nine built-in agent perspectives, custom agent inputs, final-state metrics, matched rules, and unresolved shocks.",
                strength="STRONG",
                concessions=([{"argument_idx": 0, "reason": conditions[0]}] if conditions else []),
            )
        )

        # Generate planning recommendations
        run_recommendations = self._generate_recommendations(
            verdict=verdict,
            winning_arguments=winning_arguments,
            minority_opinion=minority_opinion,
            conditions=conditions,
            support_confidence=support_confidence,
            challenge_confidence=challenge_confidence,
        )
        run_risk_factors = self._generate_risk_factors(
            challenger_rounds=[
                r for r in rounds if r["role"] in {"risk_analyst", "challenger", "intel_analyst"}
            ],
            verdict=verdict,
            minority_opinion=minority_opinion,
        )
        run_alternative_scenarios = self._generate_alternative_scenarios(
            advocate_rounds=[
                r
                for r in rounds
                if r["role"]
                in {
                    "strategist",
                    "advocate",
                    "geo_expert",
                    "econ_analyst",
                    "military_strategist",
                    "tech_foresight",
                    "social_impact",
                }
            ],
            challenger_rounds=[
                r for r in rounds if r["role"] in {"risk_analyst", "challenger", "intel_analyst"}
            ],
            verdict=verdict,
        )
        run_conclusion = self._generate_conclusion_summary(
            verdict=verdict,
            support_confidence=support_confidence,
            challenge_confidence=challenge_confidence,
            recommendations=run_recommendations,
        )

        return DebateAssessment(
            support_confidence=support_confidence,
            challenge_confidence=challenge_confidence,
            verdict=verdict,
            winning_arguments=winning_arguments,
            decisive_evidence=decisive_evidence,
            conditions=conditions,
            minority_opinion=minority_opinion,
            context_payload={
                "run_id": run.id,
                "domain_id": run.domain_id,
                "final_state": final_state,
                "report_id": report.id if report is not None else None,
                "latest_decision_id": latest_decision.id if latest_decision is not None else None,
                "evidence_statements": evidence_statements[:3],
                "user_context": payload.context_lines,
            },
            rounds=rounds,
            recommendations=run_recommendations,
            risk_factors=run_risk_factors,
            alternative_scenarios=run_alternative_scenarios,
            conclusion_summary=run_conclusion,
        )

    async def _run_subject_name(self, session: AsyncSession, run: SimulationRun) -> str:
        if run.company_id is not None:
            company = await session.get(CompanyProfile, run.company_id)
            if company is not None:
                return company.name
        if run.force_id is not None:
            force = await session.get(ForceProfile, run.force_id)
            if force is not None:
                return force.name
        return run.id

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

    async def find_claim_relations(
        self,
        session: AsyncSession,
        claim: Claim,
    ) -> ClaimRelationContext:
        base_tokens = self._claim_tokens(claim.statement)
        if not base_tokens:
            return ClaimRelationContext(supportive_claims=[], conflicting_claims=[])

        candidates = list(
            (
                await session.scalars(
                    select(Claim)
                    .where(
                        Claim.id != claim.id,
                        Claim.status.in_(
                            [ClaimStatus.ACCEPTED.value, ClaimStatus.PENDING_REVIEW.value]
                        ),
                    )
                    .order_by(Claim.updated_at.desc())
                    .limit(50)
                )
            ).all()
        )
        base_direction = self._claim_direction(claim.statement)
        supportive_claims: list[Claim] = []
        conflicting_claims: list[Claim] = []

        for candidate in candidates:
            if candidate.evidence_item_id == claim.evidence_item_id:
                continue
            similarity = self._claim_similarity(
                base_tokens, self._claim_tokens(candidate.statement)
            )
            similarity_threshold = (
                0.2
                if normalize_text(candidate.subject).lower()
                == normalize_text(claim.subject).lower()
                else 0.3
            )
            if similarity < similarity_threshold:
                continue
            candidate_direction = self._claim_direction(candidate.statement)
            if (
                base_direction != 0
                and candidate_direction != 0
                and base_direction != candidate_direction
            ):
                conflicting_claims.append(candidate)
            else:
                supportive_claims.append(candidate)

        supportive_claims.sort(
            key=lambda item: (
                item.status == ClaimStatus.ACCEPTED.value,
                float(item.confidence),
            ),
            reverse=True,
        )
        conflicting_claims.sort(
            key=lambda item: (
                item.status == ClaimStatus.ACCEPTED.value,
                float(item.confidence),
            ),
            reverse=True,
        )
        return ClaimRelationContext(
            supportive_claims=supportive_claims[:3],
            conflicting_claims=conflicting_claims[:3],
        )

    def _claim_argument_block(
        self,
        primary_claim: Claim,
        related_claims: list[Claim],
        default_reasoning: str,
        confidence: float,
        opposing: bool = False,
    ) -> list[dict[str, Any]]:
        if related_claims:
            lead = related_claims[0]
            return [
                {
                    "claim": lead.statement,
                    "evidence_ids": [primary_claim.evidence_item_id, lead.evidence_item_id],
                    "reasoning": (
                        "A related accepted claim points in the same direction."
                        if not opposing
                        else "A related claim points in the opposite direction with stronger support."
                    ),
                    "strength": "STRONG"
                    if lead.status == ClaimStatus.ACCEPTED.value
                    else "MODERATE",
                }
            ]
        return [
            {
                "claim": primary_claim.statement
                if not opposing
                else "The current claim still faces unresolved conflict risk.",
                "evidence_ids": [primary_claim.evidence_item_id],
                "reasoning": default_reasoning,
                "strength": "STRONG" if confidence >= 0.7 else "MODERATE",
            }
        ]

    def _claim_tokens(self, statement: str) -> set[str]:
        normalized = normalize_text(statement).lower()
        return {
            token
            for token in _TOKEN_RE.findall(normalized)
            if len(token) > 2 and token not in _CLAIM_STOPWORDS
        }

    def _claim_similarity(self, base_tokens: set[str], candidate_tokens: set[str]) -> float:
        if not base_tokens or not candidate_tokens:
            return 0.0
        overlap = len(base_tokens & candidate_tokens)
        union = len(base_tokens | candidate_tokens)
        if union == 0:
            return 0.0
        return overlap / union

    def _claim_direction(self, statement: str) -> int:
        normalized = normalize_text(statement).lower()
        tokens = set(_TOKEN_RE.findall(normalized))
        positive_hits = len(tokens & _POSITIVE_CLAIM_KEYWORDS)
        negative_hits = len(tokens & _NEGATIVE_CLAIM_KEYWORDS)
        if positive_hits > negative_hits:
            return 1
        if negative_hits > positive_hits:
            return -1
        return 0

    def _clamp(self, value: float, minimum: float, maximum: float) -> float:
        return max(minimum, min(maximum, value))

    # ── New: reliability scoring, bias/blind-spot detection, weighted consensus ──

    def _detect_biases(self, text: str) -> list[str]:
        """Detect bias patterns in argument text. Returns list of bias flag names."""
        lower = text.lower()
        flags: list[str] = []
        for bias_name, patterns in _BIAS_PATTERNS.items():
            if any(pattern in lower for pattern in patterns):
                flags.append(bias_name)
        return flags

    def _assess_evidence_strength(self, argument: dict[str, Any]) -> str:
        """Classify evidence strength based on argument metadata."""
        strength = argument.get("strength", "MODERATE").upper()
        evidence_ids = argument.get("evidence_ids", [])
        if strength == "STRONG" and len(evidence_ids) >= 2:
            return "strong"
        if strength in ("STRONG", "MODERATE") and evidence_ids:
            return "moderate"
        if evidence_ids:
            return "weak"
        return "speculative"

    def _compute_reliability_score(
        self, bias_flags: list[str], evidence_strength: str, reasoning: str
    ) -> int:
        """Compute reliability score 1-5 based on bias count and evidence quality."""
        base = 4
        evidence_map = {"strong": 1, "moderate": 0, "weak": -1, "speculative": -2}
        base += evidence_map.get(evidence_strength, 0)
        base -= len(bias_flags)
        # Penalize very short or empty reasoning
        if len(reasoning.strip()) < 20:
            base -= 1
        return max(1, min(5, base))

    async def score_argument_reliability(
        self,
        debate_id: str,
        round_records: list[dict[str, Any]],
        session: AsyncSession,
    ) -> list[DebateReliabilityScore]:
        """Score each argument for reliability, bias, and blind spots.

        Creates a DebateReliabilityScore for every argument in every round.
        Returns the list of persisted objects (already session.add'd).
        """
        scores: list[DebateReliabilityScore] = []
        for round_data in round_records:
            round_number = round_data.get("round_number", 1)
            role = round_data.get("role", "unknown")
            arguments = round_data.get("arguments", [])
            for idx, arg in enumerate(arguments):
                claim_text = arg.get("claim", "")
                reasoning = arg.get("reasoning", "")
                combined_text = f"{claim_text} {reasoning}"

                bias_flags = self._detect_biases(combined_text)
                evidence_strength = self._assess_evidence_strength(arg)
                rel_score = self._compute_reliability_score(
                    bias_flags, evidence_strength, reasoning
                )

                # Blind spots specific to this argument
                arg_blind_spots: list[str] = []
                arg_text_lower = combined_text.lower()
                covered_dims: set[str] = set()
                for dim, keywords in _RISK_DIMENSIONS.items():
                    if any(kw in arg_text_lower for kw in keywords):
                        covered_dims.add(dim)
                # Don't flag all missing dimensions—only flag if the argument
                # claims comprehensiveness but omits major areas
                if any(
                    phrase in arg_text_lower
                    for phrase in (
                        "all factors",
                        "comprehensive",
                        "holistic",
                        "all risks",
                        "all aspects",
                    )
                ):
                    for dim in _RISK_DIMENSIONS:
                        if dim not in covered_dims:
                            arg_blind_spots.append(f"claims_completeness_but_ignores_{dim}")

                # Determine auditor role (the "other side")
                auditor_role = (
                    "risk_analyst"
                    if role
                    in (
                        "strategist",
                        "advocate",
                        "geo_expert",
                        "econ_analyst",
                        "military_strategist",
                        "tech_foresight",
                        "social_impact",
                    )
                    else "strategist"
                )

                score_obj = DebateReliabilityScore(
                    debate_id=debate_id,
                    round_number=round_number,
                    role=role,
                    argument_index=idx,
                    argument_summary=claim_text[:500],
                    reliability_score=rel_score,
                    bias_flags=bias_flags,
                    blind_spots=arg_blind_spots,
                    evidence_strength=evidence_strength,
                    auditor_role=auditor_role,
                )
                session.add(score_obj)
                scores.append(score_obj)
        return scores

    def detect_blind_spots(self, round_records: list[dict[str, Any]]) -> list[str]:
        """Identify risk dimensions that no role covered in the debate.

        Aggregates all argument text across all rounds and checks which
        risk dimension keyword sets had zero hits.
        """
        all_text_parts: list[str] = []
        for round_data in round_records:
            for arg in round_data.get("arguments", []):
                all_text_parts.append(arg.get("claim", ""))
                all_text_parts.append(arg.get("reasoning", ""))
        combined = " ".join(all_text_parts).lower()
        tokens = set(_TOKEN_RE.findall(combined))

        blind_spots: list[str] = []
        for dimension, keywords in _RISK_DIMENSIONS.items():
            if not tokens & keywords:
                blind_spots.append(f"No argument addressed the '{dimension}' risk dimension.")
        return blind_spots

    def weighted_consensus(
        self,
        support_confidence: float,
        challenge_confidence: float,
        domain_weights: dict[str, float],
    ) -> tuple[str, float]:
        """Compute regime-weighted consensus verdict.

        Args:
            support_confidence: Raw confidence from advocate side.
            challenge_confidence: Raw confidence from challenger side.
            domain_weights: Mapping of role name → weight multiplier.
                Example: {"strategist": 1.2, "risk_analyst": 1.0, "opportunist": 0.8}

        Returns:
            Tuple of (verdict_string, weighted_confidence).
        """
        support_weight = domain_weights.get("strategist", 1.0)
        challenge_weight = domain_weights.get("risk_analyst", 1.0)
        arb_weight = domain_weights.get("opportunist", 0.5)

        weighted_support = support_confidence * support_weight
        weighted_challenge = challenge_confidence * challenge_weight

        # Blend toward arbitrator weight when it's meaningfully different
        if arb_weight != 1.0:
            midpoint = (weighted_support + weighted_challenge) / 2.0
            weighted_support = (
                weighted_support * (1.0 - arb_weight * 0.2) + midpoint * arb_weight * 0.2
            )
            weighted_challenge = (
                weighted_challenge * (1.0 - arb_weight * 0.2) + midpoint * arb_weight * 0.2
            )

        weighted_confidence = max(weighted_support, weighted_challenge)

        if weighted_support >= weighted_challenge + 0.1 and weighted_support >= 0.65:
            verdict = "ACCEPTED"
        elif weighted_challenge >= weighted_support + 0.1 and weighted_challenge >= 0.65:
            verdict = "REJECTED"
        else:
            verdict = "CONDITIONAL"

        return verdict, self._clamp(weighted_confidence, minimum=0.0, maximum=1.0)

    async def generate_structured_dissent(
        self,
        debate_id: str,
        round_records: list[dict[str, Any]],
        dissenter_role: str,
        session: AsyncSession,
    ) -> DebateStructuredDissent:
        """Generate a structured dissent record from challenger/OPPOSE arguments.

        Collects all arguments from the dissenter role, evidence gaps,
        and the confidence trajectory across rounds.
        """
        challenger_roles = {"challenger", "risk_analyst", "intel_analyst"}

        claims: list[dict[str, Any]] = []
        confidence_trajectory: list[float] = []
        evidence_gaps: list[str] = []
        recommended_monitoring: list[str] = []

        for round_data in round_records:
            role = round_data.get("role", "")
            confidence = round_data.get("confidence", 0.5)
            position = round_data.get("position", "")

            # Track confidence for challenger-side roles
            if role in challenger_roles or position == "OPPOSE":
                confidence_trajectory.append(confidence)

            # Collect arguments from the dissenter side
            if role in challenger_roles or (position == "OPPOSE" and role == dissenter_role):
                for arg in round_data.get("arguments", []):
                    claim_text = arg.get("claim", "")
                    evidence_ids = arg.get("evidence_ids", [])
                    arg_confidence = confidence

                    # Categorize the claim
                    category = "risk"
                    claim_lower = claim_text.lower()
                    if any(kw in claim_lower for kw in ("evidence", "data", "source", "cite")):
                        category = "evidence_quality"
                    elif any(
                        kw in claim_lower for kw in ("alternative", "instead", "could", "option")
                    ):
                        category = "alternative"
                    elif any(kw in claim_lower for kw in ("assumption", "presume", "given that")):
                        category = "assumption_challenge"

                    claims.append(
                        {
                            "claim": claim_text[:500],
                            "evidence": evidence_ids[:5],
                            "confidence": arg_confidence,
                            "category": category,
                        }
                    )

                    # Identify evidence gaps: arguments with no or weak evidence
                    if not evidence_ids:
                        evidence_gaps.append(f"Unsupported claim: {claim_text[:200]}")

        # Build monitoring recommendations from claims
        seen_categories = {c["category"] for c in claims}
        if "risk" in seen_categories:
            recommended_monitoring.append("Track risk indicators identified by challenger.")
        if "evidence_quality" in seen_categories:
            recommended_monitoring.append("Verify evidence sources flagged as weak.")
        if "alternative" in seen_categories:
            recommended_monitoring.append("Evaluate alternative approaches proposed by dissenter.")
        if "assumption_challenge" in seen_categories:
            recommended_monitoring.append("Re-examine challenged assumptions in next review cycle.")
        if not recommended_monitoring:
            recommended_monitoring.append("Continue monitoring debate outcomes for drift.")

        # Compute overall dissent strength
        if claims:
            avg_confidence = sum(c["confidence"] for c in claims) / len(claims)
            # More claims + higher confidence = stronger dissent
            overall_dissent_strength = self._clamp(
                0.3 + 0.1 * len(claims) + 0.3 * avg_confidence,
                minimum=0.0,
                maximum=1.0,
            )
        else:
            overall_dissent_strength = 0.0

        dissent = DebateStructuredDissent(
            debate_id=debate_id,
            dissenter_role=dissenter_role,
            claims=claims,
            evidence_gaps=evidence_gaps,
            confidence_trajectory=confidence_trajectory,
            recommended_monitoring=recommended_monitoring,
            overall_dissent_strength=overall_dissent_strength,
        )
        return dissent
