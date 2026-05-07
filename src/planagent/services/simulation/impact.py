from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from planagent.domain.models import (
    Claim,
    DecisionRecordRecord,
)
from planagent.services.pipeline import normalize_text
from planagent.services.simulation_branching import (
    _STATE_POLICIES,
    MetricPolicy,
)
from planagent.simulation.domain_packs import registry
from planagent.simulation.rules import RuleSpec


@dataclass(frozen=True)
class SelectedAction:
    action_id: str
    why_selected: str
    rule_ids: list[str]
    evidence_ids: list[str]
    expected_effect: dict[str, float]
    actual_effect: dict[str, float]
    decision_method: str = "rule_engine"


@dataclass(frozen=True)
class RuleScore:
    rule: RuleSpec
    claim: Claim
    score: float
    matched_keywords: tuple[str, ...]


@dataclass
class ActionCandidate:
    action_id: str
    rule_scores: list[RuleScore] = field(default_factory=list)
    base_score: float = 0.0
    state_adjustment: float = 0.0
    history_penalty: float = 0.0

    @property
    def total_score(self) -> float:
        return round(self.base_score + self.state_adjustment - self.history_penalty, 4)


_DECISION_EVIDENCE_WINDOW = 3
_DECISION_RECENCY_WEIGHTS = (1.0, 0.65, 0.45)
_DECISION_MIN_SCORE = 0.6


