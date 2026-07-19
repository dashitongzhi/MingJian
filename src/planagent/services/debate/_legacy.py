from __future__ import annotations

from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from planagent.domain.api import DebateTriggerRequest

from .contracts import (
    DebateCommand,
    DebateFinished,
    DebateInterruptInjected,
    DebateObservation,
    DebateRoundCompleted,
    DebateRoundStarted,
    DebateStreamEvent,
    DebateTarget,
)


class _LegacyTargetResolver(Protocol):
    async def _resolve_trigger_payload(
        self,
        session: AsyncSession,
        payload: DebateTriggerRequest,
    ) -> DebateTriggerRequest: ...


async def _command_from_legacy_request(
    resolver: _LegacyTargetResolver,
    session: AsyncSession,
    payload: DebateTriggerRequest,
) -> DebateCommand:
    target_kind = payload.target_type
    if (
        target_kind == "run"
        and payload.claim_id is not None
        and payload.run_id is None
        and payload.target_id is None
    ):
        target_kind = "claim"

    if target_kind == "branch" and payload.target_id is None:
        payload = await resolver._resolve_trigger_payload(session, payload)

    if target_kind == "run":
        target = DebateTarget.run(payload.target_id or payload.run_id or "")
    elif target_kind == "claim":
        target = DebateTarget.claim(payload.target_id or payload.claim_id or "")
    elif target_kind == "branch":
        target = DebateTarget.branch(payload.target_id or "")
    else:
        target = DebateTarget.report(payload.target_id or "", payload.run_id or "")

    return DebateCommand(
        target=target,
        topic=payload.topic,
        trigger_type=payload.trigger_type,
        context=tuple(payload.context_lines),
        mode=payload.debate_mode,
        domain_id=payload.domain_id,
    )


def _legacy_event_from_observation(observation: DebateObservation) -> DebateStreamEvent:
    if isinstance(observation, DebateInterruptInjected):
        return DebateStreamEvent(
            event="debate_interrupt_injected",
            payload={
                "debate_id": observation.debate_id,
                "round_number": observation.round_number,
                "role": observation.role,
                "count": observation.count,
                "interrupt_ids": list(observation.interrupt_ids),
            },
        )
    if isinstance(observation, DebateRoundStarted):
        return DebateStreamEvent(
            event="debate_round_start",
            payload={
                "debate_id": observation.debate_id,
                "round_number": observation.round_number,
                "role": observation.role,
            },
        )
    if isinstance(observation, DebateRoundCompleted):
        return DebateStreamEvent(
            event="debate_round_complete",
            payload={
                "debate_id": observation.debate_id,
                "round_number": observation.round_number,
                "role": observation.role,
                "position": observation.position,
                "confidence": observation.confidence,
                "key_arguments": list(observation.key_arguments),
            },
        )
    if not isinstance(observation, DebateFinished):
        raise TypeError(f"Unsupported debate observation: {type(observation).__name__}")
    verdict = observation.debate.verdict
    return DebateStreamEvent(
        event="debate_verdict",
        payload={
            "debate_id": observation.debate_id,
            "verdict": verdict.verdict if verdict is not None else None,
            "confidence": verdict.confidence if verdict is not None else None,
            "winning_arguments": verdict.winning_arguments if verdict is not None else [],
            "decisive_evidence": verdict.decisive_evidence if verdict is not None else [],
        },
    )
