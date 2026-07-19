from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from planagent.domain.api import DebateTriggerRequest
from planagent.domain.models import GeneratedReport, ScenarioBranchRecord, SimulationRun

from .contracts import DebateAssessment
from .engines import HeuristicDebateAdapter, load_custom_debate_agents

_HEURISTIC_DEBATE_ADAPTER = HeuristicDebateAdapter()


class BranchDebateAssessmentStrategy:
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
            custom_agents=load_custom_debate_agents(),
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
