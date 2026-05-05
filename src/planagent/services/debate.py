from __future__ import annotations

from collections.abc import AsyncIterator
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
from planagent.services.openai_client import DebatePositionPayload, OpenAIService
from planagent.services.pipeline import normalize_text
from planagent.services.providers import AnthropicProvider

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
    recommendations: list[dict[str, Any]]
    risk_factors: list[str]
    alternative_scenarios: list[dict[str, Any]]
    conclusion_summary: str


@dataclass(frozen=True)
class DebateStreamEvent:
    event: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class DebateStreamPreparation:
    context: str
    llm_evidence_ids: list[str]
    assessment_evidence_ids: list[str]
    assessment_kwargs: dict[str, Any]


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
        agent_registry: object | None = None,
    ) -> None:
        self.settings = settings
        self.event_bus = event_bus
        self.openai_service = openai_service
        self.agent_registry = agent_registry

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
            recommendations=assessment.recommendations,
            risk_factors=assessment.risk_factors,
            alternative_scenarios=assessment.alternative_scenarios,
            conclusion_summary=assessment.conclusion_summary,
        )
        session.add(verdict)

        if payload.trigger_type in ("pivot_decision", "auto_conflict_detection") and payload.run_id is not None:
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

    async def stream_debate(
        self,
        session: AsyncSession,
        payload: DebateTriggerRequest,
    ) -> AsyncIterator[DebateStreamEvent]:
        payload = await self._resolve_trigger_payload(session, payload)
        if payload.run_id is None and payload.claim_id is None:
            raise ValueError("Debate trigger requires run_id or claim_id.")

        run = await session.get(SimulationRun, payload.run_id) if payload.run_id is not None else None
        claim = await session.get(Claim, payload.claim_id) if payload.claim_id is not None else None
        debate_session = DebateSessionRecord(
            run_id=payload.run_id,
            claim_id=payload.claim_id,
            tenant_id=(claim.tenant_id if claim is not None else None) or (run.tenant_id if run is not None else None),
            preset_id=(claim.preset_id if claim is not None else None) or (run.preset_id if run is not None else None),
            topic=payload.topic,
            trigger_type=payload.trigger_type,
            status="RUNNING",
            target_type=payload.target_type,
            target_id=payload.target_id or payload.claim_id or payload.run_id,
            context_payload={"user_context": payload.context_lines},
        )
        trigger_payload: dict[str, Any]
        debate_id: str

        try:
            async with session.begin_nested():
                session.add(debate_session)
                await session.flush()
                debate_id = debate_session.id
                trigger_payload = {
                    "debate_id": debate_id,
                    "run_id": payload.run_id,
                    "claim_id": payload.claim_id,
                    "topic": payload.topic,
                    "trigger_type": payload.trigger_type,
                }
                session.add(EventArchive(topic=EventTopic.DEBATE_TRIGGERED.value, payload=trigger_payload))
                await session.flush()

            preparation = await self._prepare_stream_llm_debate(session, payload)
            if preparation is not None and self._has_available_debate_provider():
                rounds = []
                async for stream_event in self._stream_llm_rounds(
                    topic=payload.topic,
                    trigger_type=payload.trigger_type,
                    context=preparation.context,
                    evidence_ids=preparation.llm_evidence_ids,
                ):
                    if stream_event.event == "debate_round_start":
                        yield self._stream_event(stream_event.event, debate_id, stream_event.payload)
                        continue
                    round_payload = stream_event.payload["round"]
                    rounds.append(round_payload)
                    await self._persist_stream_round(session, debate_id, round_payload)
                    yield self._stream_event(
                        "debate_round_complete",
                        debate_id,
                        self._round_complete_payload(round_payload),
                    )
                assessment = self._build_assessment_from_llm_rounds(
                    rounds,
                    preparation.assessment_evidence_ids,
                    payload,
                    **preparation.assessment_kwargs,
                )
            else:
                assessment = await self._assess_debate(session, payload)
                rounds = []
                for round_payload in assessment.rounds:
                    rounds.append(round_payload)
                    yield self._stream_event(
                        "debate_round_start",
                        debate_id,
                        {
                            "round_number": round_payload["round_number"],
                            "role": round_payload["role"],
                        },
                    )
                    await self._persist_stream_round(session, debate_id, round_payload)
                    yield self._stream_event(
                        "debate_round_complete",
                        debate_id,
                        self._round_complete_payload(round_payload),
                    )

            verdict = DebateVerdictRecord(
                debate_id=debate_id,
                topic=payload.topic,
                trigger_type=payload.trigger_type,
                rounds_completed=max(round_data["round_number"] for round_data in assessment.rounds),
                verdict=assessment.verdict,
                confidence=max(assessment.support_confidence, assessment.challenge_confidence),
                winning_arguments=assessment.winning_arguments,
                decisive_evidence=assessment.decisive_evidence,
                conditions=assessment.conditions,
                minority_opinion=assessment.minority_opinion,
                recommendations=assessment.recommendations,
                risk_factors=assessment.risk_factors,
                alternative_scenarios=assessment.alternative_scenarios,
                conclusion_summary=assessment.conclusion_summary,
            )
            async with session.begin_nested():
                debate_session.status = "COMPLETED"
                debate_session.context_payload = assessment.context_payload
                session.add(verdict)

                if payload.trigger_type in ("pivot_decision", "auto_conflict_detection") and payload.run_id is not None:
                    latest_decision = (
                        await session.scalars(
                            select(DecisionRecordRecord)
                            .where(DecisionRecordRecord.run_id == payload.run_id)
                            .order_by(DecisionRecordRecord.tick.desc(), DecisionRecordRecord.sequence.desc())
                            .limit(1)
                        )
                    ).first()
                    if latest_decision is not None:
                        latest_decision.debate_verdict_id = debate_id
                    if run is not None:
                        run.summary = {
                            **(run.summary or {}),
                            "latest_debate_id": debate_id,
                            "latest_debate_verdict": assessment.verdict,
                            "debate_disagreements": [assessment.minority_opinion] if assessment.minority_opinion else [],
                        }
                        await self._ensure_debate_prediction(session, run, verdict, latest_decision)

                completed_payload = {
                    "debate_id": debate_id,
                    "run_id": payload.run_id,
                    "claim_id": payload.claim_id,
                    "verdict": assessment.verdict,
                    "confidence": verdict.confidence,
                }
                session.add(EventArchive(topic=EventTopic.DEBATE_COMPLETED.value, payload=completed_payload))
                await session.flush()

            await session.commit()
            await self.event_bus.publish(EventTopic.DEBATE_TRIGGERED.value, trigger_payload)
            await self.event_bus.publish(EventTopic.DEBATE_COMPLETED.value, completed_payload)
            yield self._stream_event(
                "debate_verdict",
                debate_id,
                {
                    "verdict": assessment.verdict,
                    "confidence": completed_payload["confidence"],
                    "winning_arguments": assessment.winning_arguments,
                    "decisive_evidence": assessment.decisive_evidence,
                },
            )
        except Exception:
            await session.rollback()
            raise

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
                    recommendations=verdict.recommendations or [],
                    risk_factors=verdict.risk_factors or [],
                    alternative_scenarios=verdict.alternative_scenarios or [],
                    conclusion_summary=verdict.conclusion_summary,
                    created_at=verdict.created_at,
                )
                if verdict is not None
                else None
            ),
            created_at=debate.created_at,
            updated_at=debate.updated_at,
        )

    async def list_all_debates(self, session: AsyncSession, limit: int = 50) -> list[DebateSummaryRead]:
        """List all debates across all runs, newest first."""
        sessions = list(
            (
                await session.scalars(
                    select(DebateSessionRecord)
                    .order_by(DebateSessionRecord.created_at.desc())
                    .limit(limit)
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
                recommendation_count=len(verdicts.get(item.id).recommendations or []) if item.id in verdicts else 0,
                created_at=item.created_at,
            )
            for item in sessions
        ]

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
                recommendation_count=len(verdicts.get(item.id).recommendations or []) if item.id in verdicts else 0,
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

    async def _prepare_stream_llm_debate(
        self,
        session: AsyncSession,
        payload: DebateTriggerRequest,
    ) -> DebateStreamPreparation | None:
        if payload.claim_id is not None:
            claim = await session.get(Claim, payload.claim_id)
            if claim is None:
                raise LookupError(f"Claim {payload.claim_id} was not found.")
            evidence = await session.get(EvidenceItem, claim.evidence_item_id)
            relations = await self.find_claim_relations(session, claim)
            decisive_evidence = list(dict.fromkeys([
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
            if payload.context_lines:
                context_parts.append("Trigger context:\n" + "\n".join(payload.context_lines))
            if relations.supportive_claims:
                context_parts.append(f"Strongest support: {relations.supportive_claims[0].statement[:200]}")
            if relations.conflicting_claims:
                context_parts.append(f"Strongest conflict: {relations.conflicting_claims[0].statement[:200]}")
            return DebateStreamPreparation(
                context="\n".join(context_parts),
                llm_evidence_ids=decisive_evidence,
                assessment_evidence_ids=decisive_evidence,
                assessment_kwargs={
                    "claim_id": claim.id,
                    "claim_statement": claim.statement,
                    "claim_confidence": float(claim.confidence),
                },
            )

        if payload.target_type == "branch":
            return None

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
        context_parts = [
            f"Domain: {run.domain_id}",
            f"Subject: {subject_name}",
            f"Final state: {final_state}",
            f"Matched rules: {matched_rules[:5]}",
            f"Shocks: {[shock.shock_type for shock in shocks[:5]]}",
        ] + [f"Evidence: {statement}" for statement in evidence_statements[:3]]
        if payload.context_lines:
            context_parts.append("Trigger context:\n" + "\n".join(payload.context_lines))
        if report is not None:
            context_parts.append(f"Report summary: {report.summary[:500]}")
        return DebateStreamPreparation(
            context="\n".join(context_parts),
            llm_evidence_ids=evidence_ids[:5],
            assessment_evidence_ids=evidence_ids,
            assessment_kwargs={
                "run_id": run.id,
                "report_id": report.id if report is not None else None,
                "latest_decision_id": latest_decision.id if latest_decision is not None else None,
                "final_state": final_state,
                "evidence_statements": evidence_statements[:3],
            },
        )

    async def _stream_llm_rounds(
        self,
        *,
        topic: str,
        trigger_type: str,
        context: str,
        evidence_ids: list[str],
    ) -> AsyncIterator[DebateStreamEvent]:
        completed_rounds: list[dict[str, Any]] = []

        def argument_refs(rounds: list[dict[str, Any]]) -> list[dict[str, str]]:
            return [
                {"claim": str(argument.get("claim", "")), "reasoning": str(argument.get("reasoning", ""))}
                for round_payload in rounds
                for argument in round_payload.get("arguments", [])
            ]

        def own_refs(role: str) -> list[dict[str, str]]:
            return [
                {"claim": str(argument.get("claim", ""))}
                for round_payload in completed_rounds
                if round_payload["role"] == role
                for argument in round_payload.get("arguments", [])
            ]

        def debate_history() -> str:
            lines: list[str] = []
            for item in completed_rounds:
                lines.append(
                    f"Round {item['round_number']} {item['role']} "
                    f"({item['position']}, confidence {item['confidence']:.2f}):"
                )
                for argument in item.get("arguments", [])[:3]:
                    claim = str(argument.get("claim", ""))[:90]
                    reasoning = str(argument.get("reasoning", ""))[:70]
                    lines.append(f"- {claim} | {reasoning}")
            return "\n".join(lines)

        def context_with_history(instruction: str) -> str:
            return (
                f"{instruction}\n\n"
                f"Debate history so far:\n{debate_history() or 'No prior debate rounds.'}\n\n"
                f"Original context:\n{context}"
            )

        round_plan = [
            # ── Round 1: 立论 ──────────────────────────────────────
            (1, "advocate", "【第1轮·立论】战略支持者：请提出支持该命题的核心证据链和战略逻辑框架。"),
            (1, "intel_analyst", "【第1轮·立论】情报分析师：请提供情报支撑，评估关键信息的可靠性和情报盲区。"),
            (1, "geo_expert", "【第1轮·立论】地缘政治专家：请从地理、联盟体系和国际秩序维度分析命题的可行性。"),
            (1, "econ_analyst", "【第1轮·立论】经济分析师：请评估命题的宏观经济影响、成本收益和经济约束。"),
            (1, "military_strategist", "【第1轮·立论】军事战略家：请从军事力量平衡和作战可行性角度评估命题。"),
            (1, "tech_foresight", "【第1轮·立论】技术前瞻者：请评估相关技术发展趋势及其对命题的影响。"),
            (1, "social_impact", "【第1轮·立论】社会影响评估师：请评估命题的社会维度影响和公众舆论基础。"),
            # ── Round 2: 质询 ──────────────────────────────────────
            (2, "challenger", "【第2轮·质询】风险挑战者：请针对所有立论进行系统性质疑，找出逻辑漏洞和证据缺陷。"),
            (2, "intel_analyst", "【第2轮·质询】情报分析师：请对立论中的事实声明进行情报核实，标注矛盾信息和来源可信度。"),
            # ── Round 3: 修订 ──────────────────────────────────────
            (3, "advocate", "【第3轮·修订】战略支持者：请根据质询反馈修订和完善你的核心论证。"),
            (3, "geo_expert", "【第3轮·修订】地缘政治专家：请根据质询修订地缘政治分析，补充被质疑的论据。"),
            (3, "econ_analyst", "【第3轮·修订】经济分析师：请根据质询修订经济分析，修正数据和结论。"),
            (3, "military_strategist", "【第3轮·修订】军事战略家：请根据质询修订军事评估，强化或修正关键判断。"),
            (3, "tech_foresight", "【第3轮·修订】技术前瞻者：请根据质询修订技术评估，更新时间线和置信度。"),
            (3, "social_impact", "【第3轮·修订】社会影响评估师：请根据质询修订社会影响分析。"),
            # ── Round 4: 仲裁 ──────────────────────────────────────
            (4, "arbitrator", "【第4轮·仲裁】首席仲裁官：请基于全部论证历史做出最终裁决，综合权衡各维度分析。"),
        ]

        for round_number, role, instruction in round_plan:
            yield DebateStreamEvent(
                event="debate_round_start",
                payload={"round_number": round_number, "role": role},
            )
            opponent_rounds = [
                item for item in completed_rounds
                if (round_number == 2 and item["round_number"] == 1)  # 质询方看到所有立论
                or (round_number == 3 and item["round_number"] == 2)  # 修订方看到所有质询
                or (role == "arbitrator")  # 仲裁官看到所有历史
            ]
            position = await self._call_llm(
                role=role,
                topic=topic,
                trigger_type=trigger_type,
                context=context_with_history(instruction),
                opponent_arguments=argument_refs(opponent_rounds) if opponent_rounds else None,
                own_previous=own_refs(role) if role != "arbitrator" else None,
            )
            round_payload = (
                self._position_to_round_payload(round_number, role, position, evidence_ids)
                if position is not None
                else self._fallback_stream_round(round_number, role, evidence_ids)
            )
            completed_rounds.append(round_payload)
            yield DebateStreamEvent(event="debate_round_complete", payload={"round": round_payload})

    def _position_to_round_payload(
        self,
        round_number: int,
        role: str,
        position: DebatePositionPayload,
        evidence_ids: list[str],
    ) -> dict[str, Any]:
        return {
            "round_number": round_number,
            "role": role,
            "position": position.position,
            "confidence": position.confidence,
            "arguments": [
                {
                    "claim": argument.claim,
                    "evidence_ids": argument.evidence_ids or evidence_ids[:3],
                    "reasoning": argument.reasoning,
                    "strength": argument.strength,
                }
                for argument in position.arguments
            ],
            "rebuttals": position.rebuttals or [],
            "concessions": position.concessions or [],
        }

    def _fallback_stream_round(
        self,
        round_number: int,
        role: str,
        evidence_ids: list[str],
    ) -> dict[str, Any]:
        position = "OPPOSE" if role == "challenger" else "CONDITIONAL"
        if role == "advocate" and round_number == 1:
            position = "SUPPORT"
        return {
            "round_number": round_number,
            "role": role,
            "position": position,
            "confidence": 0.5,
            "arguments": [
                {
                    "claim": f"{role} did not return a structured debate payload.",
                    "evidence_ids": evidence_ids[:3],
                    "reasoning": "The stream preserved the debate sequence with a neutral fallback round.",
                    "strength": "WEAK",
                }
            ],
            "rebuttals": [],
            "concessions": [],
        }

    async def _persist_stream_round(
        self,
        session: AsyncSession,
        debate_id: str,
        round_payload: dict[str, Any],
    ) -> None:
        async with session.begin_nested():
            session.add(
                DebateRoundRecord(
                    debate_id=debate_id,
                    round_number=round_payload["round_number"],
                    role=round_payload["role"],
                    position=round_payload["position"],
                    confidence=round_payload["confidence"],
                    arguments=round_payload["arguments"],
                    rebuttals=round_payload["rebuttals"],
                    concessions=round_payload["concessions"],
                )
            )
            await session.flush()

    def _round_complete_payload(self, round_payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "round_number": round_payload["round_number"],
            "role": round_payload["role"],
            "position": round_payload["position"],
            "confidence": round_payload["confidence"],
            "key_arguments": self._round_key_arguments(round_payload),
        }

    def _round_key_arguments(self, round_payload: dict[str, Any]) -> list[str]:
        return [
            str(argument.get("claim", ""))
            for argument in round_payload.get("arguments", [])[:3]
            if argument.get("claim")
        ]

    def _stream_event(self, event: str, debate_id: str, payload: dict[str, Any]) -> DebateStreamEvent:
        return DebateStreamEvent(event=event, payload={"debate_id": debate_id, **payload})

    async def _llm_debate_rounds(
        self,
        topic: str,
        trigger_type: str,
        context: str,
        evidence_ids: list[str],
    ) -> list[dict[str, Any]] | None:
        if not self._has_available_debate_provider():
            return None

        def argument_dicts(arguments: list[Any]) -> list[dict[str, Any]]:
            return [
                {
                    "claim": argument.claim,
                    "evidence_ids": argument.evidence_ids or evidence_ids[:3],
                    "reasoning": argument.reasoning,
                    "strength": argument.strength,
                }
                for argument in arguments
            ]

        def argument_refs(arguments: list[Any]) -> list[dict[str, str]]:
            return [
                {"claim": argument.claim, "reasoning": argument.reasoning}
                for argument in arguments
            ]

        def round_payload(round_number: int, role: str, position: Any) -> dict[str, Any]:
            return {
                "round_number": round_number,
                "role": role,
                "position": position.position,
                "confidence": position.confidence,
                "arguments": argument_dicts(position.arguments),
                "rebuttals": position.rebuttals or [],
                "concessions": position.concessions or [],
            }

        def debate_history(completed_rounds: list[dict[str, Any]]) -> str:
            lines: list[str] = []
            for item in completed_rounds:
                lines.append(
                    f"Round {item['round_number']} {item['role']} "
                    f"({item['position']}, confidence {item['confidence']:.2f}):"
                )
                for argument in item.get("arguments", [])[:3]:
                    claim = str(argument.get("claim", ""))[:90]
                    reasoning = str(argument.get("reasoning", ""))[:70]
                    lines.append(f"- {claim} | {reasoning}")
                for rebuttal in item.get("rebuttals", [])[:2]:
                    lines.append(f"- rebuttal: {str(rebuttal)[:90]}")
                for concession in item.get("concessions", [])[:2]:
                    lines.append(f"- concession: {str(concession)[:90]}")
            return "\n".join(lines)

        def context_with_history(instruction: str, completed_rounds: list[dict[str, Any]]) -> str:
            history = debate_history(completed_rounds)
            return (
                f"{instruction}\n\n"
                f"Debate history so far:\n{history or 'No prior debate rounds.'}\n\n"
                f"Original context:\n{context}"
            )

        # ── Round 1: 立论 ──────────────────────────────────────
        advocate_r1 = await self._call_llm(
            role="advocate",
            topic=topic,
            trigger_type=trigger_type,
            context=context,
        )
        intel_r1 = await self._call_llm(
            role="intel_analyst",
            topic=topic,
            trigger_type=trigger_type,
            context=context,
        )
        geo_r1 = await self._call_llm(
            role="geo_expert",
            topic=topic,
            trigger_type=trigger_type,
            context=context,
        )
        econ_r1 = await self._call_llm(
            role="econ_analyst",
            topic=topic,
            trigger_type=trigger_type,
            context=context,
        )
        military_r1 = await self._call_llm(
            role="military_strategist",
            topic=topic,
            trigger_type=trigger_type,
            context=context,
        )
        tech_r1 = await self._call_llm(
            role="tech_foresight",
            topic=topic,
            trigger_type=trigger_type,
            context=context,
        )
        social_r1 = await self._call_llm(
            role="social_impact",
            topic=topic,
            trigger_type=trigger_type,
            context=context,
        )
        challenger_r1 = await self._call_llm(
            role="challenger",
            topic=topic,
            trigger_type=trigger_type,
            context=context,
        )
        if advocate_r1 is None and challenger_r1 is None:
            return None

        rounds: list[dict[str, Any]] = []
        if advocate_r1 is not None:
            rounds.append(round_payload(1, "advocate", advocate_r1))
        if intel_r1 is not None:
            rounds.append(round_payload(1, "intel_analyst", intel_r1))
        if geo_r1 is not None:
            rounds.append(round_payload(1, "geo_expert", geo_r1))
        if econ_r1 is not None:
            rounds.append(round_payload(1, "econ_analyst", econ_r1))
        if military_r1 is not None:
            rounds.append(round_payload(1, "military_strategist", military_r1))
        if tech_r1 is not None:
            rounds.append(round_payload(1, "tech_foresight", tech_r1))
        if social_r1 is not None:
            rounds.append(round_payload(1, "social_impact", social_r1))
        if challenger_r1 is not None:
            rounds.append(round_payload(1, "challenger", challenger_r1))

        # ── Round 2: 质询 ──────────────────────────────────────
        all_r1_args = [
            a for p in [advocate_r1, intel_r1, geo_r1, econ_r1, military_r1, tech_r1, social_r1]
            if p is not None for a in p.arguments
        ]
        chal_args_r1 = challenger_r1.arguments if challenger_r1 else []
        round_2_instruction = "【第2轮·质询】请针对第1轮所有立论进行系统性质疑，找出逻辑漏洞和证据缺陷。"
        challenger_r2 = await self._call_llm(
            role="challenger",
            topic=topic,
            trigger_type=trigger_type,
            context=context_with_history(round_2_instruction, rounds),
            opponent_arguments=argument_refs(all_r1_args),
        )
        intel_r2 = await self._call_llm(
            role="intel_analyst",
            topic=topic,
            trigger_type=trigger_type,
            context=context_with_history(
                "【第2轮·质询】情报分析师：请对立论中的事实声明进行情报核实，标注矛盾信息和来源可信度。",
                rounds,
            ),
            opponent_arguments=argument_refs(all_r1_args),
        )

        if challenger_r2 is not None:
            rounds.append(round_payload(2, "challenger", challenger_r2))
        if intel_r2 is not None:
            rounds.append(round_payload(2, "intel_analyst", intel_r2))

        # ── Round 3: 修订 ──────────────────────────────────────
        all_r2_args = [
            a for p in [challenger_r2, intel_r2]
            if p is not None for a in p.arguments
        ]
        adv_args_r1 = advocate_r1.arguments if advocate_r1 else []
        round_3_instruction = "【第3轮·修订】请根据第2轮质询反馈修订和完善你的核心论证，保留有证据支撑的部分，修正被质疑的部分。"
        advocate_r3 = await self._call_llm(
            role="advocate",
            topic=topic,
            trigger_type=trigger_type,
            context=context_with_history(round_3_instruction, rounds),
            opponent_arguments=argument_refs(all_r2_args),
            own_previous=[{"claim": a.claim} for a in adv_args_r1],
        )
        geo_r3 = await self._call_llm(
            role="geo_expert",
            topic=topic,
            trigger_type=trigger_type,
            context=context_with_history(
                "【第3轮·修订】地缘政治专家：请根据质询修订地缘政治分析，补充被质疑的论据。",
                rounds,
            ),
            opponent_arguments=argument_refs(all_r2_args),
        )
        econ_r3 = await self._call_llm(
            role="econ_analyst",
            topic=topic,
            trigger_type=trigger_type,
            context=context_with_history(
                "【第3轮·修订】经济分析师：请根据质询修订经济分析，修正数据和结论。",
                rounds,
            ),
            opponent_arguments=argument_refs(all_r2_args),
        )
        military_r3 = await self._call_llm(
            role="military_strategist",
            topic=topic,
            trigger_type=trigger_type,
            context=context_with_history(
                "【第3轮·修订】军事战略家：请根据质询修订军事评估，强化或修正关键判断。",
                rounds,
            ),
            opponent_arguments=argument_refs(all_r2_args),
        )
        tech_r3 = await self._call_llm(
            role="tech_foresight",
            topic=topic,
            trigger_type=trigger_type,
            context=context_with_history(
                "【第3轮·修订】技术前瞻者：请根据质询修订技术评估，更新时间线和置信度。",
                rounds,
            ),
            opponent_arguments=argument_refs(all_r2_args),
        )
        social_r3 = await self._call_llm(
            role="social_impact",
            topic=topic,
            trigger_type=trigger_type,
            context=context_with_history(
                "【第3轮·修订】社会影响评估师：请根据质询修订社会影响分析。",
                rounds,
            ),
            opponent_arguments=argument_refs(all_r2_args),
        )

        if advocate_r3 is not None:
            rounds.append(round_payload(3, "advocate", advocate_r3))
        if geo_r3 is not None:
            rounds.append(round_payload(3, "geo_expert", geo_r3))
        if econ_r3 is not None:
            rounds.append(round_payload(3, "econ_analyst", econ_r3))
        if military_r3 is not None:
            rounds.append(round_payload(3, "military_strategist", military_r3))
        if tech_r3 is not None:
            rounds.append(round_payload(3, "tech_foresight", tech_r3))
        if social_r3 is not None:
            rounds.append(round_payload(3, "social_impact", social_r3))

        # ── Round 4: 仲裁 ──────────────────────────────────────
        all_round_args = [
            a for p in [
                advocate_r1, intel_r1, geo_r1, econ_r1, military_r1, tech_r1, social_r1,
                challenger_r1, challenger_r2, intel_r2,
                advocate_r3, geo_r3, econ_r3, military_r3, tech_r3, social_r3,
            ]
            if p is not None for a in p.arguments
        ]
        round_4_instruction = (
            "【第4轮·仲裁】首席仲裁官：请基于全部论证历史做出最终裁决，"
            "综合权衡战略、情报、地缘政治、经济、军事、技术和社会各维度的分析。"
        )
        arbitrator = await self._call_llm(
            role="arbitrator",
            topic=topic,
            trigger_type=trigger_type,
            context=context_with_history(round_4_instruction, rounds),
            opponent_arguments=argument_refs(all_round_args),
        )
        if arbitrator is not None:
            rounds.append(round_payload(4, "arbitrator", arbitrator))

        return rounds if rounds else None

    def _has_available_debate_provider(self) -> bool:
        if self._anthropic_is_configured():
            return True
        if self.openai_service is None:
            return False
        return any(
            self.openai_service.is_configured(target)
            for target in [
                "debate_advocate",
                "debate_challenger",
                "debate_arbitrator",
                "primary",
                "extraction",
                "report",
            ]
        )

    async def _call_llm(
        self,
        *,
        role: str,
        topic: str,
        trigger_type: str,
        context: str,
        opponent_arguments: list[dict[str, Any]] | None = None,
        own_previous: list[dict[str, Any]] | None = None,
    ) -> DebatePositionPayload | None:
        # ── 优先使用 Agent Registry ──────────────────────────
        registry_cfg = self._get_agent_registry_config(role)
        if registry_cfg and registry_cfg.get("api_key"):
            result = await self._call_registry_llm(
                role=role,
                topic=topic,
                trigger_type=trigger_type,
                context=context,
                opponent_arguments=opponent_arguments,
                own_previous=own_previous,
                cfg=registry_cfg,
            )
            if result is not None:
                return result

        # ── 回退到原有 settings 逻辑 ────────────────────────
        requested_provider = self._debate_provider_for_role(role)
        provider_order = list(dict.fromkeys([requested_provider, "openai"]))
        for provider_name in provider_order:
            if provider_name == "anthropic":
                result = await self._call_anthropic_llm(
                    role=role,
                    topic=topic,
                    trigger_type=trigger_type,
                    context=context,
                    opponent_arguments=opponent_arguments,
                    own_previous=own_previous,
                )
            elif provider_name == "openai":
                result = await self._call_openai_llm(
                    role=role,
                    topic=topic,
                    trigger_type=trigger_type,
                    context=context,
                    opponent_arguments=opponent_arguments,
                    own_previous=own_previous,
                )
            else:
                result = None
            if result is not None:
                return result
        return None

    async def _call_openai_llm(
        self,
        *,
        role: str,
        topic: str,
        trigger_type: str,
        context: str,
        opponent_arguments: list[dict[str, Any]] | None,
        own_previous: list[dict[str, Any]] | None,
    ) -> DebatePositionPayload | None:
        if self.openai_service is None:
            return None
        target = self._debate_target_for_role(role)
        if not self.openai_service.is_configured(target):
            return None

        prompt = self._build_debate_prompt(
            role=role,
            topic=topic,
            trigger_type=trigger_type,
            context=context,
            opponent_arguments=opponent_arguments,
            own_previous=own_previous,
        )
        if hasattr(self.openai_service, "generate_json_for_target"):
            _, parsed = await self.openai_service.generate_json_for_target(
                target=target,
                system_prompt=self._debate_role_instruction(role),
                user_content=(
                    f"{prompt}\n\n"
                    "Return valid JSON only. "
                    f"Target schema: {DebatePositionPayload.model_json_schema()}"
                ),
                max_tokens=1000,
            )
            position = self._parse_debate_position_payload(parsed)
            if position is not None:
                return position

        return await self.openai_service.generate_debate_position(
            role=role,
            topic=topic,
            trigger_type=trigger_type,
            context=context,
            opponent_arguments=opponent_arguments,
            own_previous=own_previous,
            target=target,
        )

    async def _call_anthropic_llm(
        self,
        *,
        role: str,
        topic: str,
        trigger_type: str,
        context: str,
        opponent_arguments: list[dict[str, Any]] | None,
        own_previous: list[dict[str, Any]] | None,
    ) -> DebatePositionPayload | None:
        if not self._anthropic_is_configured():
            return None
        provider = AnthropicProvider(
            api_key=self.settings.resolved_anthropic_api_key,
            timeout=self.settings.openai_timeout_seconds,
        )
        try:
            prompt = self._build_debate_prompt(
                role=role,
                topic=topic,
                trigger_type=trigger_type,
                context=context,
                opponent_arguments=opponent_arguments,
                own_previous=own_previous,
            )
            _, parsed = await provider.generate_json(
                model=self.settings.anthropic_model,
                system_prompt=self._debate_role_instruction(role),
                user_prompt=prompt,
                schema=DebatePositionPayload.model_json_schema(),
                max_tokens=1000,
                temperature=0.3,
            )
            return self._parse_debate_position_payload(parsed)
        finally:
            await provider.close()

    def _debate_provider_for_role(self, role: str) -> str:
        role_providers = {
            "advocate": self.settings.debate_advocate_provider,
            "strategist": self.settings.debate_advocate_provider,
            "challenger": self.settings.debate_challenger_provider,
            "risk_analyst": self.settings.debate_challenger_provider,
            "arbitrator": self.settings.debate_arbitrator_provider,
            "opportunist": self.settings.debate_arbitrator_provider,
            "intel_analyst": self.settings.debate_challenger_provider,
            "geo_expert": self.settings.debate_advocate_provider,
            "econ_analyst": self.settings.debate_advocate_provider,
            "military_strategist": self.settings.debate_advocate_provider,
            "tech_foresight": self.settings.debate_advocate_provider,
            "social_impact": self.settings.debate_advocate_provider,
        }
        return role_providers.get(role, "openai").strip().lower() or "openai"

    # ── Agent Registry 集成 ──────────────────────────────────

    def _get_agent_registry_config(self, role: str) -> dict[str, str] | None:
        """从 Agent Registry 获取角色的 provider 配置"""
        if self.agent_registry is None:
            return None
        role_map = {
            "advocate": "advocate",
            "strategist": "advocate",
            "challenger": "challenger",
            "risk_analyst": "challenger",
            "arbitrator": "arbitrator",
            "opportunist": "arbitrator",
            "intel_analyst": "challenger",
            "geo_expert": "advocate",
            "econ_analyst": "advocate",
            "military_strategist": "advocate",
            "tech_foresight": "advocate",
            "social_impact": "advocate",
        }
        agent_role = role_map.get(role)
        if agent_role is None:
            return None
        try:
            return self.agent_registry.get_provider_config(agent_role)
        except Exception:
            return None

    async def _call_registry_llm(
        self,
        *,
        role: str,
        topic: str,
        trigger_type: str,
        context: str,
        opponent_arguments: list[dict[str, Any]] | None,
        own_previous: list[dict[str, Any]] | None,
        cfg: dict[str, str],
    ) -> DebatePositionPayload | None:
        """使用 Agent Registry 的配置调用 LLM"""
        provider_type = cfg.get("provider_type", "openai")
        api_key = cfg.get("api_key", "")
        base_url = cfg.get("base_url", "")
        model = cfg.get("model", "")

        if not api_key:
            return None

        prompt = self._build_debate_prompt(
            role=role,
            topic=topic,
            trigger_type=trigger_type,
            context=context,
            opponent_arguments=opponent_arguments,
            own_previous=own_previous,
        )

        if provider_type == "anthropic":
            provider = AnthropicProvider(api_key=api_key, timeout=45.0)
            try:
                _, parsed = await provider.generate_json(
                    model=model or self.settings.anthropic_model,
                    system_prompt=self._debate_role_instruction(role),
                    user_prompt=prompt,
                    schema=DebatePositionPayload.model_json_schema(),
                    max_tokens=1000,
                    temperature=0.3,
                )
                return self._parse_debate_position_payload(parsed)
            finally:
                await provider.close()
        else:
            # OpenAI 兼容
            from openai import AsyncOpenAI

            client = AsyncOpenAI(
                api_key=api_key,
                base_url=base_url or None,
                timeout=45.0,
            )
            try:
                resp = await client.chat.completions.create(
                    model=model or "gpt-4o",
                    messages=[
                        {"role": "system", "content": self._debate_role_instruction(role)},
                        {"role": "user", "content": f"{prompt}\n\nReturn valid JSON only."},
                    ],
                    max_tokens=1000,
                    temperature=0.3,
                    response_format={"type": "json_object"},
                )
                import json

                content = resp.choices[0].message.content or "{}"
                parsed = json.loads(content)
                return self._parse_debate_position_payload(parsed)
            except Exception:
                return None
            finally:
                await client.close()

    def _anthropic_is_configured(self) -> bool:
        return bool(self.settings.resolved_anthropic_api_key)

    def _debate_role_instruction(self, role: str) -> str:
        _HILL_CLIMBING = (
            "\n\n【迭代攀升要求】当你收到前序轮次的质疑或挑战时，你必须："
            "（1）逐条审视自己先前的论点，识别被有效挑战的部分；"
            "（2）保留有充分证据支撑的核心主张，修正或放弃被证伪的子论点；"
            "（3）补充新的证据或推理来强化薄弱环节；"
            "（4）明确标注置信度的变化及原因。"
            "你的目标不是固守初始立场，而是在每一轮交互中让分析更加精确和可靠。"
        )
        _EVIDENCE_CITATION = (
            "\n\n【证据引用规范】每个论点必须附带具体来源：引用具体的报告名称、日期、"
            "数据指标（如GDP增长率、军费开支、部署数量等）、条约编号或历史先例。"
            "禁止使用'据相关报道''一般来说''众所周知'等模糊表述。"
            "如果缺乏直接证据，必须明确标注为'推测性分析'并给出推理链条。"
        )
        _CROSS_DOMAIN = (
            "\n\n【跨域关联要求】你的分析不应局限于本专业领域。主动识别并引用其他维度"
            "的关联因素：经济决策的地缘政治背景、军事行动的经济约束、技术发展的社会影响等。"
            "在论证中明确指出跨域因果链，例如'经济制裁→供应链中断→军事后勤压力'。"
        )

        prompts = {
            # ── 核心辩论角色 ──────────────────────────────────────
            "advocate": (
                "你是【战略支持者🟢】，负责为命题构建系统性的支持论证。"
                "你的思维风格是结构化演绎：从宏观战略框架出发，逐层分解为可验证的子命题。"
                "你擅长识别命题成立的充分条件，并构建多条独立的证据链形成交叉验证。"
                "在论证中采用'战略叙事'手法——将分散的事实编织成连贯的战略逻辑。"
                "始终站在决策者视角，说明该命题为何在战略上是必要且可行的。"
                + _EVIDENCE_CITATION + _CROSS_DOMAIN + _HILL_CLIMBING
            ),
            "challenger": (
                "你是【风险挑战者🔴】，负责系统性地解构命题的支撑论据。"
                "你的思维风格是批判性分析：采用'红队思维'，专门寻找论证中的逻辑漏洞、"
                "证据缺陷和隐含假设。你擅长运用'事前验尸法'——假设命题已经失败，"
                "逆向推导失败的可能路径。对每个论点追问三个层次：证据是否充分？"
                "推理是否严密？结论是否唯一？你的目标不是为反对而反对，而是通过"
                "严格的压力测试暴露命题的真实脆弱性。"
                + _EVIDENCE_CITATION + _CROSS_DOMAIN + _HILL_CLIMBING
            ),
            "arbitrator": (
                "你是【首席仲裁官⚖️】，负责在充分听取各方论证后做出最终裁决。"
                "你的思维风格是辩证综合：不简单地选择胜出方，而是通过'辩证扬弃'——"
                "保留各方论证中经得起检验的部分，剔除被有效反驳的部分，"
                "在此基础上构建更高层次的综合判断。你必须：（1）评估每条证据链的可靠性；"
                "（2）权衡不同维度分析的权重；（3）明确裁决的置信区间；"
                "（4）指出在什么条件下裁决可能需要修正。"
                "你的裁决应当体现'认知谦逊'——对不确定性保持诚实。"
                + _EVIDENCE_CITATION + _CROSS_DOMAIN
            ),
            # ── 专业分析角色 ──────────────────────────────────────
            "intel_analyst": (
                "你是【情报分析师🔍】，负责为辩论提供情报基础的事实核查与来源评估。"
                "你的思维风格是结构化情报分析（SIA）：采用A-B-C来源分级体系评估信息可靠性，"
                "区分硬情报（已验证事实）与软情报（未验证传闻）。你擅长识别情报盲区——"
                "哪些关键信息缺失？信息不对称在哪里？对手可能拥有哪些我们不知道的信息？"
                "在辩论中，你的核心职能是为其他专家的论点提供情报可信度评估，"
                "并对矛盾信息进行交叉验证。"
                "引用情报时必须标注来源类型（OSINT/HUMINT/SIGINT/公开报告）和时效性。"
                + _CROSS_DOMAIN + _HILL_CLIMBING
            ),
            "geo_expert": (
                "你是【地缘政治专家🌍】，负责从地理、联盟体系和国际秩序维度分析命题。"
                "你的思维风格是地缘战略推演：运用麦金德心脏地带论、马汉海权论、"
                "斯皮克曼边缘地带论等经典地缘政治框架，结合当代多极化现实进行分析。"
                "你特别关注：（1）关键地理节点（海峡、通道、战略要地）的影响；"
                "（2）联盟体系的可靠性与约束（如北约第五条款、双边安全条约）；"
                "（3）国际制度框架（联合国安理会、WTO、区域组织）的制约作用；"
                "（4）非国家行为体（跨国公司、NGO、恐怖组织）的地缘影响力。"
                "分析中必须引用具体的地缘历史先例和当前联盟承诺。"
                + _EVIDENCE_CITATION + _CROSS_DOMAIN + _HILL_CLIMBING
            ),
            "econ_analyst": (
                "你是【经济分析师💰】，负责评估命题的宏观经济影响和经济可行性。"
                "你的思维风格是量化成本收益分析：用具体经济指标（GDP、CPI、失业率、"
                "贸易差额、外汇储备、债务率等）支撑每个论点。你擅长分析："
                "（1）直接经济成本与机会成本；（2）供应链脆弱性与关键依赖；"
                "（3）制裁/贸易战的传导效应；（4）金融市场预期与风险溢价变化；"
                "（5）长期结构性影响与短期周期性波动的区别。"
                "你的分析必须考虑地缘政治对经济的外溢效应——例如安全风险如何影响资本流动、"
                "能源价格如何传导至通胀。引用数据时注明时间范围和数据来源。"
                + _EVIDENCE_CITATION + _HILL_CLIMBING
            ),
            "military_strategist": (
                "你是【军事战略家⚔️】，负责从军事力量平衡和作战可行性角度评估命题。"
                "你的思维风格是兵棋推演式分析：评估（1）双方军事力量对比（兵力、装备、"
                "训练、指挥体系）；（2）地理环境对作战的影响；（3）后勤保障能力与持续作战能力；"
                "（4）技术代差与不对称作战可能性；（5）核威慑与升级风险。"
                "你擅长引用具体战例进行类比分析（如海湾战争的后勤教训、"
                "俄乌冲突的无人机战术演变），并评估军事选项的政治后果。"
                "分析中必须区分'军事可行性'与'政治可接受性'——军事上可行的方案"
                "政治上未必可接受。"
                + _EVIDENCE_CITATION + _CROSS_DOMAIN + _HILL_CLIMBING
            ),
            "tech_foresight": (
                "你是【技术前瞻者🔮】，负责评估技术发展趋势对命题的影响。"
                "你的思维风格是技术成熟度曲线（Gartner Hype Cycle）与S曲线分析相结合："
                "评估关键技术的当前TRL（技术就绪水平）、发展瓶颈和突破时间窗口。"
                "你关注：（1）颠覆性技术（AI、量子计算、高超音速武器）对现有格局的冲击；"
                "（2）技术封锁与自主可控的博弈；（3）军民融合技术的扩散效应；"
                "（4）网络空间与信息战的新维度。"
                "你的分析必须区分'技术可能性'与'工程可行性'与'规模化部署时间线'。"
                "引用具体的研发项目进展、专利数据和技术指标。"
                + _EVIDENCE_CITATION + _CROSS_DOMAIN + _HILL_CLIMBING
            ),
            "social_impact": (
                "你是【社会影响评估师👥】，负责评估命题的社会维度影响。"
                "你的思维风格是社会系统动力学：分析（1）公众舆论与政治合法性；"
                "（2）社会稳定与治理韧性；（3）人口结构变化的长期影响；"
                "（4）信息环境与认知战的影响；（5）人道主义关切与国际规范。"
                "你擅长识别'社会脆弱性指标'——哪些社会因素可能成为决策的约束条件或放大器？"
                "分析中引用民调数据、社会运动案例、人口统计数据和历史社会危机案例。"
                "特别关注技术变革对社会结构的冲击以及代际价值观差异对政策执行的影响。"
                + _EVIDENCE_CITATION + _CROSS_DOMAIN + _HILL_CLIMBING
            ),
        }
        return prompts.get(role, (
            "你是一名客观分析员，负责基于证据评估命题。"
            "要求：引用具体数据和来源，避免模糊表述；考虑跨领域关联因素；"
            "在收到质疑时主动修正和完善分析。"
            + _EVIDENCE_CITATION + _CROSS_DOMAIN + _HILL_CLIMBING
        ))

    def _build_debate_prompt(
        self,
        *,
        role: str,
        topic: str,
        trigger_type: str,
        context: str,
        opponent_arguments: list[dict[str, Any]] | None = None,
        own_previous: list[dict[str, Any]] | None = None,
    ) -> str:
        _ROLE_DISPLAY = {
            "advocate": "战略支持者🟢",
            "challenger": "风险挑战者🔴",
            "arbitrator": "首席仲裁官⚖️",
            "intel_analyst": "情报分析师🔍",
            "geo_expert": "地缘政治专家🌍",
            "econ_analyst": "经济分析师💰",
            "military_strategist": "军事战略家⚔️",
            "tech_foresight": "技术前瞻者🔮",
            "social_impact": "社会影响评估师👥",
        }
        role_display = _ROLE_DISPLAY.get(role, role)

        opponent_text = ""
        if opponent_arguments:
            opponent_text = "\n【前序论证摘要】\n" + "\n".join(
                f"- {a.get('claim', a.get('counter', str(a)))[:200]}" for a in opponent_arguments[:8]
            )

        own_text = ""
        if own_previous:
            own_text = "\n【你此前的论点】\n" + "\n".join(
                f"- {a.get('claim', str(a))[:200]}" for a in own_previous[:5]
            )

        return (
            f"角色：{role_display}\n"
            f"议题：{topic}\n"
            f"触发类型：{trigger_type}\n"
            f"背景信息、证据项和相关声明：\n{context}\n"
            f"{opponent_text}{own_text}\n\n"
            "请返回以下结构化结果：\n"
            "1. 立场（SUPPORT/OPPOSE/CONDITIONAL）\n"
            "2. 置信度（0-1之间的浮点数）\n"
            "3. 最多3条论证（每条包含：claim-论点声明、evidence_ids-引用的证据ID、"
            "reasoning-推理过程、strength-论点强度0-1）\n"
            "4. 可选的反驳（target_argument_idx-目标论点索引、counter-反驳内容）\n"
            "5. 可选的让步（argument_idx-论点索引、reason-让步原因）\n"
            "请尽量使用提供的evidence_ids。如果进行了跨域分析，在reasoning中明确标注关联领域。"
        )

    def _parse_debate_position_payload(self, parsed: dict[str, Any] | None) -> DebatePositionPayload | None:
        if parsed is None:
            return None
        try:
            return DebatePositionPayload.model_validate(parsed)
        except Exception:
            return None

    def _debate_target_for_role(self, role: str) -> str:
        if self.openai_service is None:
            return "primary"
        role_targets = {
            "advocate": ("debate_advocate", "primary"),
            "challenger": ("debate_challenger", "extraction", "primary"),
            "arbitrator": ("debate_arbitrator", "report", "primary"),
            "strategist": ("debate_advocate", "primary"),
            "risk_analyst": ("debate_challenger", "extraction", "primary"),
            "opportunist": ("debate_arbitrator", "report", "primary"),
            "intel_analyst": ("debate_challenger", "extraction", "primary"),
            "geo_expert": ("debate_advocate", "primary"),
            "econ_analyst": ("debate_advocate", "primary"),
            "military_strategist": ("debate_advocate", "primary"),
            "tech_foresight": ("debate_advocate", "primary"),
            "social_impact": ("debate_advocate", "primary"),
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
        advocate_rounds = [r for r in rounds if r["role"] in {"advocate", "strategist", "geo_expert", "econ_analyst", "military_strategist", "tech_foresight", "social_impact"}]
        challenger_rounds = [r for r in rounds if r["role"] in {"challenger", "risk_analyst", "intel_analyst"}]
        arbitrator_rounds = [r for r in rounds if r["role"] in {"arbitrator", "opportunist"}]

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
                "role": "strategist",
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
                "role": "risk_analyst",
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
                "role": "opportunist",
                "position": self._verdict_position(verdict),
                "confidence": max(support_confidence, challenge_confidence),
                "arguments": [
                    {
                        "claim": f"Final verdict: {verdict}.",
                        "evidence_ids": evidence_ids[:3],
                        "reasoning": "The opportunist compared branch KPI deltas, recommendations, and unresolved downside tradeoffs.",
                        "strength": "STRONG",
                    }
                ],
                "rebuttals": [],
                "concessions": ([{"argument_idx": 0, "reason": conditions[0]}] if conditions else []),
            },
        ]

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
            challenger_rounds=[r for r in rounds if r["role"] in {"risk_analyst", "challenger", "intel_analyst"}],
            verdict=verdict,
            minority_opinion=minority_opinion,
        )
        branch_alternative_scenarios = self._generate_alternative_scenarios(
            advocate_rounds=[r for r in rounds if r["role"] in {"strategist", "advocate", "geo_expert", "econ_analyst", "military_strategist", "tech_foresight", "social_impact"}],
            challenger_rounds=[r for r in rounds if r["role"] in {"risk_analyst", "challenger", "intel_analyst"}],
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
        if payload.context_lines:
            context_parts.append("Trigger context:\n" + "\n".join(payload.context_lines))
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
                "role": "strategist",
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
                "role": "risk_analyst",
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
                "role": "opportunist",
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
            challenger_rounds=[r for r in rounds if r["role"] in {"risk_analyst", "challenger", "intel_analyst"}],
            verdict=verdict,
            minority_opinion=minority_opinion,
        )
        claim_alternative_scenarios = self._generate_alternative_scenarios(
            advocate_rounds=[r for r in rounds if r["role"] in {"strategist", "advocate", "geo_expert", "econ_analyst", "military_strategist", "tech_foresight", "social_impact"}],
            challenger_rounds=[r for r in rounds if r["role"] in {"risk_analyst", "challenger", "intel_analyst"}],
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
                "role": "strategist",
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
                "role": "risk_analyst",
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
                "role": "strategist",
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
                "role": "risk_analyst",
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
                "role": "opportunist",
                "position": self._verdict_position(verdict),
                "confidence": max(support_confidence, challenge_confidence),
                "arguments": [
                    {
                        "claim": f"Final verdict: {verdict}.",
                        "evidence_ids": decisive_evidence,
                        "reasoning": "The opportunist weighted final-state metrics, matched rules, and unresolved shocks.",
                        "strength": "STRONG",
                    }
                ],
                "rebuttals": [],
                "concessions": (
                    [{"argument_idx": 0, "reason": conditions[0]}] if conditions else []
                ),
            },
        ]

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
            challenger_rounds=[r for r in rounds if r["role"] in {"risk_analyst", "challenger", "intel_analyst"}],
            verdict=verdict,
            minority_opinion=minority_opinion,
        )
        run_alternative_scenarios = self._generate_alternative_scenarios(
            advocate_rounds=[r for r in rounds if r["role"] in {"strategist", "advocate", "geo_expert", "econ_analyst", "military_strategist", "tech_foresight", "social_impact"}],
            challenger_rounds=[r for r in rounds if r["role"] in {"risk_analyst", "challenger", "intel_analyst"}],
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
            recommendations.append({
                "title": "Proceed with current strategy",
                "priority": "high",
                "rationale": f"Strong support confidence ({support_confidence:.0%}) indicates favorable conditions.",
                "action_items": [arg for arg in winning_arguments[:2]],
            })
            if minority_opinion:
                recommendations.append({
                    "title": "Monitor identified risks",
                    "priority": "medium",
                    "rationale": f"While accepted, the risk analyst noted: {minority_opinion[:200]}",
                    "action_items": ["Set up monitoring for risk factors", "Schedule periodic reassessment"],
                })
        elif verdict == "REJECTED":
            recommendations.append({
                "title": "Revise strategy before proceeding",
                "priority": "high",
                "rationale": f"Challenge confidence ({challenge_confidence:.0%}) indicates significant concerns.",
                "action_items": [arg for arg in winning_arguments[:2]],
            })
            recommendations.append({
                "title": "Explore alternative approaches",
                "priority": "high",
                "rationale": "Current approach carries too much risk. Consider pivoting strategy.",
                "action_items": ["Conduct scenario analysis for alternatives", "Gather additional evidence"],
            })
        else:
            recommendations.append({
                "title": "Proceed with conditions",
                "priority": "medium",
                "rationale": "Mixed signals suggest proceeding cautiously with monitoring.",
                "action_items": (conditions or ["Continue monitoring key indicators"])[:2],
            })

        if conditions:
            recommendations.append({
                "title": "Address conditional requirements",
                "priority": "medium",
                "rationale": "Conditions must be met before full commitment.",
                "action_items": conditions[:3],
            })

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
            risks.insert(0, "Current strategy was rejected — high risk of failure if pursued unchanged.")
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
            scenarios.append({
                "name": "Pivot Strategy",
                "description": "Abandon current approach and adopt the challenger's recommended path.",
                "expected_outcome": "Reduced risk exposure, potentially slower progress.",
            })
        elif verdict == "CONDITIONAL":
            scenarios.append({
                "name": "Incremental Approach",
                "description": "Implement recommendations in phases with checkpoints.",
                "expected_outcome": "Balanced risk-reward with built-in course correction.",
            })
        else:
            scenarios.append({
                "name": "Accelerated Execution",
                "description": "Fast-track implementation given strong support signals.",
                "expected_outcome": "Faster results but requires active monitoring for emergent risks.",
            })
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
