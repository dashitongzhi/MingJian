from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from planagent.domain.api import DebateTriggerRequest
from planagent.domain.models import (
    CompanyProfile,
    DecisionRecordRecord,
    ExternalShockRecord,
    ForceProfile,
    GeneratedReport,
    SimulationRun,
)

from .contracts import DebateAssessment
from .engines import load_custom_debate_agents
from .roles import debate_role_label


class RunDebateAssessmentStrategy:
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
        llm_rounds = await self.llm_adapter.collect_rounds(
            topic=payload.topic,
            trigger_type=payload.trigger_type,
            context=llm_context,
            evidence_ids=evidence_ids[:5],
            debate_mode=payload.debate_mode,
            domain_id=payload.domain_id or run.domain_id,
            custom_agents=load_custom_debate_agents(),
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

        for custom_agent in load_custom_debate_agents():
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
