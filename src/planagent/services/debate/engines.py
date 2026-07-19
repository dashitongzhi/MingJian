from __future__ import annotations

from typing import Any

from .roles import debate_role_label, debate_round_sort_key


class HeuristicDebateAdapter:
    """Build deterministic full-panel rounds without an external model provider."""

    def build_full_panel(
        self,
        *,
        subject_name: str,
        support_confidence: float,
        challenge_confidence: float,
        verdict: str,
        decisive_evidence: list[str],
        winning_arguments: list[str],
        minority_opinion: str | None,
        conditions: list[str] | None,
        focus: str,
        role_claims: dict[str, tuple[str, str]] | None,
        custom_agents: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Return deterministic, canonically ordered rounds for one debate assessment."""
        support_claim = (winning_arguments or [f"{focus} remains supportable."])[0]
        risk_claim = minority_opinion or f"{focus} still has unresolved downside risk."
        role_claims = role_claims or {}

        default_claims = {
            "advocate": (
                support_claim,
                f"The strategic support case for {subject_name} remains coherent under the available evidence.",
            ),
            "intel_analyst": (
                decisive_evidence[0] if decisive_evidence else f"{focus} needs source refresh.",
                "The intelligence assessor validates the available evidence and flags missing corroboration.",
            ),
            "geo_expert": (
                support_claim,
                "The geopolitical perspective checks alliance, geography, and external posture constraints.",
            ),
            "econ_analyst": (
                support_claim,
                "The economic perspective weighs resource cost, opportunity cost, and sustainability.",
            ),
            "military_strategist": (
                support_claim,
                "The military perspective evaluates readiness, feasibility, logistics, and escalation exposure.",
            ),
            "tech_foresight": (
                support_claim,
                "The technical perspective tests whether capability and infrastructure assumptions remain plausible.",
            ),
            "social_impact": (
                risk_claim,
                "The social perspective keeps civilian, legitimacy, and stakeholder-response constraints visible.",
            ),
        }
        default_claims.update(role_claims)
        challenger_claim, challenger_reasoning = role_claims.get(
            "challenger",
            (
                risk_claim,
                "The challenger pressure-tests every first-round expert claim and preserves unresolved downside.",
            ),
        )

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
                        "evidence_ids": decisive_evidence[:3],
                        "reasoning": reasoning,
                        "strength": strength,
                    }
                ],
                "rebuttals": rebuttals or [],
                "concessions": concessions or [],
            }

        rounds = [
            make_round(
                1,
                role,
                "SUPPORT" if role != "social_impact" else "CONDITIONAL",
                support_confidence
                if role != "social_impact"
                else self._clamp(
                    (support_confidence + challenge_confidence) / 2,
                    0.2,
                    0.9,
                ),
                default_claims[role][0],
                default_claims[role][1],
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
                    challenger_claim,
                    challenger_reasoning,
                    strength="STRONG",
                    rebuttals=[
                        {
                            "target_argument_idx": 0,
                            "counter": support_claim,
                            "evidence_ids": decisive_evidence[:3],
                        }
                    ],
                ),
                make_round(
                    2,
                    "intel_analyst",
                    "CONDITIONAL",
                    self._clamp(
                        (support_confidence + challenge_confidence) / 2,
                        0.2,
                        0.9,
                    ),
                    "Fact check: the evidence supports a provisional verdict, but confidence depends on refresh quality.",
                    "The evidence assessor revisits all first-round claims and marks what needs source review.",
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
                    f"{label} revised view: {focus} remains supportable with explicit monitoring.",
                    f"{label} keeps supported claims, narrows weak assumptions, and responds to the challenger.",
                    rebuttals=[
                        {
                            "target_argument_idx": 0,
                            "counter": risk_claim,
                            "evidence_ids": decisive_evidence[:3],
                        }
                    ],
                    concessions=(
                        [{"argument_idx": 0, "reason": conditions[0]}]
                        if conditions and role == "advocate"
                        else []
                    ),
                )
            )

        for custom_agent in custom_agents:
            role_key = str(custom_agent.get("role_key", "custom_agent"))
            name = str(custom_agent.get("name", role_key))
            description = str(custom_agent.get("description", ""))[:180]
            custom_confidence = self._clamp(
                (support_confidence + challenge_confidence) / 2,
                0.2,
                0.9,
            )
            rounds.append(
                make_round(
                    1,
                    role_key,
                    "CONDITIONAL",
                    custom_confidence,
                    f"{name} participated in the expert panel.",
                    description
                    or "The custom agent contributed a specialized independent perspective.",
                )
            )
            rounds.append(
                make_round(
                    3,
                    role_key,
                    "CONDITIONAL",
                    self._clamp(custom_confidence - 0.02, 0.2, 0.9),
                    f"{name} revised its view after challenger pressure.",
                    "The custom agent acknowledged the shared debate history and preserved its key monitoring point.",
                    rebuttals=[
                        {
                            "target_argument_idx": 0,
                            "counter": risk_claim,
                            "evidence_ids": decisive_evidence[:3],
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
                "The arbitrator weighted all nine built-in roles, custom inputs, challenged claims, conditions, and minority concerns.",
                strength="STRONG",
                concessions=([{"argument_idx": 0, "reason": conditions[0]}] if conditions else []),
            )
        )
        rounds.sort(key=lambda item: debate_round_sort_key(item["round_number"], item["role"]))
        return rounds

    @staticmethod
    def _verdict_position(verdict: str) -> str:
        if verdict == "ACCEPTED":
            return "SUPPORT"
        if verdict == "REJECTED":
            return "OPPOSE"
        return "CONDITIONAL"

    @staticmethod
    def _clamp(value: float, minimum: float, maximum: float) -> float:
        return max(minimum, min(maximum, value))
