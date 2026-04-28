from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from planagent.config import Settings
from planagent.domain.api import DebateDetailRead, DebateSummaryRead, DebateTriggerRequest, DebateVerdictRead
from planagent.domain.enums import ClaimStatus, EventTopic
from planagent.domain.models import (
    Claim,
    CompanyProfile,
    DebateRoundRecord,
    DebateSessionRecord,
    DebateVerdictRecord,
    DecisionRecordRecord,
    DecisionOption,
    EventArchive,
    EvidenceItem,
    ExternalShockRecord,
    ForceProfile,
    GeneratedReport,
    Hypothesis,
    ScenarioBranchRecord,
    SimulationRun,
)
from planagent.events.bus import EventBus
from planagent.services.openai_client import OpenAIService
from planagent.services.pipeline import normalize_text

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


@dataclass(frozen=True)
class DebateAssessment:
    support_confidence: float
    challenge_confidence: float
    verdict: str
    winning_arguments: list[str]
    decisive_evidence: list[str]
    conditions: list[str] | None
    minority_opinion: str | None
    context_payload: dict[str, Any]
    rounds: list[dict[str, Any]]


@dataclass(frozen=True)
class ClaimRelationContext:
    supportive_claims: list[Claim]
    conflicting_claims: list[Claim]


class DebateService:
    def __init__(
        self,
        settings: Settings,
        event_bus: EventBus,
        openai_service: OpenAIService | None = None,
    ) -> None:
        self.settings = settings
        self.event_bus = event_bus
        self.openai_service = openai_service

    async def trigger_debate(
        self,
        session: AsyncSession,
        payload: DebateTriggerRequest,
    ) -> DebateDetailRead:
        payload = await self._resolve_trigger_payload(session, payload)
        if payload.run_id is None and payload.claim_id is None:
            raise ValueError("Debate trigger requires run_id or claim_id.")

        assessment = await self._assess_debate(session, payload)
        run = await session.get(SimulationRun, payload.run_id) if payload.run_id is not None else None
        claim = await session.get(Claim, payload.claim_id) if payload.claim_id is not None else None
        debate_session = DebateSessionRecord(
            run_id=payload.run_id,
            claim_id=payload.claim_id,
            tenant_id=(claim.tenant_id if claim is not None else None) or (run.tenant_id if run is not None else None),
            preset_id=(claim.preset_id if claim is not None else None) or (run.preset_id if run is not None else None),
            topic=payload.topic,
            trigger_type=payload.trigger_type,
            status="COMPLETED",
            target_type=payload.target_type,
            target_id=payload.target_id or payload.claim_id or payload.run_id,
            context_payload=assessment.context_payload,
        )
        session.add(debate_session)
        await session.flush()

        trigger_payload = {
            "debate_id": debate_session.id,
            "run_id": payload.run_id,
            "claim_id": payload.claim_id,
            "topic": payload.topic,
            "trigger_type": payload.trigger_type,
        }
        session.add(EventArchive(topic=EventTopic.DEBATE_TRIGGERED.value, payload=trigger_payload))

        for round_payload in assessment.rounds:
            session.add(
                DebateRoundRecord(
                    debate_id=debate_session.id,
                    round_number=round_payload["round_number"],
                    role=round_payload["role"],
                    position=round_payload["position"],
                    confidence=round_payload["confidence"],
                    arguments=round_payload["arguments"],
                    rebuttals=round_payload["rebuttals"],
                    concessions=round_payload["concessions"],
                )
            )

        verdict = DebateVerdictRecord(
            debate_id=debate_session.id,
            topic=payload.topic,
            trigger_type=payload.trigger_type,
            rounds_completed=max(round_data["round_number"] for round_data in assessment.rounds),
            verdict=assessment.verdict,
            confidence=max(assessment.support_confidence, assessment.challenge_confidence),
            winning_arguments=assessment.winning_arguments,
            decisive_evidence=assessment.decisive_evidence,
            conditions=assessment.conditions,
            minority_opinion=assessment.minority_opinion,
        )
        session.add(verdict)

        if payload.trigger_type == "pivot_decision" and payload.run_id is not None:
            latest_decision = (
                await session.scalars(
                    select(DecisionRecordRecord)
                    .where(DecisionRecordRecord.run_id == payload.run_id)
                    .order_by(DecisionRecordRecord.tick.desc(), DecisionRecordRecord.sequence.desc())
                    .limit(1)
                )
            ).first()
            if latest_decision is not None:
                latest_decision.debate_verdict_id = debate_session.id
            if run is not None:
                run.summary = {
                    **(run.summary or {}),
                    "latest_debate_id": debate_session.id,
                    "latest_debate_verdict": assessment.verdict,
                    "debate_disagreements": [assessment.minority_opinion] if assessment.minority_opinion else [],
                }
                await self._ensure_debate_prediction(session, run, verdict, latest_decision)

        completed_payload = {
            "debate_id": debate_session.id,
            "run_id": payload.run_id,
            "claim_id": payload.claim_id,
            "verdict": assessment.verdict,
            "confidence": verdict.confidence,
        }
        session.add(EventArchive(topic=EventTopic.DEBATE_COMPLETED.value, payload=completed_payload))

        await session.commit()
        await self.event_bus.publish(EventTopic.DEBATE_TRIGGERED.value, trigger_payload)
        await self.event_bus.publish(EventTopic.DEBATE_COMPLETED.value, completed_payload)
        return await self.get_debate(session, debate_session.id)

    async def _ensure_debate_prediction(
        self,
        session: AsyncSession,
        run: SimulationRun,
        verdict: DebateVerdictRecord,
        latest_decision: DecisionRecordRecord | None,
    ) -> None:
        option = (
            await session.scalars(
                select(DecisionOption)
                .where(DecisionOption.run_id == run.id)
                .order_by(DecisionOption.ranking.asc())
                .limit(1)
            )
        ).first()
        if option is None:
            option = DecisionOption(
                run_id=run.id,
                tenant_id=run.tenant_id,
                preset_id=run.preset_id,
                title=f"Debate verdict: {verdict.verdict}"[:255],
                description=(verdict.winning_arguments or [verdict.topic])[0][:2000],
                expected_effects=latest_decision.expected_effect if latest_decision is not None else {},
                risks=([verdict.minority_opinion] if verdict.minority_opinion else []),
                evidence_ids=verdict.decisive_evidence,
                confidence=verdict.confidence,
                conditions=verdict.conditions or [],
                ranking=1,
            )
            session.add(option)
            await session.flush()

        existing_hypothesis = (
            await session.scalars(
                select(Hypothesis)
                .where(Hypothesis.run_id == run.id, Hypothesis.decision_option_id == option.id)
                .limit(1)
            )
        ).first()
        if existing_hypothesis is not None:
            return
        horizon = "1_week" if run.domain_id == "military" else "3_months"
        prediction = (
            f"Debate verdict {verdict.verdict} with confidence {verdict.confidence:.2f} "
            f"will remain supportable over {horizon} if decisive evidence holds."
        )
        session.add(
            Hypothesis(
                run_id=run.id,
                decision_option_id=option.id,
                tenant_id=run.tenant_id,
                preset_id=run.preset_id,
                prediction=prediction,
                time_horizon=horizon,
            )
        )

    async def _resolve_trigger_payload(
        self,
        session: AsyncSession,
        payload: DebateTriggerRequest,
    ) -> DebateTriggerRequest:
        if payload.target_type != "branch":
            return payload

        branch: ScenarioBranchRecord | None = None
        if payload.target_id:
            branch = await session.get(ScenarioBranchRecord, payload.target_id)
            if branch is None:
                raise LookupError(f"Scenario branch {payload.target_id} was not found.")
        elif payload.run_id is not None:
            branch = (
                await session.scalars(
                    select(ScenarioBranchRecord).where(ScenarioBranchRecord.run_id == payload.run_id).limit(1)
                )
            ).first()
            if branch is None:
                raise LookupError(f"Run {payload.run_id} is not attached to a scenario branch.")

        if branch is None:
            raise ValueError("Branch debates require target_id or run_id.")
        return payload.model_copy(update={"run_id": branch.run_id, "target_id": branch.id})

    async def get_debate(self, session: AsyncSession, debate_id: str) -> DebateDetailRead:
        debate = await session.get(DebateSessionRecord, debate_id)
        if debate is None:
            raise LookupError(f"Debate {debate_id} was not found.")

        rounds = list(
            (
                await session.scalars(
                    select(DebateRoundRecord)
                    .where(DebateRoundRecord.debate_id == debate_id)
                    .order_by(DebateRoundRecord.round_number.asc(), DebateRoundRecord.role.asc())
                )
            ).all()
        )
        verdict = await session.get(DebateVerdictRecord, debate_id)
        return DebateDetailRead(
            id=debate.id,
            run_id=debate.run_id,
            claim_id=debate.claim_id,
            topic=debate.topic,
            trigger_type=debate.trigger_type,
            status=debate.status,
            target_type=debate.target_type,
            target_id=debate.target_id,
            context_payload=debate.context_payload,
            rounds=[
                {
                    "round_number": item.round_number,
                    "role": item.role,
                    "position": item.position,
                    "confidence": item.confidence,
                    "arguments": item.arguments,
                    "rebuttals": item.rebuttals,
                    "concessions": item.concessions,
                    "created_at": item.created_at,
                }
                for item in rounds
            ],
            verdict=(
                DebateVerdictRead(
                    debate_id=verdict.debate_id,
                    topic=verdict.topic,
                    trigger_type=verdict.trigger_type,
                    rounds_completed=verdict.rounds_completed,
                    verdict=verdict.verdict,
                    confidence=verdict.confidence,
                    winning_arguments=verdict.winning_arguments,
                    decisive_evidence=verdict.decisive_evidence,
                    conditions=verdict.conditions,
                    minority_opinion=verdict.minority_opinion,
                    created_at=verdict.created_at,
                )
                if verdict is not None
                else None
            ),
            created_at=debate.created_at,
            updated_at=debate.updated_at,
        )

    async def list_run_debates(self, session: AsyncSession, run_id: str) -> list[DebateSummaryRead]:
        sessions = list(
            (
                await session.scalars(
                    select(DebateSessionRecord)
                    .where(DebateSessionRecord.run_id == run_id)
                    .order_by(DebateSessionRecord.created_at.desc())
                )
            ).all()
        )
        verdicts = await self._load_verdicts(session, [item.id for item in sessions])
        return [
            DebateSummaryRead(
                debate_id=item.id,
                topic=item.topic,
                trigger_type=item.trigger_type,
                verdict=verdicts.get(item.id).verdict if item.id in verdicts else None,
                confidence=verdicts.get(item.id).confidence if item.id in verdicts else None,
                created_at=item.created_at,
            )
            for item in sessions
        ]

    async def _load_verdicts(
        self,
        session: AsyncSession,
        debate_ids: list[str],
    ) -> dict[str, DebateVerdictRecord]:
        if not debate_ids:
            return {}
        return {
            item.debate_id: item
            for item in (
                await session.scalars(
                    select(DebateVerdictRecord).where(DebateVerdictRecord.debate_id.in_(debate_ids))
                )
            ).all()
        }

    async def _llm_debate_rounds(
        self,
        topic: str,
        trigger_type: str,
        context: str,
        evidence_ids: list[str],
    ) -> list[dict[str, Any]] | None:
        if self.openai_service is None:
            return None
        if not any(
            self.openai_service.is_configured(target)
            for target in [
                "debate_advocate",
                "debate_challenger",
                "debate_arbitrator",
                "primary",
                "extraction",
                "report",
            ]
        ):
            return None

        advocate_r1 = await self.openai_service.generate_debate_position(
            role="advocate",
            topic=topic,
            trigger_type=trigger_type,
            context=context,
            target=self._debate_target_for_role("advocate"),
        )
        challenger_r1 = await self.openai_service.generate_debate_position(
            role="challenger",
            topic=topic,
            trigger_type=trigger_type,
            context=context,
            target=self._debate_target_for_role("challenger"),
        )
        if advocate_r1 is None and challenger_r1 is None:
            return None

        adv_args_r1 = advocate_r1.arguments if advocate_r1 else []
        chal_args_r1 = challenger_r1.arguments if challenger_r1 else []
        rounds: list[dict[str, Any]] = []

        if advocate_r1 is not None:
            rounds.append({
                "round_number": 1,
                "role": "advocate",
                "position": advocate_r1.position,
                "confidence": advocate_r1.confidence,
                "arguments": [
                    {"claim": a.claim, "evidence_ids": a.evidence_ids or evidence_ids[:3],
                     "reasoning": a.reasoning, "strength": a.strength}
                    for a in adv_args_r1
                ],
                "rebuttals": [],
                "concessions": [],
            })
        if challenger_r1 is not None:
            rounds.append({
                "round_number": 1,
                "role": "challenger",
                "position": challenger_r1.position,
                "confidence": challenger_r1.confidence,
                "arguments": [
                    {"claim": a.claim, "evidence_ids": a.evidence_ids or evidence_ids[:3],
                     "reasoning": a.reasoning, "strength": a.strength}
                    for a in chal_args_r1
                ],
                "rebuttals": [],
                "concessions": [],
            })

        advocate_r2 = await self.openai_service.generate_debate_position(
            role="advocate",
            topic=topic,
            trigger_type=trigger_type,
            context=context,
            opponent_arguments=[{"claim": a.claim, "reasoning": a.reasoning} for a in chal_args_r1],
            own_previous=[{"claim": a.claim} for a in adv_args_r1],
            target=self._debate_target_for_role("advocate"),
        )
        challenger_r2 = await self.openai_service.generate_debate_position(
            role="challenger",
            topic=topic,
            trigger_type=trigger_type,
            context=context,
            opponent_arguments=[{"claim": a.claim, "reasoning": a.reasoning} for a in adv_args_r1],
            own_previous=[{"claim": a.claim} for a in chal_args_r1],
            target=self._debate_target_for_role("challenger"),
        )

        if advocate_r2 is not None:
            rounds.append({
                "round_number": 2,
                "role": "advocate",
                "position": advocate_r2.position,
                "confidence": advocate_r2.confidence,
                "arguments": [
                    {"claim": a.claim, "evidence_ids": a.evidence_ids or evidence_ids[:3],
                     "reasoning": a.reasoning, "strength": a.strength}
                    for a in advocate_r2.arguments
                ],
                "rebuttals": advocate_r2.rebuttals or [],
                "concessions": advocate_r2.concessions or [],
            })
        if challenger_r2 is not None:
            rounds.append({
                "round_number": 2,
                "role": "challenger",
                "position": challenger_r2.position,
                "confidence": challenger_r2.confidence,
                "arguments": [
                    {"claim": a.claim, "evidence_ids": a.evidence_ids or evidence_ids[:3],
                     "reasoning": a.reasoning, "strength": a.strength}
                    for a in challenger_r2.arguments
                ],
                "rebuttals": challenger_r2.rebuttals or [],
                "concessions": challenger_r2.concessions or [],
            })

        all_adv_args = adv_args_r1 + (advocate_r2.arguments if advocate_r2 else [])
        all_chal_args = chal_args_r1 + (challenger_r2.arguments if challenger_r2 else [])
        arbitrator = await self.openai_service.generate_debate_position(
            role="arbitrator",
            topic=topic,
            trigger_type=trigger_type,
            context=context,
            opponent_arguments=[{"claim": a.claim, "reasoning": a.reasoning} for a in all_adv_args + all_chal_args],
            target=self._debate_target_for_role("arbitrator"),
        )
        if arbitrator is not None:
            rounds.append({
                "round_number": 3,
                "role": "arbitrator",
                "position": arbitrator.position,
                "confidence": arbitrator.confidence,
                "arguments": [
                    {"claim": a.claim, "evidence_ids": a.evidence_ids or evidence_ids[:3],
                     "reasoning": a.reasoning, "strength": a.strength}
                    for a in arbitrator.arguments
                ],
                "rebuttals": arbitrator.rebuttals or [],
                "concessions": arbitrator.concessions or [],
            })

        return rounds if rounds else None

    def _debate_target_for_role(self, role: str) -> str:
        if self.openai_service is None:
            return "primary"
        role_targets = {
            "advocate": ("debate_advocate", "primary"),
            "challenger": ("debate_challenger", "extraction", "primary"),
            "arbitrator": ("debate_arbitrator", "report", "primary"),
        }
        for target in role_targets.get(role, ("primary",)):
            if self.openai_service.is_configured(target):
                return target
        return "primary"

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
        advocate_rounds = [r for r in rounds if r["role"] == "advocate"]
        challenger_rounds = [r for r in rounds if r["role"] == "challenger"]
        arbitrator_rounds = [r for r in rounds if r["role"] == "arbitrator"]

        support_confidence = max(
            (r["confidence"] for r in advocate_rounds), default=0.5,
        )
        challenge_confidence = max(
            (r["confidence"] for r in challenger_rounds), default=0.5,
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
                conditions = [c.get("reason", "Condition attached by arbitrator.") for c in arb_concessions] or [
                    "The LLM arbitrator issued a conditional verdict."
                ]
            else:
                conditions = ["Retain the current conclusion, but keep analyst review attached to the next report cycle."]

        context_payload: dict[str, Any] = {"debate_method": "llm", "user_context": payload.context_lines}
        if run_id is not None:
            context_payload.update({
                "run_id": run_id,
                "report_id": report_id,
                "latest_decision_id": latest_decision_id,
                "final_state": final_state or {},
                "evidence_statements": evidence_statements or [],
            })
        if claim_id is not None:
            context_payload.update({
                "claim_statement": claim_statement,
                "claim_confidence": claim_confidence,
            })

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
            metric_score = self._branch_metric_score(branch_run.domain_id, metric, baseline_end, scenario_end)
            net_branch_score += metric_score
            if metric_score > 0.08:
                positives.append(self._branch_metric_summary(metric, baseline_end, scenario_end, better=True))
            elif metric_score < -0.08:
                risks.append(self._branch_metric_summary(metric, baseline_end, scenario_end, better=False))

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
            0.44 + (0.12 * len(risks)) + max(-net_branch_score, 0.0) * 0.08 - (0.04 * len(positives)),
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
            conditions = ["Keep the branch visible in compare view until the next evidence refresh resolves the tradeoffs."]

        winning_arguments = (positives or ["The branch presents a plausible alternative action path."])[:3]
        minority_opinion = (risks or ["The branch does not clearly dominate the baseline outcome."])[0]
        subject_name = await self._run_subject_name(session, branch_run)

        rounds = [
            {
                "round_number": 1,
                "role": "advocate",
                "position": "SUPPORT",
                "confidence": support_confidence,
                "arguments": [
                    {
                        "claim": argument,
                        "evidence_ids": evidence_ids[:3],
                        "reasoning": f"The branch for {subject_name} improves part of the scenario surface versus baseline.",
                        "strength": "STRONG" if index == 0 else "MODERATE",
                    }
                    for index, argument in enumerate(winning_arguments)
                ],
                "rebuttals": [],
                "concessions": [],
            },
            {
                "round_number": 1,
                "role": "challenger",
                "position": "OPPOSE" if verdict == "REJECTED" else "CONDITIONAL",
                "confidence": challenge_confidence,
                "arguments": [
                    {
                        "claim": argument,
                        "evidence_ids": evidence_ids[:3],
                        "reasoning": "The alternative branch still carries meaningful tradeoffs against the baseline.",
                        "strength": "STRONG" if index == 0 else "MODERATE",
                    }
                    for index, argument in enumerate((risks or ["The branch does not yet beat baseline on the highest-value metrics."])[:3])
                ],
                "rebuttals": [],
                "concessions": [],
            },
            {
                "round_number": 2,
                "role": "arbitrator",
                "position": self._verdict_position(verdict),
                "confidence": max(support_confidence, challenge_confidence),
                "arguments": [
                    {
                        "claim": f"Final verdict: {verdict}.",
                        "evidence_ids": evidence_ids[:3],
                        "reasoning": "The arbitrator compared branch KPI deltas, recommendations, and unresolved downside tradeoffs.",
                        "strength": "STRONG",
                    }
                ],
                "rebuttals": [],
                "concessions": ([{"argument_idx": 0, "reason": conditions[0]}] if conditions else []),
            },
        ]

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
        decisive_evidence_pre = list(dict.fromkeys([
            claim.evidence_item_id,
            *[item.evidence_item_id for item in relations.supportive_claims[:2]],
            *[item.evidence_item_id for item in relations.conflicting_claims[:2]],
        ]))
        context_parts = [
            f"Claim: {claim.statement}",
            f"Claim confidence: {claim.confidence}",
            f"Evidence title: {evidence.title if evidence is not None else 'unknown'}",
            f"Supporting claims: {len(relations.supportive_claims)}",
            f"Conflicting claims: {len(relations.conflicting_claims)}",
        ]
        if relations.supportive_claims:
            context_parts.append(f"Strongest support: {relations.supportive_claims[0].statement[:200]}")
        if relations.conflicting_claims:
            context_parts.append(f"Strongest conflict: {relations.conflicting_claims[0].statement[:200]}")
        llm_context = "\n".join(context_parts)
        llm_rounds = await self._llm_debate_rounds(
            topic=payload.topic,
            trigger_type=payload.trigger_type,
            context=llm_context,
            evidence_ids=decisive_evidence_pre,
        )
        if llm_rounds is not None:
            return self._build_assessment_from_llm_rounds(
                llm_rounds, decisive_evidence_pre, payload,
                claim_id=claim.id,
                claim_statement=claim.statement,
                claim_confidence=float(claim.confidence),
            )

        # Fallback: heuristic debate
        strongest_support = relations.supportive_claims[0] if relations.supportive_claims else None
        strongest_conflict = relations.conflicting_claims[0] if relations.conflicting_claims else None
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
        rounds = [
            {
                "round_number": 1,
                "role": "advocate",
                "position": "SUPPORT",
                "confidence": support_confidence,
                "arguments": self._claim_argument_block(
                    primary_claim=claim,
                    related_claims=relations.supportive_claims,
                    default_reasoning="The statement is directly grounded in the linked evidence item.",
                    confidence=support_confidence,
                ),
                "rebuttals": [],
                "concessions": [],
            },
            {
                "round_number": 1,
                "role": "challenger",
                "position": "OPPOSE" if verdict != "ACCEPTED" else "CONDITIONAL",
                "confidence": challenge_confidence,
                "arguments": self._claim_argument_block(
                    primary_claim=claim,
                    related_claims=relations.conflicting_claims,
                    default_reasoning="The confidence band alone does not establish that this claim wins against the conflict set.",
                    confidence=challenge_confidence,
                    opposing=True,
                ),
                "rebuttals": [],
                "concessions": [],
            },
            {
                "round_number": 2,
                "role": "arbitrator",
                "position": self._verdict_position(verdict),
                "confidence": max(support_confidence, challenge_confidence),
                "arguments": [
                    {
                        "claim": f"Final verdict: {verdict}.",
                        "evidence_ids": decisive_evidence,
                        "reasoning": f"Evidence title: {evidence.title if evidence is not None else 'unknown'}.",
                        "strength": "STRONG",
                    }
                ],
                "rebuttals": [],
                "concessions": [],
            },
        ]
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
        final_state = {key: float(value) for key, value in run.summary.get("final_state", {}).items()}
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
        if report is not None:
            context_parts.append(f"Report summary: {report.summary[:500]}")
        llm_context = "\n".join(context_parts)
        llm_rounds = await self._llm_debate_rounds(
            topic=payload.topic,
            trigger_type=payload.trigger_type,
            context=llm_context,
            evidence_ids=evidence_ids[:5],
        )
        if llm_rounds is not None:
            return self._build_assessment_from_llm_rounds(
                llm_rounds, evidence_ids, payload, run_id=run.id,
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
            conditions = ["Retain the current conclusion, but keep analyst review attached to the next report cycle."]

        winning_arguments = (positives or ["The baseline decision sequence remained coherent."])[:3]
        decisive_evidence = evidence_ids[:3]
        minority_opinion = (risks or ["The challenger found limited contradictory evidence."])[0]

        subject_name = await self._run_subject_name(session, run)
        rounds = [
            {
                "round_number": 1,
                "role": "advocate",
                "position": "SUPPORT",
                "confidence": support_confidence,
                "arguments": [
                    {
                        "claim": argument,
                        "evidence_ids": decisive_evidence,
                        "reasoning": f"The run for {subject_name} closed with supportive signals in the final state.",
                        "strength": "STRONG" if index == 0 else "MODERATE",
                    }
                    for index, argument in enumerate((positives or ["The run maintained a coherent action path."])[:3])
                ],
                "rebuttals": [],
                "concessions": [],
            },
            {
                "round_number": 1,
                "role": "challenger",
                "position": "OPPOSE" if verdict == "REJECTED" else "CONDITIONAL",
                "confidence": challenge_confidence,
                "arguments": [
                    {
                        "claim": argument,
                        "evidence_ids": decisive_evidence,
                        "reasoning": "Residual operational risk prevents a clean endorsement.",
                        "strength": "STRONG" if index == 0 else "MODERATE",
                    }
                    for index, argument in enumerate((risks or ["Contradictory signals were limited but not zero."])[:3])
                ],
                "rebuttals": [],
                "concessions": [],
            },
            {
                "round_number": 2,
                "role": "advocate",
                "position": "SUPPORT",
                "confidence": self._clamp(support_confidence - 0.03, minimum=0.2, maximum=0.92),
                "arguments": [
                    {
                        "claim": "The supportive indicators still outweigh the unresolved risks.",
                        "evidence_ids": decisive_evidence,
                        "reasoning": "The matched rules and completed actions show a consistent execution path.",
                        "strength": "MODERATE",
                    }
                ],
                "rebuttals": [{"target_argument_idx": 0, "counter": minority_opinion, "evidence_ids": decisive_evidence}],
                "concessions": [],
            },
            {
                "round_number": 2,
                "role": "challenger",
                "position": "OPPOSE" if verdict == "REJECTED" else "CONDITIONAL",
                "confidence": self._clamp(challenge_confidence - 0.03, minimum=0.15, maximum=0.9),
                "arguments": [
                    {
                        "claim": "The downside case still remains operationally relevant.",
                        "evidence_ids": decisive_evidence,
                        "reasoning": "Open risk factors should remain visible in the final recommendation.",
                        "strength": "MODERATE",
                    }
                ],
                "rebuttals": [{"target_argument_idx": 0, "counter": winning_arguments[0], "evidence_ids": decisive_evidence}],
                "concessions": [],
            },
            {
                "round_number": 3,
                "role": "arbitrator",
                "position": self._verdict_position(verdict),
                "confidence": max(support_confidence, challenge_confidence),
                "arguments": [
                    {
                        "claim": f"Final verdict: {verdict}.",
                        "evidence_ids": decisive_evidence,
                        "reasoning": "The arbitrator weighted final-state metrics, matched rules, and unresolved shocks.",
                        "strength": "STRONG",
                    }
                ],
                "rebuttals": [],
                "concessions": (
                    [{"argument_idx": 0, "reason": conditions[0]}] if conditions else []
                ),
            },
        ]

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
                        Claim.status.in_([ClaimStatus.ACCEPTED.value, ClaimStatus.PENDING_REVIEW.value]),
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
            similarity = self._claim_similarity(base_tokens, self._claim_tokens(candidate.statement))
            similarity_threshold = (
                0.2
                if normalize_text(candidate.subject).lower() == normalize_text(claim.subject).lower()
                else 0.3
            )
            if similarity < similarity_threshold:
                continue
            candidate_direction = self._claim_direction(candidate.statement)
            if base_direction != 0 and candidate_direction != 0 and base_direction != candidate_direction:
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
                    "strength": "STRONG" if lead.status == ClaimStatus.ACCEPTED.value else "MODERATE",
                }
            ]
        return [
            {
                "claim": primary_claim.statement if not opposing else "The current claim still faces unresolved conflict risk.",
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
        return round(max(minimum, min(maximum, float(value))), 2)