class SimulationImpactMixin:
    def _calculate_impact(
        self,
        state: dict[str, float],
        effect: dict[str, float],
    ) -> dict[str, float]:
        impacted = dict(state)
        self._apply_effects(impacted, effect)
        return impacted

    def _score_probability(self, probability_band: str | float | int | None) -> float:
        if probability_band is None:
            return 0.5
        if isinstance(probability_band, (int, float)):
            return round(max(0.0, min(1.0, float(probability_band))), 4)
        normalized = normalize_text(probability_band).lower()
        lookup = {
            "very_low": 0.1,
            "low": 0.25,
            "medium": 0.5,
            "moderate": 0.5,
            "high": 0.75,
            "very_high": 0.9,
        }
        return lookup.get(normalized.replace(" ", "_"), 0.5)

    def _score_severity(self, impact: dict[str, float]) -> float:
        if not impact:
            return 0.0
        magnitude = sum(abs(float(value)) for value in impact.values()) / max(len(impact), 1)
        return round(max(0.0, min(1.0, magnitude)), 4)

    def _derive_shocks(
        self,
        domain_id: str,
        statement: str,
        evidence_id: str,
    ) -> list[dict[str, Any]]:
        lowered = statement.lower()
        shocks: list[dict[str, Any]] = []
        if domain_id == "corporate":
            if any(keyword in lowered for keyword in ["cost", "price", "gpu"]):
                shocks.append(
                    {
                        "shock_type": "market_cost_pressure",
                        "summary": normalize_text(statement),
                        "payload": {
                            "matched_keywords": ["cost", "price", "gpu"],
                            "evidence_id": evidence_id,
                        },
                    }
                )
            if any(keyword in lowered for keyword in ["ship", "launch", "release"]):
                shocks.append(
                    {
                        "shock_type": "product_launch",
                        "summary": normalize_text(statement),
                        "payload": {
                            "matched_keywords": ["ship", "launch", "release"],
                            "evidence_id": evidence_id,
                        },
                    }
                )
            if any(keyword in lowered for keyword in ["demand", "adoption", "growth"]):
                shocks.append(
                    {
                        "shock_type": "demand_shift",
                        "summary": normalize_text(statement),
                        "payload": {
                            "matched_keywords": ["demand", "adoption", "growth"],
                            "evidence_id": evidence_id,
                        },
                    }
                )
            if any(
                keyword in lowered
                for keyword in ["bundled", "native", "copilot", "platform", "workspace"]
            ):
                shocks.append(
                    {
                        "shock_type": "platform_bundling_pressure",
                        "summary": normalize_text(statement),
                        "payload": {
                            "matched_keywords": [
                                "bundled",
                                "native",
                                "copilot",
                                "platform",
                                "workspace",
                            ],
                            "evidence_id": evidence_id,
                        },
                    }
                )
            if any(
                keyword in lowered
                for keyword in ["security", "compliance", "procurement", "integration", "pilot"]
            ):
                shocks.append(
                    {
                        "shock_type": "enterprise_buying_friction",
                        "summary": normalize_text(statement),
                        "payload": {
                            "matched_keywords": [
                                "security",
                                "compliance",
                                "procurement",
                                "integration",
                                "pilot",
                            ],
                            "evidence_id": evidence_id,
                        },
                    }
                )
            if any(
                keyword in lowered
                for keyword in ["hallucination", "latency", "outage", "accuracy", "reliability"]
            ):
                shocks.append(
                    {
                        "shock_type": "reliability_incident",
                        "summary": normalize_text(statement),
                        "payload": {
                            "matched_keywords": [
                                "hallucination",
                                "latency",
                                "outage",
                                "accuracy",
                                "reliability",
                            ],
                            "evidence_id": evidence_id,
                        },
                    }
                )
            if any(
                keyword in lowered
                for keyword in ["roi", "renewal", "expansion", "savings", "hours"]
            ):
                shocks.append(
                    {
                        "shock_type": "validated_roi",
                        "summary": normalize_text(statement),
                        "payload": {
                            "matched_keywords": ["roi", "renewal", "expansion", "savings", "hours"],
                            "evidence_id": evidence_id,
                        },
                    }
                )
            return shocks

        if any(keyword in lowered for keyword in ["supply", "bridge", "port", "convoy"]):
            shocks.append(
                {
                    "shock_type": "supply_disruption",
                    "summary": normalize_text(statement),
                    "payload": {
                        "matched_keywords": ["supply", "bridge", "port", "convoy"],
                        "evidence_id": evidence_id,
                    },
                }
            )
        if any(keyword in lowered for keyword in ["weather", "storm", "fog", "mud"]):
            shocks.append(
                {
                    "shock_type": "weather_window",
                    "summary": normalize_text(statement),
                    "payload": {
                        "matched_keywords": ["weather", "storm", "fog", "mud"],
                        "evidence_id": evidence_id,
                    },
                }
            )
        if any(keyword in lowered for keyword in ["drone", "swarm", "strike", "airspace"]):
            shocks.append(
                {
                    "shock_type": "air_attack",
                    "summary": normalize_text(statement),
                    "payload": {
                        "matched_keywords": ["drone", "swarm", "strike", "airspace"],
                        "evidence_id": evidence_id,
                    },
                }
            )
        if any(keyword in lowered for keyword in ["isr", "satellite", "recon", "radar"]):
            shocks.append(
                {
                    "shock_type": "isr_window",
                    "summary": normalize_text(statement),
                    "payload": {
                        "matched_keywords": ["isr", "satellite", "recon", "radar"],
                        "evidence_id": evidence_id,
                    },
                }
            )
        if any(keyword in lowered for keyword in ["jam", "electronic", "cyber"]):
            shocks.append(
                {
                    "shock_type": "electronic_attack",
                    "summary": normalize_text(statement),
                    "payload": {
                        "matched_keywords": ["jam", "electronic", "cyber"],
                        "evidence_id": evidence_id,
                    },
                }
            )
        return shocks

    def _apply_external_shock(
        self, domain_id: str, state: dict[str, float], statement: str
    ) -> None:
        lowered = statement.lower()
        if domain_id == "corporate":
            if any(keyword in lowered for keyword in ["cost", "price", "gpu"]):
                state["infra_cost_index"] = state.get("infra_cost_index", 1.0) + 0.08
                state["runway_weeks"] = state.get("runway_weeks", 52.0) - 2.0
                state["gross_margin"] = state.get("gross_margin", 0.62) - 0.05
                state["pipeline"] = state.get("pipeline", 1.0) - 0.02
            if any(keyword in lowered for keyword in ["ship", "launch", "release"]):
                state["brand_index"] = state.get("brand_index", 1.0) + 0.05
                state["market_share"] = state.get("market_share", 0.05) + 0.01
                state["pipeline"] = state.get("pipeline", 1.0) + 0.08
                state["active_deployments"] = state.get("active_deployments", 3.0) + 0.25
                state["support_load"] = state.get("support_load", 0.35) + 0.04
                state["reliability_debt"] = state.get("reliability_debt", 0.28) + 0.02
            if any(keyword in lowered for keyword in ["demand", "adoption", "growth"]):
                state["delivery_velocity"] = state.get("delivery_velocity", 1.0) - 0.01
                state["market_share"] = state.get("market_share", 0.05) + 0.015
                state["pipeline"] = state.get("pipeline", 1.0) + 0.12
                state["active_deployments"] = state.get("active_deployments", 3.0) + 0.3
                state["support_load"] = state.get("support_load", 0.35) + 0.03
            if any(
                keyword in lowered
                for keyword in ["bundled", "native", "copilot", "platform", "workspace"]
            ):
                state["brand_index"] = state.get("brand_index", 1.0) - 0.04
                state["market_share"] = state.get("market_share", 0.05) - 0.02
                state["team_morale"] = state.get("team_morale", 1.0) - 0.01
                state["pipeline"] = state.get("pipeline", 1.0) - 0.08
                state["nrr"] = state.get("nrr", 1.02) - 0.03
                state["churn_risk"] = state.get("churn_risk", 0.12) + 0.04
            if any(
                keyword in lowered
                for keyword in ["security", "compliance", "procurement", "integration", "pilot"]
            ):
                state["delivery_velocity"] = state.get("delivery_velocity", 1.0) - 0.03
                state["cash"] = state.get("cash", 100.0) - 4.0
                state["runway_weeks"] = state.get("runway_weeks", 52.0) - 1.0
                state["active_deployments"] = state.get("active_deployments", 3.0) + 0.2
                state["support_load"] = state.get("support_load", 0.35) + 0.08
                state["implementation_capacity"] = state.get("implementation_capacity", 3.0) - 0.05
            if any(
                keyword in lowered
                for keyword in ["hallucination", "latency", "outage", "accuracy", "reliability"]
            ):
                state["brand_index"] = state.get("brand_index", 1.0) - 0.06
                state["market_share"] = state.get("market_share", 0.05) - 0.015
                state["team_morale"] = state.get("team_morale", 1.0) - 0.03
                state["reliability_debt"] = state.get("reliability_debt", 0.28) + 0.1
                state["support_load"] = state.get("support_load", 0.35) + 0.09
                state["churn_risk"] = state.get("churn_risk", 0.12) + 0.05
                state["nrr"] = state.get("nrr", 1.02) - 0.04
            if any(
                keyword in lowered
                for keyword in ["roi", "renewal", "expansion", "savings", "hours"]
            ):
                state["cash"] = state.get("cash", 100.0) + 8.0
                state["brand_index"] = state.get("brand_index", 1.0) + 0.04
                state["market_share"] = state.get("market_share", 0.05) + 0.015
                state["pipeline"] = state.get("pipeline", 1.0) + 0.06
                state["gross_margin"] = state.get("gross_margin", 0.62) + 0.03
                state["nrr"] = state.get("nrr", 1.02) + 0.05
                state["churn_risk"] = state.get("churn_risk", 0.12) - 0.03
            return

        if any(keyword in lowered for keyword in ["supply", "bridge", "port", "convoy"]):
            state["logistics_throughput"] = state.get("logistics_throughput", 1.0) - 0.12
            state["ammo"] = state.get("ammo", 1.0) - 0.06
            state["readiness"] = state.get("readiness", 1.0) - 0.04
            state["supply_network"] = state.get("supply_network", 0.84) - 0.10
            state["objective_control"] = state.get("objective_control", 0.5) - 0.04
            state["enemy_pressure"] = state.get("enemy_pressure", 0.66) + 0.05
        if any(keyword in lowered for keyword in ["weather", "storm", "fog"]):
            state["mobility"] = state.get("mobility", 1.0) - 0.10
            state["isr_coverage"] = state.get("isr_coverage", 1.0) - 0.05
            state["supply_network"] = state.get("supply_network", 0.84) - 0.05
            state["recovery_capacity"] = state.get("recovery_capacity", 0.68) - 0.02
        if any(keyword in lowered for keyword in ["drone", "swarm", "strike"]):
            state["air_defense"] = state.get("air_defense", 1.0) - 0.08
            state["civilian_risk"] = state.get("civilian_risk", 0.25) + 0.06
            state["escalation_index"] = state.get("escalation_index", 0.3) + 0.05
            state["enemy_pressure"] = state.get("enemy_pressure", 0.66) + 0.07
            state["enemy_readiness"] = state.get("enemy_readiness", 0.82) + 0.03
        if any(keyword in lowered for keyword in ["isr", "satellite", "recon"]):
            state["isr_coverage"] = state.get("isr_coverage", 1.0) + 0.10
            state["information_advantage"] = state.get("information_advantage", 1.0) + 0.08
            state["objective_control"] = state.get("objective_control", 0.5) + 0.04
            state["enemy_pressure"] = state.get("enemy_pressure", 0.66) - 0.03
        if any(keyword in lowered for keyword in ["jam", "electronic", "cyber"]):
            state["ew_control"] = state.get("ew_control", 1.0) - 0.08
            state["command_cohesion"] = state.get("command_cohesion", 1.0) - 0.05
            state["objective_control"] = state.get("objective_control", 0.5) - 0.03
            state["supply_network"] = state.get("supply_network", 0.84) - 0.03

    async def _select_action(
        self,
        domain_id: str,
        state: dict[str, float],
        active_claim: Claim | None,
        rules: list[RuleSpec],
        recent_claims: list[Claim] | None = None,
        action_history: list[str] | None = None,
        recent_decisions: list[DecisionRecordRecord] | None = None,
        calibration_context_text: str = "",
        session: AsyncSession | None = None,
    ) -> SelectedAction:
        evidence_window = self._build_evidence_window(active_claim, recent_claims)
        candidate = self._rank_action_candidates(
            domain_id,
            state,
            evidence_window,
            rules,
            action_history or [],
        )
        if candidate is not None and candidate.total_score >= _DECISION_MIN_SCORE:
            expected = self._aggregate_candidate_effect(candidate)
            return SelectedAction(
                action_id=candidate.action_id,
                why_selected=self._build_selection_explanation(candidate),
                rule_ids=self._candidate_rule_ids(candidate),
                evidence_ids=self._candidate_evidence_ids(candidate),
                expected_effect=expected,
                actual_effect=expected,
                decision_method="rule_engine",
            )

        # Level 2: LLM-assisted decision (when rules produce no strong candidate)
        llm_result = await self._llm_decide_action(
            domain_id,
            state,
            rules,
            evidence_window,
            recent_decisions or [],
            action_history or [],
            calibration_context_text,
            session=session,
        )
        if llm_result is not None:
            return llm_result

        # Level 3: Weighted fallback
        fallback_effect = self._fallback_effect(domain_id, state)
        return SelectedAction(
            action_id=fallback_effect["action_id"],
            why_selected=fallback_effect["why_selected"],
            rule_ids=[],
            evidence_ids=[active_claim.evidence_item_id] if active_claim is not None else [],
            expected_effect=fallback_effect["effects"],
            actual_effect=fallback_effect["effects"],
            decision_method="fallback_random",
        )

    async def _llm_decide_action(
        self,
        domain_id: str,
        state: dict[str, float],
        rules: list[RuleSpec],
        evidence_window: list[Claim],
        recent_decisions: list[DecisionRecordRecord],
        action_history: list[str],
        calibration_context_text: str = "",
        session: AsyncSession | None = None,
    ) -> SelectedAction | None:
        if self.openai_service is None or not self.openai_service.is_configured("report"):
            return None

        pack = registry.get(domain_id)
        available_actions = [
            {"action_id": a.action_id, "description": a.description} for a in pack.action_library
        ]
        state_lines = [f"  {k}: {v:.3f}" for k, v in sorted(state.items())]
        state_summary = "\n".join(state_lines)
        recent = [
            {
                "tick": str(rec.tick),
                "action_id": rec.action_id,
                "why": (rec.why_selected or "")[:120],
            }
            for rec in recent_decisions[-3:]
        ]
        evidence = await self._build_weighted_evidence_context(session, evidence_window[-3:])

        try:
            result = await asyncio.wait_for(
                self.openai_service.generate_action_decision(
                    domain_id=domain_id,
                    state_summary=state_summary,
                    available_actions=available_actions,
                    recent_decisions=recent,
                    evidence=evidence,
                    calibration_context=calibration_context_text,
                    target="report",
                ),
                timeout=10.0,
            )
        except (asyncio.TimeoutError, Exception):
            return None

        if result is None:
            return None

        action_id = result.action_id
        valid_ids = {a.action_id for a in pack.action_library}
        if action_id not in valid_ids:
            matched = [
                a.action_id
                for a in pack.action_library
                if a.action_id in action_id or action_id in a.action_id
            ]
            action_id = matched[0] if matched else None
        if action_id is None:
            return None

        reasoning = result.reasoning or "LLM-assisted action selection."
        expected = dict(result.expected_effect) if result.expected_effect else {}

        return SelectedAction(
            action_id=action_id,
            why_selected=reasoning,
            rule_ids=[],
            evidence_ids=[
                claim.evidence_item_id for claim in evidence_window if claim.evidence_item_id
            ][:3],
            expected_effect=expected,
            actual_effect=expected,
            decision_method="llm_assisted",
        )

    async def _build_weighted_evidence_context(
        self,
        session: AsyncSession | None,
        evidence_window: list[Claim],
    ) -> list[str]:
        if session is None:
            return [claim.statement for claim in evidence_window]
        evidence_ids = [
            claim.evidence_item_id for claim in evidence_window if claim.evidence_item_id
        ]
        context = await self.evidence_weighting.get_evidence_context(session, evidence_ids)
        if context:
            return [line for line in context.splitlines() if line]
        return [claim.statement for claim in evidence_window]

    def _build_evidence_window(
        self,
        active_claim: Claim | None,
        recent_claims: list[Claim] | None,
    ) -> list[Claim]:
        window = list(recent_claims or [])
        if active_claim is not None and (
            not window or self._claim_key(window[-1]) != self._claim_key(active_claim)
        ):
            window.append(active_claim)
        return window[-_DECISION_EVIDENCE_WINDOW:]

    def _rank_action_candidates(
        self,
        domain_id: str,
        state: dict[str, float],
        evidence_window: list[Claim],
        rules: list[RuleSpec],
        action_history: list[str],
    ) -> ActionCandidate | None:
        candidates: dict[str, ActionCandidate] = {}
        for distance, claim in enumerate(reversed(evidence_window)):
            recency_weight = _DECISION_RECENCY_WEIGHTS[
                min(distance, len(_DECISION_RECENCY_WEIGHTS) - 1)
            ]
            confidence = float(claim.confidence or 0.75)
            confidence_weight = 0.7 + (max(0.0, min(confidence, 1.0)) * 0.4)
            for rule in rules:
                matched_keywords = self._matched_keywords(rule, claim.statement)
                if not matched_keywords:
                    continue
                coverage_bonus = 0.08 * max(0, len(matched_keywords) - 1)
                effective_priority = self.rule_registry.effective_priority(rule)
                score = round(
                    ((effective_priority / 100.0) + coverage_bonus)
                    * recency_weight
                    * confidence_weight,
                    4,
                )
                candidate = candidates.setdefault(
                    rule.action_id, ActionCandidate(action_id=rule.action_id)
                )
                candidate.rule_scores.append(
                    RuleScore(
                        rule=rule,
                        claim=claim,
                        score=score,
                        matched_keywords=matched_keywords,
                    )
                )
                candidate.base_score = round(candidate.base_score + score, 4)

        if not candidates:
            return None

        for candidate in candidates.values():
            aggregated_effect = self._aggregate_candidate_effect(candidate)
            candidate.state_adjustment = self._score_state_alignment(
                domain_id,
                state,
                candidate.action_id,
                aggregated_effect,
            )
            candidate.history_penalty = self._score_history_penalty(
                candidate.action_id, action_history
            )

        ranked = sorted(
            candidates.values(),
            key=lambda item: (
                item.total_score,
                item.base_score,
                max((score.score for score in item.rule_scores), default=0.0),
            ),
            reverse=True,
        )
        return ranked[0]

    def _matched_keywords(self, rule: RuleSpec, statement: str) -> tuple[str, ...]:
        lowered = statement.lower()
        return tuple(keyword for keyword in rule.trigger_keywords if keyword.lower() in lowered)

    def _aggregate_candidate_effect(self, candidate: ActionCandidate) -> dict[str, float]:
        aggregated: dict[str, float] = {}
        seen_rules: set[str] = set()
        ranked_scores = sorted(candidate.rule_scores, key=lambda item: item.score, reverse=True)
        for index, score in enumerate(ranked_scores):
            if score.rule.rule_id in seen_rules:
                multiplier = 0.15
            elif index == 0:
                multiplier = 1.0
            else:
                multiplier = 0.35
            seen_rules.add(score.rule.rule_id)
            for target, value in self._effects_to_mapping(score.rule.effects).items():
                aggregated[target] = round(aggregated.get(target, 0.0) + (value * multiplier), 4)

        evidence_count = len({score.claim.evidence_item_id for score in ranked_scores})
        support_multiplier = 1.0 + (0.08 * min(max(evidence_count - 1, 0), 2))
        return {
            target: round(value * support_multiplier, 4) for target, value in aggregated.items()
        }

    def _score_state_alignment(
        self,
        domain_id: str,
        state: dict[str, float],
        action_id: str,
        effects: dict[str, float],
    ) -> float:
        policies = _STATE_POLICIES.get(domain_id, {})
        adjustment = 0.0
        urgent_metric_present = False
        for target, delta in effects.items():
            policy = policies.get(target)
            if policy is None or delta == 0:
                continue
            urgency = self._metric_urgency(float(state.get(target, 0.0)), policy)
            urgent_metric_present = urgent_metric_present or urgency >= 0.5
            helps = self._effect_relieves_pressure(delta, policy)
            harms = self._effect_adds_pressure(delta, policy)
            if urgency == 0:
                if helps:
                    adjustment += 0.04
                elif harms:
                    adjustment -= 0.08
                continue
            if helps:
                adjustment += 0.22 + (0.28 * urgency)
                if self._metric_is_critical(float(state.get(target, 0.0)), policy):
                    adjustment += 0.12
            elif harms:
                adjustment -= 0.3 + (0.35 * urgency)
                if self._metric_is_critical(float(state.get(target, 0.0)), policy):
                    adjustment -= 0.2

        if action_id == "monitor" and urgent_metric_present:
            adjustment -= 0.25
        return round(adjustment, 4)

    def _metric_urgency(self, value: float, policy: MetricPolicy) -> float:
        if policy.preferred_direction == "increase":
            if value >= policy.alert_threshold:
                return 0.0
            denominator = max(policy.alert_threshold - policy.critical_threshold, 0.01)
            return min(1.0, max(0.0, (policy.alert_threshold - value) / denominator))

        if value <= policy.alert_threshold:
            return 0.0
        denominator = max(policy.critical_threshold - policy.alert_threshold, 0.01)
        return min(1.0, max(0.0, (value - policy.alert_threshold) / denominator))

    def _metric_is_critical(self, value: float, policy: MetricPolicy) -> bool:
        if policy.preferred_direction == "increase":
            return value <= policy.critical_threshold
        return value >= policy.critical_threshold

    def _effect_relieves_pressure(self, delta: float, policy: MetricPolicy) -> bool:
        return (policy.preferred_direction == "increase" and delta > 0) or (
            policy.preferred_direction == "decrease" and delta < 0
        )

    def _effect_adds_pressure(self, delta: float, policy: MetricPolicy) -> bool:
        return (policy.preferred_direction == "increase" and delta < 0) or (
            policy.preferred_direction == "decrease" and delta > 0
        )

    def _score_history_penalty(self, action_id: str, action_history: list[str]) -> float:
        penalty = 0.0
        for distance, previous_action in enumerate(reversed(action_history[-3:]), start=1):
            if previous_action != action_id:
                continue
            if distance == 1:
                penalty += 0.75
            elif distance == 2:
                penalty += 0.3
            else:
                penalty += 0.15
        return round(penalty, 4)

    def _candidate_rule_ids(self, candidate: ActionCandidate) -> list[str]:
        ordered_rule_ids: list[str] = []
        seen: set[str] = set()
        for score in sorted(candidate.rule_scores, key=lambda item: item.score, reverse=True):
            if score.rule.rule_id in seen:
                continue
            seen.add(score.rule.rule_id)
            ordered_rule_ids.append(score.rule.rule_id)
        return ordered_rule_ids

    def _candidate_evidence_ids(self, candidate: ActionCandidate) -> list[str]:
        ordered_evidence_ids: list[str] = []
        seen: set[str] = set()
        for score in sorted(candidate.rule_scores, key=lambda item: item.score, reverse=True):
            evidence_id = score.claim.evidence_item_id
            if evidence_id in seen:
                continue
            seen.add(evidence_id)
            ordered_evidence_ids.append(evidence_id)
        return ordered_evidence_ids

    def _build_selection_explanation(self, candidate: ActionCandidate) -> str:
        top_score = max(candidate.rule_scores, key=lambda item: item.score)
        rule_ids = self._candidate_rule_ids(candidate)
        evidence_count = len(self._candidate_evidence_ids(candidate))
        return (
            f"Selected {candidate.action_id} from {len(rule_ids)} supporting rule(s) "
            f"across {evidence_count} evidence item(s); top signal was {top_score.rule.rule_id} "
            f"and the final score was {candidate.total_score:.2f} after state and history adjustments."
        )

    def _claim_key(self, claim: Claim) -> str:
        claim_id = getattr(claim, "id", None)
        if claim_id:
            return str(claim_id)
        return f"{claim.evidence_item_id}:{normalize_text(claim.statement).lower()}"

    def _effects_to_mapping(self, effects: tuple[Any, ...]) -> dict[str, float]:
        result: dict[str, float] = {}
        for effect in effects:
            if effect.op != "add":
                continue
            result[effect.target] = result.get(effect.target, 0.0) + float(effect.value)
        return result

    def _fallback_effect(self, domain_id: str, state: dict[str, float]) -> dict[str, Any]:
        if domain_id == "corporate":
            deployment_load = state.get("active_deployments", 3.0) / max(
                state.get("implementation_capacity", 3.0), 1.0
            )
            if (
                state.get("pipeline", 1.0) > 1.15
                and deployment_load > 0.95
                and state.get("support_load", 0.35) > 0.48
                and state.get("runway_weeks", 52.0) > 48.0
                and state.get("gross_margin", 0.62) > 0.6
            ):
                return {
                    "action_id": "hire",
                    "why_selected": (
                        "Fallback policy invested in delivery capacity because qualified demand outran "
                        "implementation bandwidth while retention economics stayed healthy."
                    ),
                    "effects": {
                        "delivery_velocity": 0.05,
                        "implementation_capacity": 0.45,
                        "support_load": -0.06,
                        "cash": -8.0,
                        "runway_weeks": -2.0,
                    },
                }
            if state.get("runway_weeks", 52.0) < 28.0 or state.get("cash", 100.0) < 30.0:
                return {
                    "action_id": "tighten_scope",
                    "why_selected": "Fallback policy narrowed scope because liquidity and deployment capacity entered the red zone.",
                    "effects": {
                        "runway_weeks": 4.0,
                        "delivery_velocity": 0.03,
                        "brand_index": 0.01,
                        "market_share": -0.005,
                        "support_load": -0.08,
                        "reliability_debt": -0.04,
                        "active_deployments": -0.2,
                    },
                }
            if (
                state.get("brand_index", 1.0) < 0.88
                or state.get("reliability_debt", 0.28) > 0.44
                or state.get("churn_risk", 0.12) > 0.2
            ):
                return {
                    "action_id": "improve_reliability",
                    "why_selected": (
                        "Fallback policy prioritized trust recovery after reliability debt and renewal risk "
                        "started to outweigh short-term delivery pressure."
                    ),
                    "effects": {
                        "brand_index": 0.05,
                        "market_share": 0.005,
                        "delivery_velocity": -0.04,
                        "team_morale": -0.01,
                        "reliability_debt": -0.1,
                        "support_load": -0.07,
                        "nrr": 0.03,
                        "churn_risk": -0.05,
                    },
                }
            if (
                state.get("market_share", 0.05) < 0.03 and state.get("brand_index", 1.0) < 0.95
            ) or state.get("pipeline", 1.0) < 0.8:
                return {
                    "action_id": "focus_vertical",
                    "why_selected": (
                        "Fallback policy narrowed the wedge because broad positioning stopped converting into "
                        "qualified pipeline and durable retention."
                    ),
                    "effects": {
                        "brand_index": 0.03,
                        "market_share": 0.01,
                        "delivery_velocity": -0.03,
                        "pipeline": 0.08,
                        "gross_margin": 0.04,
                        "nrr": 0.02,
                        "churn_risk": -0.02,
                    },
                }
            if state.get("infra_cost_index", 1.0) > 1.1 or state.get("gross_margin", 0.62) < 0.55:
                return {
                    "action_id": "optimize_cost",
                    "why_selected": "Fallback policy detected sustained cost pressure and deteriorating unit economics.",
                    "effects": {
                        "infra_cost_index": -0.05,
                        "runway_weeks": 2.0,
                        "delivery_velocity": -0.01,
                        "gross_margin": 0.05,
                        "support_load": -0.02,
                    },
                }
            return {
                "action_id": "monitor",
                "why_selected": "No rule crossed the action threshold, so the baseline policy held position.",
                "effects": {"brand_index": 0.01, "pipeline": 0.01},
            }

        if state.get("civilian_risk", 0.0) > 0.55:
            return {
                "action_id": "protect_civilians",
                "why_selected": "Fallback policy prioritized civilian protection after risk crossed the alert line.",
                "effects": {
                    "civilian_risk": -0.08,
                    "readiness": -0.01,
                    "escalation_index": -0.04,
                    "objective_control": -0.02,
                },
            }
        if (
            state.get("logistics_throughput", 1.0) < 0.82
            or state.get("supply_network", 0.84) < 0.76
        ):
            return {
                "action_id": "open_supply_line",
                "why_selected": "Fallback policy restored the supply corridor to recover readiness.",
                "effects": {
                    "logistics_throughput": 0.10,
                    "supply_network": 0.08,
                    "ammo": 0.05,
                    "readiness": 0.03,
                    "recovery_capacity": 0.02,
                },
            }
        if state.get("objective_control", 0.5) < 0.48:
            return {
                "action_id": "secure_objective",
                "why_selected": "Fallback policy stabilized the decisive objective before the force lost positional leverage.",
                "effects": {
                    "objective_control": 0.08,
                    "enemy_pressure": -0.04,
                    "attrition_rate": -0.02,
                    "mobility": -0.02,
                },
            }
        if state.get("enemy_pressure", 0.66) > 0.7 or state.get("enemy_readiness", 0.82) > 0.82:
            return {
                "action_id": "suppress_enemy_fires",
                "why_selected": "Fallback policy disrupted enemy pressure before additional fires stacked onto the corridor fight.",
                "effects": {
                    "enemy_pressure": -0.08,
                    "enemy_readiness": -0.04,
                    "information_advantage": 0.03,
                    "ammo": -0.04,
                    "escalation_index": 0.03,
                },
            }
        if state.get("attrition_rate", 0.18) > 0.28 or state.get("recovery_capacity", 0.68) < 0.58:
            return {
                "action_id": "rotate_and_repair",
                "why_selected": "Fallback policy rotated damaged elements because attrition outpaced recovery capacity.",
                "effects": {
                    "readiness": 0.05,
                    "attrition_rate": -0.05,
                    "recovery_capacity": 0.05,
                    "mobility": -0.03,
                },
            }
        if state.get("air_defense", 1.0) < 0.85:
            return {
                "action_id": "rebalance_air_defense",
                "why_selected": "Fallback policy shifted coverage to reduce incoming drone exposure.",
                "effects": {
                    "air_defense": 0.09,
                    "mobility": -0.02,
                    "enemy_pressure": -0.04,
                    "civilian_risk": -0.03,
                },
            }
        return {
            "action_id": "fortify",
            "why_selected": "No military rule crossed the threshold, so the force hardened its current position.",
            "effects": {
                "readiness": 0.02,
                "air_defense": 0.03,
                "objective_control": 0.03,
                "attrition_rate": -0.02,
            },
        }

    def _apply_effects(self, state: dict[str, float], effect: dict[str, float]) -> None:
        for key, delta in effect.items():
            state[key] = round(float(state.get(key, 0.0)) + float(delta), 4)
