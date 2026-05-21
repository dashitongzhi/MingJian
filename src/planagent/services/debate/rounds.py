from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from planagent.domain.api import DebateTriggerRequest
from planagent.domain.models import (
    Claim,
    DebateRoundRecord,
    DecisionRecordRecord,
    EvidenceItem,
    ExternalShockRecord,
    GeneratedReport,
    SimulationRun,
)
from planagent.services.openai_client import DebatePositionPayload

from . import DebateStreamEvent, DebateStreamPreparation
from .prompts import build_round_plan

_TOKEN_BUDGET_PER_ROUND = 60000
_WRAP_UP_RATIO = 0.8
_KEEP_RECENT_MESSAGES = 3


def _estimate_tokens(text: str) -> int:
    return len(text) // 4


def _inject_wrap_up_nudge(messages: list, used: int, budget: int) -> None:
    if used > budget * _WRAP_UP_RATIO:
        messages.append(
            {
                "role": "system",
                "content": (
                    f"[系统] Token预算即将耗尽（已用{used}/{budget}）。"
                    "请立即停止扩展论证，输出最终立场总结。"
                ),
            }
        )


def _trim_old_messages(messages: list, keep: int = _KEEP_RECENT_MESSAGES) -> list:
    if len(messages) <= keep:
        return messages
    trimmed = []
    for msg in messages[:-keep]:
        # Preserve essential structure (round_number, role) for debate_history()
        trimmed.append(
            {
                "round_number": msg.get("round_number", 0),
                "role": msg.get("role", "unknown"),
                "position": msg.get("position", "NEUTRAL"),
                "confidence": msg.get("confidence", 0.0),
                "arguments": [],
                "rebuttals": [],
                "concessions": [],
            }
        )
    trimmed.extend(messages[-keep:])
    return trimmed


class DebateRoundMixin:
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
            decisive_evidence = list(
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
        final_state = {
            key: float(value) for key, value in run.summary.get("final_state", {}).items()
        }
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
        debate_mode: str = "full",
        domain_id: str | None = None,
        session: AsyncSession | None = None,
        debate_id: str | None = None,
    ) -> AsyncIterator[DebateStreamEvent]:
        completed_rounds: list[dict[str, Any]] = []
        round_plan = build_round_plan(
            self._get_custom_agents(),
            mode=debate_mode,
            domain_id=domain_id,
            topic=topic,
            context=context,
            evidence_count=len(evidence_ids),
        )

        for round_number, role, instruction in round_plan:
            if session is not None and debate_id is not None:
                pending_interrupts = await self.get_pending_interrupts(session, debate_id)
                interrupt_context = self.format_interrupts_for_context(pending_interrupts)
                if interrupt_context:
                    context = f"{context}\n\n{interrupt_context}"
                    injected_count = await self.mark_interrupts_injected(
                        session, debate_id, round_number
                    )
                    await session.flush()
                    yield DebateStreamEvent(
                        event="debate_interrupt_injected",
                        payload={
                            "round_number": round_number,
                            "role": role,
                            "count": injected_count,
                            "interrupt_ids": [item.id for item in pending_interrupts],
                        },
                    )
            yield DebateStreamEvent(
                event="debate_round_start",
                payload={"round_number": round_number, "role": role},
            )
            round_payload = await self._execute_single_round(
                round_number=round_number,
                role=role,
                instruction=instruction,
                topic=topic,
                trigger_type=trigger_type,
                context=context,
                evidence_ids=evidence_ids,
                completed_rounds=completed_rounds,
            )
            completed_rounds.append(round_payload)
            yield DebateStreamEvent(event="debate_round_complete", payload={"round": round_payload})

    async def _execute_single_round(
        self,
        *,
        round_number: int,
        role: str,
        instruction: str,
        topic: str,
        trigger_type: str,
        context: str,
        evidence_ids: list[str],
        completed_rounds: list[dict[str, Any]],
    ) -> dict[str, Any]:
        messages = self._build_round_messages(
            round_number=round_number,
            role=role,
            instruction=instruction,
            context=context,
            completed_rounds=completed_rounds,
        )
        position = await self._call_llm(
            role=role,
            topic=topic,
            trigger_type=trigger_type,
            context=messages["context"],
            opponent_arguments=messages["opponent_arguments"],
            own_previous=messages["own_previous"],
        )
        if position is None:
            return self._fallback_stream_round(round_number, role, evidence_ids)
        return self._position_to_round_payload(round_number, role, position, evidence_ids)

    def _build_round_messages(
        self,
        *,
        round_number: int,
        role: str,
        instruction: str,
        context: str,
        completed_rounds: list[dict[str, Any]],
    ) -> dict[str, Any]:
        def argument_refs(rounds: list[dict[str, Any]]) -> list[dict[str, str]]:
            return [
                {
                    "claim": str(argument.get("claim", "")),
                    "reasoning": str(argument.get("reasoning", "")),
                }
                for round_payload in rounds
                for argument in round_payload.get("arguments", [])
            ]

        def own_refs() -> list[dict[str, str]]:
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

        def pending_cross_questions() -> str:
            lines: list[str] = []
            for item in completed_rounds:
                for rebuttal in item.get("rebuttals", []) or []:
                    target_role = str(
                        rebuttal.get("target_role")
                        or rebuttal.get("target")
                        or rebuttal.get("to_role")
                        or ""
                    )
                    if target_role and target_role != role:
                        continue
                    question = rebuttal.get("question") or rebuttal.get("counter")
                    if not question:
                        continue
                    source_role = str(item.get("role", "unknown"))
                    lines.append(f"- From {source_role}: {str(question)[:220]}")
            return "\n".join(lines)

        opponent_rounds = [
            item
            for item in completed_rounds
            if (round_number == 2 and item["round_number"] == 1)
            or (round_number == 3 and item["round_number"] == 2)
            or (role == "arbitrator")
        ]
        history = debate_history()
        cross_questions = pending_cross_questions()
        return {
            "context": (
                f"{instruction}\n\n"
                f"Debate history so far:\n{history or 'No prior debate rounds.'}\n\n"
                f"Pending cross-examination questions for this role:\n{cross_questions or 'None.'}\n\n"
                f"Original context:\n{context}"
            ),
            "opponent_arguments": argument_refs(opponent_rounds) if opponent_rounds else None,
            "own_previous": own_refs() if role != "arbitrator" else None,
        }

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

    def _stream_event(
        self, event: str, debate_id: str, payload: dict[str, Any]
    ) -> DebateStreamEvent:
        return DebateStreamEvent(event=event, payload={"debate_id": debate_id, **payload})

    async def _llm_debate_rounds(
        self,
        topic: str,
        trigger_type: str,
        context: str,
        evidence_ids: list[str],
        debate_mode: str = "full",
        domain_id: str | None = None,
    ) -> list[dict[str, Any]] | None:
        if not self._has_available_debate_provider():
            return None

        rounds: list[dict[str, Any]] = []
        async for stream_event in self._stream_llm_rounds(
            topic=topic,
            trigger_type=trigger_type,
            context=context,
            evidence_ids=evidence_ids,
            debate_mode=debate_mode,
            domain_id=domain_id,
        ):
            if stream_event.event == "debate_round_complete":
                rounds.append(stream_event.payload["round"])
        return rounds if rounds else None
