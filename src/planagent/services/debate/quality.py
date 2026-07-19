from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from planagent.domain.enums import ClaimStatus
from planagent.domain.models import Claim, DebateReliabilityScore, DebateStructuredDissent
from planagent.services.pipeline import normalize_text

from ._quality_rules import (
    _BIAS_PATTERNS,
    _CLAIM_STOPWORDS,
    _NEGATIVE_CLAIM_KEYWORDS,
    _POSITIVE_CLAIM_KEYWORDS,
    _RISK_DIMENSIONS,
    _TOKEN_RE,
)
from .contracts import ClaimRelationContext


class DebateQualityMixin:
    """Concentrate claim relations, reliability, blind spots, and dissent."""

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

    @staticmethod
    def _claim_tokens(statement: str) -> set[str]:
        normalized = normalize_text(statement).lower()
        return {
            token
            for token in _TOKEN_RE.findall(normalized)
            if len(token) > 2 and token not in _CLAIM_STOPWORDS
        }

    @staticmethod
    def _claim_similarity(base_tokens: set[str], candidate_tokens: set[str]) -> float:
        if not base_tokens or not candidate_tokens:
            return 0.0
        overlap = len(base_tokens & candidate_tokens)
        union = len(base_tokens | candidate_tokens)
        if union == 0:
            return 0.0
        return overlap / union

    @staticmethod
    def _claim_direction(statement: str) -> int:
        normalized = normalize_text(statement).lower()
        tokens = set(_TOKEN_RE.findall(normalized))
        positive_hits = len(tokens & _POSITIVE_CLAIM_KEYWORDS)
        negative_hits = len(tokens & _NEGATIVE_CLAIM_KEYWORDS)
        if positive_hits > negative_hits:
            return 1
        if negative_hits > positive_hits:
            return -1
        return 0

    @staticmethod
    def _clamp(value: float, minimum: float, maximum: float) -> float:
        return max(minimum, min(maximum, value))

    @staticmethod
    def _detect_biases(text: str) -> list[str]:
        lower = text.lower()
        return [
            bias_name
            for bias_name, patterns in _BIAS_PATTERNS.items()
            if any(pattern in lower for pattern in patterns)
        ]

    @staticmethod
    def _assess_evidence_strength(argument: dict[str, Any]) -> str:
        strength = argument.get("strength", "MODERATE").upper()
        evidence_ids = argument.get("evidence_ids", [])
        if strength == "STRONG" and len(evidence_ids) >= 2:
            return "strong"
        if strength in ("STRONG", "MODERATE") and evidence_ids:
            return "moderate"
        if evidence_ids:
            return "weak"
        return "speculative"

    @staticmethod
    def _compute_reliability_score(
        bias_flags: list[str], evidence_strength: str, reasoning: str
    ) -> int:
        base = 4
        base += {"strong": 1, "moderate": 0, "weak": -1, "speculative": -2}.get(
            evidence_strength, 0
        )
        base -= len(bias_flags)
        if len(reasoning.strip()) < 20:
            base -= 1
        return max(1, min(5, base))

    async def score_argument_reliability(
        self,
        debate_id: str,
        round_records: list[dict[str, Any]],
        session: AsyncSession,
    ) -> list[DebateReliabilityScore]:
        scores: list[DebateReliabilityScore] = []
        for round_data in round_records:
            round_number = round_data.get("round_number", 1)
            role = round_data.get("role", "unknown")
            for index, argument in enumerate(round_data.get("arguments", [])):
                claim_text = argument.get("claim", "")
                reasoning = argument.get("reasoning", "")
                combined_text = f"{claim_text} {reasoning}"
                bias_flags = self._detect_biases(combined_text)
                evidence_strength = self._assess_evidence_strength(argument)
                reliability_score = self._compute_reliability_score(
                    bias_flags, evidence_strength, reasoning
                )

                blind_spots: list[str] = []
                argument_text = combined_text.lower()
                covered_dimensions = {
                    dimension
                    for dimension, keywords in _RISK_DIMENSIONS.items()
                    if any(keyword in argument_text for keyword in keywords)
                }
                if any(
                    phrase in argument_text
                    for phrase in (
                        "all factors",
                        "comprehensive",
                        "holistic",
                        "all risks",
                        "all aspects",
                    )
                ):
                    blind_spots.extend(
                        f"claims_completeness_but_ignores_{dimension}"
                        for dimension in _RISK_DIMENSIONS
                        if dimension not in covered_dimensions
                    )

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
                score = DebateReliabilityScore(
                    debate_id=debate_id,
                    round_number=round_number,
                    role=role,
                    argument_index=index,
                    argument_summary=claim_text[:500],
                    reliability_score=reliability_score,
                    bias_flags=bias_flags,
                    blind_spots=blind_spots,
                    evidence_strength=evidence_strength,
                    auditor_role=auditor_role,
                )
                session.add(score)
                scores.append(score)
        return scores

    @staticmethod
    def detect_blind_spots(round_records: list[dict[str, Any]]) -> list[str]:
        text_parts = [
            text
            for round_data in round_records
            for argument in round_data.get("arguments", [])
            for text in (argument.get("claim", ""), argument.get("reasoning", ""))
        ]
        tokens = set(_TOKEN_RE.findall(" ".join(text_parts).lower()))
        return [
            f"No argument addressed the '{dimension}' risk dimension."
            for dimension, keywords in _RISK_DIMENSIONS.items()
            if not tokens & keywords
        ]

    def weighted_consensus(
        self,
        support_confidence: float,
        challenge_confidence: float,
        domain_weights: dict[str, float],
    ) -> tuple[str, float]:
        support_weight = domain_weights.get("strategist", 1.0)
        challenge_weight = domain_weights.get("risk_analyst", 1.0)
        arbitrator_weight = domain_weights.get("opportunist", 0.5)
        weighted_support = support_confidence * support_weight
        weighted_challenge = challenge_confidence * challenge_weight
        if arbitrator_weight != 1.0:
            midpoint = (weighted_support + weighted_challenge) / 2.0
            weighted_support = (
                weighted_support * (1.0 - arbitrator_weight * 0.2)
                + midpoint * arbitrator_weight * 0.2
            )
            weighted_challenge = (
                weighted_challenge * (1.0 - arbitrator_weight * 0.2)
                + midpoint * arbitrator_weight * 0.2
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
        challenger_roles = {"challenger", "risk_analyst", "intel_analyst"}
        claims: list[dict[str, Any]] = []
        confidence_trajectory: list[float] = []
        evidence_gaps: list[str] = []
        recommended_monitoring: list[str] = []

        for round_data in round_records:
            role = round_data.get("role", "")
            confidence = round_data.get("confidence", 0.5)
            position = round_data.get("position", "")
            if role in challenger_roles or position == "OPPOSE":
                confidence_trajectory.append(confidence)
            if role not in challenger_roles and not (
                position == "OPPOSE" and role == dissenter_role
            ):
                continue
            for argument in round_data.get("arguments", []):
                claim_text = argument.get("claim", "")
                evidence_ids = argument.get("evidence_ids", [])
                category = "risk"
                claim_lower = claim_text.lower()
                if any(
                    keyword in claim_lower for keyword in ("evidence", "data", "source", "cite")
                ):
                    category = "evidence_quality"
                elif any(
                    keyword in claim_lower
                    for keyword in ("alternative", "instead", "could", "option")
                ):
                    category = "alternative"
                elif any(
                    keyword in claim_lower for keyword in ("assumption", "presume", "given that")
                ):
                    category = "assumption_challenge"
                claims.append(
                    {
                        "claim": claim_text[:500],
                        "evidence": evidence_ids[:5],
                        "confidence": confidence,
                        "category": category,
                    }
                )
                if not evidence_ids:
                    evidence_gaps.append(f"Unsupported claim: {claim_text[:200]}")

        categories = {claim["category"] for claim in claims}
        if "risk" in categories:
            recommended_monitoring.append("Track risk indicators identified by challenger.")
        if "evidence_quality" in categories:
            recommended_monitoring.append("Verify evidence sources flagged as weak.")
        if "alternative" in categories:
            recommended_monitoring.append("Evaluate alternative approaches proposed by dissenter.")
        if "assumption_challenge" in categories:
            recommended_monitoring.append("Re-examine challenged assumptions in next review cycle.")
        if not recommended_monitoring:
            recommended_monitoring.append("Continue monitoring debate outcomes for drift.")

        if claims:
            average_confidence = sum(claim["confidence"] for claim in claims) / len(claims)
            dissent_strength = self._clamp(
                0.3 + 0.1 * len(claims) + 0.3 * average_confidence,
                minimum=0.0,
                maximum=1.0,
            )
        else:
            dissent_strength = 0.0

        return DebateStructuredDissent(
            debate_id=debate_id,
            dissenter_role=dissenter_role,
            claims=claims,
            evidence_gaps=evidence_gaps,
            confidence_trajectory=confidence_trajectory,
            recommended_monitoring=recommended_monitoring,
            overall_dissent_strength=dissent_strength,
        )
