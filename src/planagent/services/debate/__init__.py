from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from planagent.config import Settings
from planagent.domain.api import (
    DebateDetailRead,
    DebateSummaryRead,
    DebateTriggerRequest,
    DebateVerdictRead,
)
from planagent.domain.enums import EventTopic
from planagent.domain.models import (
    Claim,
    DebateInterruptRecord,
    DebateRoundRecord,
    DebateSessionRecord,
    DebateVerdictRecord,
    DecisionRecordRecord,
    DecisionOption,
    EventArchive,
    Hypothesis,
    ScenarioBranchRecord,
    SimulationRun,
)
from planagent.events.bus import EventBus
from planagent.services.openai_client import OpenAIService


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


from .adjudication import DebateAdjudicationMixin  # noqa: E402
from .llm import DebateLLMMixin  # noqa: E402
from .revisions import DebateRevisionMixin  # noqa: E402
from .rounds import DebateRoundMixin  # noqa: E402
from .triggers import DebateTriggerMixin  # noqa: E402


class DebateService(
    DebateRoundMixin,
    DebateLLMMixin,
    DebateAdjudicationMixin,
    DebateRevisionMixin,
    DebateTriggerMixin,
):
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
        run = (
            await session.get(SimulationRun, payload.run_id) if payload.run_id is not None else None
        )
        claim = await session.get(Claim, payload.claim_id) if payload.claim_id is not None else None
        debate_session = DebateSessionRecord(
            run_id=payload.run_id,
            claim_id=payload.claim_id,
            tenant_id=(claim.tenant_id if claim is not None else None)
            or (run.tenant_id if run is not None else None),
            preset_id=(claim.preset_id if claim is not None else None)
            or (run.preset_id if run is not None else None),
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

        if (
            payload.trigger_type in ("pivot_decision", "auto_conflict_detection")
            and payload.run_id is not None
        ):
            latest_decision = (
                await session.scalars(
                    select(DecisionRecordRecord)
                    .where(DecisionRecordRecord.run_id == payload.run_id)
                    .order_by(
                        DecisionRecordRecord.tick.desc(), DecisionRecordRecord.sequence.desc()
                    )
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
                    "debate_disagreements": [assessment.minority_opinion]
                    if assessment.minority_opinion
                    else [],
                }
                await self._ensure_debate_prediction(session, run, verdict, latest_decision)

        completed_payload = {
            "debate_id": debate_session.id,
            "run_id": payload.run_id,
            "claim_id": payload.claim_id,
            "verdict": assessment.verdict,
            "confidence": verdict.confidence,
        }
        session.add(
            EventArchive(topic=EventTopic.DEBATE_COMPLETED.value, payload=completed_payload)
        )

        # 立场自动修订检查
        revision_records = await self.check_and_apply_revisions(
            session=session,
            debate_id=debate_session.id,
            rounds=assessment.rounds,
        )
        if revision_records:
            completed_payload["revisions"] = [
                {"role": r["role"], "confidence_drop": r["confidence_drop"]}
                for r in revision_records
            ]

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

        run = (
            await session.get(SimulationRun, payload.run_id) if payload.run_id is not None else None
        )
        claim = await session.get(Claim, payload.claim_id) if payload.claim_id is not None else None
        debate_session = DebateSessionRecord(
            run_id=payload.run_id,
            claim_id=payload.claim_id,
            tenant_id=(claim.tenant_id if claim is not None else None)
            or (run.tenant_id if run is not None else None),
            preset_id=(claim.preset_id if claim is not None else None)
            or (run.preset_id if run is not None else None),
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
                session.add(
                    EventArchive(topic=EventTopic.DEBATE_TRIGGERED.value, payload=trigger_payload)
                )
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
                        yield self._stream_event(
                            stream_event.event, debate_id, stream_event.payload
                        )
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
                rounds_completed=max(
                    round_data["round_number"] for round_data in assessment.rounds
                ),
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

                if (
                    payload.trigger_type in ("pivot_decision", "auto_conflict_detection")
                    and payload.run_id is not None
                ):
                    latest_decision = (
                        await session.scalars(
                            select(DecisionRecordRecord)
                            .where(DecisionRecordRecord.run_id == payload.run_id)
                            .order_by(
                                DecisionRecordRecord.tick.desc(),
                                DecisionRecordRecord.sequence.desc(),
                            )
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
                            "debate_disagreements": [assessment.minority_opinion]
                            if assessment.minority_opinion
                            else [],
                        }
                        await self._ensure_debate_prediction(session, run, verdict, latest_decision)

                completed_payload = {
                    "debate_id": debate_id,
                    "run_id": payload.run_id,
                    "claim_id": payload.claim_id,
                    "verdict": assessment.verdict,
                    "confidence": verdict.confidence,
                }
                session.add(
                    EventArchive(topic=EventTopic.DEBATE_COMPLETED.value, payload=completed_payload)
                )
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
                expected_effects=latest_decision.expected_effect
                if latest_decision is not None
                else {},
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
                    select(ScenarioBranchRecord)
                    .where(ScenarioBranchRecord.run_id == payload.run_id)
                    .limit(1)
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

    async def list_all_debates(
        self, session: AsyncSession, limit: int = 50
    ) -> list[DebateSummaryRead]:
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
                recommendation_count=len(verdicts.get(item.id).recommendations or [])
                if item.id in verdicts
                else 0,
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
                recommendation_count=len(verdicts.get(item.id).recommendations or [])
                if item.id in verdicts
                else 0,
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

    @staticmethod
    async def get_pending_interrupts(
        session: AsyncSession,
        debate_id: str,
    ) -> list[DebateInterruptRecord]:
        """获取辩论的待注入插话记录（PENDING 状态）"""
        return list(
            (
                await session.scalars(
                    select(DebateInterruptRecord)
                    .where(
                        DebateInterruptRecord.debate_session_id == debate_id,
                        DebateInterruptRecord.status == "PENDING",
                    )
                    .order_by(DebateInterruptRecord.created_at.asc())
                )
            ).all()
        )

    @staticmethod
    def format_interrupts_for_context(
        interrupts: list[DebateInterruptRecord],
    ) -> str | None:
        """将待注入的插话格式化为辩论 context 文本"""
        if not interrupts:
            return None
        lines = ["[用户插话 - 以下内容来自用户在辩论中途提交的补充信息]"]
        for intr in interrupts:
            type_label = {
                "supplementary_info": "补充信息",
                "direction_correction": "修正方向",
                "new_evidence": "新证据",
                "general": "通用插话",
            }.get(intr.interrupt_type, "通用插话")
            lines.append(f"  [{type_label}] {intr.message}")
        return "\n".join(lines)

    @staticmethod
    async def mark_interrupts_injected(
        session: AsyncSession,
        debate_id: str,
        round_number: int,
    ) -> int:
        """将 PENDING 状态的插话标记为 INJECTED，返回处理数量"""
        pending = list(
            (
                await session.scalars(
                    select(DebateInterruptRecord).where(
                        DebateInterruptRecord.debate_session_id == debate_id,
                        DebateInterruptRecord.status == "PENDING",
                    )
                )
            ).all()
        )
        for intr in pending:
            intr.status = "INJECTED"
            intr.injected_at_round = round_number
        return len(pending)


__all__ = [
    "ClaimRelationContext",
    "DebateAssessment",
    "DebateService",
    "DebateStreamEvent",
    "DebateStreamPreparation",
]
