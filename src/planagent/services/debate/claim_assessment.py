from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from planagent.domain.api import DebateTriggerRequest
from planagent.domain.enums import ClaimStatus
from planagent.domain.models import Claim, EvidenceItem

from .contracts import DebateAssessment
from .engines import HeuristicDebateAdapter, load_custom_debate_agents

_HEURISTIC_DEBATE_ADAPTER = HeuristicDebateAdapter()


class ClaimDebateAssessmentStrategy:
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
        llm_rounds = await self.llm_adapter.collect_rounds(
            topic=payload.topic,
            trigger_type=payload.trigger_type,
            context=llm_context,
            evidence_ids=decisive_evidence_pre,
            debate_mode=payload.debate_mode,
            domain_id=payload.domain_id,
            custom_agents=load_custom_debate_agents(),
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
            custom_agents=load_custom_debate_agents(),
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
