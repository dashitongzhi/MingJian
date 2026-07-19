from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from planagent.domain.api import (
    DebateDetailRead,
    DebateTriggerRequest,
    DebateVerdictRead,
)
from planagent.domain.enums import EventTopic
from planagent.domain.models import (
    Claim,
    DebateRoundRecord,
    DebateSessionRecord,
    DebateVerdictRecord,
    EventArchive,
    GeneratedReport,
    ScenarioBranchRecord,
    SimulationRun,
)
from planagent.events.bus import EventBus

from .contracts import (
    DebateAssessment,
    DebateCommand,
    DebateFinished,
    DebateInterruptInjected,
    DebateObservation,
    DebateRoundCompleted,
    DebateRoundStarted,
    DebateTargetNotFound,
    DebateStreamEvent,
)
from .engines import load_custom_debate_agents
from .llm import DebateInterruptPort, DebatePreparationPort, LLMDebateAdapter
from .roles import debate_record_sort_key


class DebateWorkflowPort(DebatePreparationPort, DebateInterruptPort, Protocol):
    event_bus: EventBus
    llm_adapter: LLMDebateAdapter

    async def _resolve_trigger_payload(
        self,
        session: AsyncSession,
        payload: DebateTriggerRequest,
    ) -> DebateTriggerRequest: ...

    async def _assess_debate(
        self,
        session: AsyncSession,
        payload: DebateTriggerRequest,
    ) -> DebateAssessment: ...

    def _build_assessment_from_llm_rounds(
        self,
        rounds: list[dict[str, Any]],
        evidence_ids: list[str],
        payload: DebateTriggerRequest,
        **context: Any,
    ) -> DebateAssessment: ...

    async def _persist_stream_round(
        self,
        session: AsyncSession,
        debate_id: str,
        round_payload: dict[str, Any],
    ) -> None: ...

    def _round_complete_payload(self, round_payload: dict[str, Any]) -> dict[str, Any]: ...

    async def _complete_debate(
        self,
        *,
        session: AsyncSession,
        payload: DebateTriggerRequest,
        assessment: DebateAssessment,
        debate_session: DebateSessionRecord,
        run: SimulationRun | None,
        persist_rounds: bool,
    ) -> tuple[DebateVerdictRecord, dict[str, Any]]: ...


