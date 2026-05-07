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
    ) -> AsyncIterator[DebateStreamEvent]:
        completed_rounds: list[dict[str, Any]] = []
        round_plan = build_round_plan(self._get_custom_agents())

        for round_number, role, instruction in round_plan:
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

        opponent_rounds = [
            item
            for item in completed_rounds
            if (round_number == 2 and item["round_number"] == 1)
            or (round_number == 3 and item["round_number"] == 2)
            or (role == "arbitrator")
        ]
        history = debate_history()
        return {
            "context": (
                f"{instruction}\n\n"
                f"Debate history so far:\n{history or 'No prior debate rounds.'}\n\n"
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
                {"claim": argument.claim, "reasoning": argument.reasoning} for argument in arguments
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
            a
            for p in [advocate_r1, intel_r1, geo_r1, econ_r1, military_r1, tech_r1, social_r1]
            if p is not None
            for a in p.arguments
        ]
        round_2_instruction = (
            "【第2轮·质询】请针对第1轮所有立论进行系统性质疑，找出逻辑漏洞和证据缺陷。"
        )
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
        all_r2_args = [a for p in [challenger_r2, intel_r2] if p is not None for a in p.arguments]
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
            a
            for p in [
                advocate_r1,
                intel_r1,
                geo_r1,
                econ_r1,
                military_r1,
                tech_r1,
                social_r1,
                challenger_r1,
                challenger_r2,
                intel_r2,
                advocate_r3,
                geo_r3,
                econ_r3,
                military_r3,
                tech_r3,
                social_r3,
            ]
            if p is not None
            for a in p.arguments
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