class DebateWorkflow:
    """Canonical command/observation interface for executing debates."""

    def __init__(self, port: DebateWorkflowPort) -> None:
        self._port = port

    async def decide(
        self,
        session: AsyncSession,
        command: DebateCommand,
    ) -> DebateDetailRead:
        """Execute one debate command and return its persisted outcome."""
        payload, run, claim = await self._prepare_command(session, command)
        assessment = await self._port._assess_debate(session, payload)
        debate_session = self._new_session(
            payload,
            run=run,
            claim=claim,
            status="COMPLETED",
            context_payload=assessment.context_payload,
        )
        session.add(debate_session)
        await session.flush()

        trigger_payload = self._trigger_payload(debate_session.id, payload)
        session.add(EventArchive(topic=EventTopic.DEBATE_TRIGGERED.value, payload=trigger_payload))
        _, completed_payload = await self._port._complete_debate(
            session=session,
            payload=payload,
            assessment=assessment,
            debate_session=debate_session,
            run=run,
            persist_rounds=True,
        )

        await session.commit()
        await self._port.event_bus.publish(EventTopic.DEBATE_TRIGGERED.value, trigger_payload)
        await self._port.event_bus.publish(EventTopic.DEBATE_COMPLETED.value, completed_payload)
        return await self.read(session, debate_session.id)

    async def observe(
        self,
        session: AsyncSession,
        command: DebateCommand,
    ) -> AsyncIterator[DebateObservation]:
        """Execute one debate command while yielding typed progress observations."""
        payload, run, claim = await self._prepare_command(session, command)
        debate_session = self._new_session(
            payload,
            run=run,
            claim=claim,
            status="RUNNING",
            context_payload={"user_context": payload.context_lines},
        )
        trigger_payload: dict[str, Any]
        debate_id = ""

        try:
            async with session.begin_nested():
                session.add(debate_session)
                await session.flush()
                debate_id = debate_session.id
                trigger_payload = self._trigger_payload(debate_id, payload)
                session.add(
                    EventArchive(topic=EventTopic.DEBATE_TRIGGERED.value, payload=trigger_payload)
                )
                await session.flush()
            await session.commit()

            preparation = await self._port.llm_adapter.prepare(
                session,
                payload,
                context_port=self._port,
            )
            if preparation is not None and self._port.llm_adapter.is_available():
                rounds: list[dict[str, Any]] = []
                async for stream_event in self._port.llm_adapter.stream_rounds(
                    topic=payload.topic,
                    trigger_type=payload.trigger_type,
                    context=preparation.context,
                    evidence_ids=preparation.llm_evidence_ids,
                    debate_mode=payload.debate_mode,
                    domain_id=payload.domain_id,
                    custom_agents=load_custom_debate_agents(),
                    session=session,
                    debate_id=debate_id,
                    interrupt_port=self._port,
                ):
                    observation, round_payload = self._observation_from_adapter(
                        debate_id, stream_event
                    )
                    if round_payload is not None:
                        rounds.append(round_payload)
                        await self._port._persist_stream_round(session, debate_id, round_payload)
                    yield observation
                assessment = self._port._build_assessment_from_llm_rounds(
                    rounds,
                    preparation.assessment_evidence_ids,
                    payload,
                    **preparation.assessment_kwargs,
                )
            else:
                assessment = await self._port._assess_debate(session, payload)
                for round_payload in assessment.rounds:
                    yield DebateRoundStarted(
                        debate_id=debate_id,
                        round_number=round_payload["round_number"],
                        role=round_payload["role"],
                    )
                    await self._port._persist_stream_round(session, debate_id, round_payload)
                    yield self._completed_observation(debate_id, round_payload)

            async with session.begin_nested():
                _, completed_payload = await self._port._complete_debate(
                    session=session,
                    payload=payload,
                    assessment=assessment,
                    debate_session=debate_session,
                    run=run,
                    persist_rounds=False,
                )
                await session.flush()

            await session.commit()
            await self._port.event_bus.publish(EventTopic.DEBATE_TRIGGERED.value, trigger_payload)
            await self._port.event_bus.publish(EventTopic.DEBATE_COMPLETED.value, completed_payload)
            detail = await self.read(session, debate_id)
            yield DebateFinished(debate_id=debate_id, debate=detail)
        except Exception:
            await session.rollback()
            if debate_id:
                failed_session = await session.get(DebateSessionRecord, debate_id)
                if failed_session is not None:
                    failed_session.status = "FAILED"
                    await session.commit()
            raise

    async def read(self, session: AsyncSession, debate_id: str) -> DebateDetailRead:
        """Read one persisted debate through the canonical result interface."""
        debate = await session.get(DebateSessionRecord, debate_id)
        if debate is None:
            raise DebateTargetNotFound(f"Debate {debate_id} was not found.")

        rounds = list(
            (
                await session.scalars(
                    select(DebateRoundRecord)
                    .where(DebateRoundRecord.debate_id == debate_id)
                    .order_by(
                        DebateRoundRecord.round_number.asc(),
                        DebateRoundRecord.created_at.asc(),
                    )
                )
            ).all()
        )
        rounds.sort(key=debate_record_sort_key)
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

    async def _prepare_command(
        self,
        session: AsyncSession,
        command: DebateCommand,
    ) -> tuple[DebateTriggerRequest, SimulationRun | None, Claim | None]:
        target = command.target
        payload = DebateTriggerRequest(
            run_id=target.id if target.kind == "run" else target.run_id,
            claim_id=target.id if target.kind == "claim" else None,
            topic=command.topic,
            trigger_type=command.trigger_type,
            target_type=target.kind,
            target_id=target.id,
            context_lines=list(command.context),
            debate_mode=command.mode,
            domain_id=command.domain_id,
        )
        payload = await self._port._resolve_trigger_payload(session, payload)

        run = (
            await session.get(SimulationRun, payload.run_id) if payload.run_id is not None else None
        )
        claim = await session.get(Claim, payload.claim_id) if payload.claim_id is not None else None
        if target.kind == "run" and run is None:
            raise DebateTargetNotFound(f"Simulation run {target.id} was not found.")
        if target.kind == "claim" and claim is None:
            raise DebateTargetNotFound(f"Claim {target.id} was not found.")
        if target.kind == "report":
            report = await session.get(GeneratedReport, target.id)
            if report is None or report.run_id != target.run_id or run is None:
                raise DebateTargetNotFound(
                    f"Report {target.id} was not found for run {target.run_id}."
                )
        if target.kind == "branch":
            branch = await session.get(ScenarioBranchRecord, target.id)
            if branch is None or run is None:
                raise DebateTargetNotFound(f"Scenario branch {target.id} was not found.")
        return payload, run, claim

    @staticmethod
    def _new_session(
        payload: DebateTriggerRequest,
        *,
        run: SimulationRun | None,
        claim: Claim | None,
        status: str,
        context_payload: dict[str, Any],
    ) -> DebateSessionRecord:
        return DebateSessionRecord(
            run_id=payload.run_id,
            claim_id=payload.claim_id,
            tenant_id=(claim.tenant_id if claim is not None else None)
            or (run.tenant_id if run is not None else None),
            preset_id=(claim.preset_id if claim is not None else None)
            or (run.preset_id if run is not None else None),
            topic=payload.topic,
            trigger_type=payload.trigger_type,
            status=status,
            target_type=payload.target_type,
            target_id=payload.target_id or payload.claim_id or payload.run_id,
            context_payload=context_payload,
        )

    @staticmethod
    def _trigger_payload(debate_id: str, payload: DebateTriggerRequest) -> dict[str, Any]:
        return {
            "debate_id": debate_id,
            "run_id": payload.run_id,
            "claim_id": payload.claim_id,
            "topic": payload.topic,
            "trigger_type": payload.trigger_type,
        }

    def _observation_from_adapter(
        self,
        debate_id: str,
        event: DebateStreamEvent,
    ) -> tuple[DebateObservation, dict[str, Any] | None]:
        if event.event == "debate_interrupt_injected":
            return (
                DebateInterruptInjected(
                    debate_id=debate_id,
                    round_number=event.payload["round_number"],
                    role=event.payload["role"],
                    count=event.payload["count"],
                    interrupt_ids=tuple(event.payload.get("interrupt_ids", [])),
                ),
                None,
            )
        if event.event == "debate_round_start":
            return (
                DebateRoundStarted(
                    debate_id=debate_id,
                    round_number=event.payload["round_number"],
                    role=event.payload["role"],
                ),
                None,
            )
        if event.event != "debate_round_complete":
            raise ValueError(f"Unsupported debate stream event: {event.event}")
        round_payload = event.payload["round"]
        return self._completed_observation(debate_id, round_payload), round_payload

    def _completed_observation(
        self,
        debate_id: str,
        round_payload: dict[str, Any],
    ) -> DebateRoundCompleted:
        payload = self._port._round_complete_payload(round_payload)
        return DebateRoundCompleted(
            debate_id=debate_id,
            round_number=payload["round_number"],
            role=payload["role"],
            position=payload["position"],
            confidence=payload["confidence"],
            key_arguments=tuple(payload["key_arguments"]),
        )
