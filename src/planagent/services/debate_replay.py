"""辩论回放服务 — Debate Replay Service

Provides replay, round detail, timeline, comparison and summary features
for completed debate sessions.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from planagent.domain.api import (
    DebateComparisonRead,
    DebateReplayRead,
    DebateReplaySummaryRead,
    DebateRoundDetailRead,
    DebateTimelineRead,
    DebateVerdictRead,
)
from planagent.domain.models import (
    DebateInterruptRecord,
    DebateRoundRecord,
    DebateSessionRecord,
    DebateVerdictRecord,
)


@dataclass(frozen=True)
class _RoundEntry:
    """Internal helper for a single round entry in the replay timeline."""
    round_number: int
    role: str
    position: str
    confidence: float
    arguments: list[dict[str, Any]]
    rebuttals: list[dict[str, Any]]
    concessions: list[dict[str, Any]]
    created_at: datetime


class DebateReplayService:
    """Service for debate replay, timeline, comparison and summary."""

    # ── helpers ────────────────────────────────────────────────────────────

    @staticmethod
    async def _get_session_or_raise(
        session: AsyncSession, debate_id: str
    ) -> DebateSessionRecord:
        debate = await session.get(DebateSessionRecord, debate_id)
        if debate is None:
            raise LookupError(f"Debate {debate_id} was not found.")
        return debate

    @staticmethod
    async def _load_rounds(
        session: AsyncSession, debate_id: str
    ) -> list[DebateRoundRecord]:
        return list(
            (
                await session.scalars(
                    select(DebateRoundRecord)
                    .where(DebateRoundRecord.debate_id == debate_id)
                    .order_by(
                        DebateRoundRecord.round_number.asc(),
                        DebateRoundRecord.role.asc(),
                    )
                )
            ).all()
        )

    @staticmethod
    async def _load_verdict(
        session: AsyncSession, debate_id: str
    ) -> DebateVerdictRecord | None:
        return await session.get(DebateVerdictRecord, debate_id)

    @staticmethod
    async def _load_interrupts(
        session: AsyncSession, debate_id: str
    ) -> list[DebateInterruptRecord]:
        return list(
            (
                await session.scalars(
                    select(DebateInterruptRecord)
                    .where(DebateInterruptRecord.debate_session_id == debate_id)
                    .order_by(DebateInterruptRecord.created_at.asc())
                )
            ).all()
        )

    @staticmethod
    def _round_to_entry(r: DebateRoundRecord) -> _RoundEntry:
        return _RoundEntry(
            round_number=r.round_number,
            role=r.role,
            position=r.position,
            confidence=r.confidence,
            arguments=r.arguments or [],
            rebuttals=r.rebuttals or [],
            concessions=r.concessions or [],
            created_at=r.created_at,
        )

    @staticmethod
    def _verdict_to_read(v: DebateVerdictRecord | None) -> DebateVerdictRead | None:
        if v is None:
            return None
        return DebateVerdictRead(
            debate_id=v.debate_id,
            topic=v.topic,
            trigger_type=v.trigger_type,
            rounds_completed=v.rounds_completed,
            verdict=v.verdict,
            confidence=v.confidence,
            winning_arguments=v.winning_arguments or [],
            decisive_evidence=v.decisive_evidence or [],
            conditions=v.conditions,
            minority_opinion=v.minority_opinion,
            recommendations=v.recommendations or [],
            risk_factors=v.risk_factors or [],
            alternative_scenarios=v.alternative_scenarios or [],
            conclusion_summary=v.conclusion_summary,
            created_at=v.created_at,
        )

    # ── get_replay ─────────────────────────────────────────────────────────

    async def get_replay(
        self, session: AsyncSession, debate_id: str
    ) -> DebateReplayRead:
        """获取辩论回放数据，按时间顺序组织（包含插话事件）"""
        debate = await self._get_session_or_raise(session, debate_id)
        rounds = await self._load_rounds(session, debate_id)
        verdict = await self._load_verdict(session, debate_id)
        interrupts = await self._load_interrupts(session, debate_id)

        # Group by round_number for the by-round view
        rounds_by_number: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in rounds:
            rounds_by_number[str(r.round_number)].append(
                {
                    "round_number": r.round_number,
                    "role": r.role,
                    "position": r.position,
                    "confidence": r.confidence,
                    "arguments": r.arguments or [],
                    "rebuttals": r.rebuttals or [],
                    "concessions": r.concessions or [],
                    "created_at": r.created_at.isoformat(),
                }
            )

        # Build chronological timeline (every speech + interruptions ordered by time)
        timeline: list[dict[str, Any]] = []

        for r in rounds:
            timeline.append({
                "event_type": "speech",
                "round_number": r.round_number,
                "role": r.role,
                "position": r.position,
                "confidence": r.confidence,
                "arguments": r.arguments or [],
                "rebuttals": r.rebuttals or [],
                "concessions": r.concessions or [],
                "timestamp": r.created_at.isoformat(),
            })

        for intr in interrupts:
            timeline.append({
                "event_type": "interrupt",
                "interrupt_id": intr.id,
                "interrupt_type": intr.interrupt_type,
                "message": intr.message,
                "injected_at_round": intr.injected_at_round,
                "status": intr.status,
                "timestamp": intr.created_at.isoformat(),
            })

        timeline.sort(key=lambda x: x["timestamp"])

        return DebateReplayRead(
            debate_id=debate.id,
            topic=debate.topic,
            trigger_type=debate.trigger_type,
            status=debate.status,
            target_type=debate.target_type,
            target_id=debate.target_id,
            total_rounds=max((int(k) for k in rounds_by_number.keys()), default=0),
            rounds_by_number=dict(rounds_by_number),
            timeline=timeline,
            verdict=self._verdict_to_read(verdict),
            created_at=debate.created_at,
            updated_at=debate.updated_at,
        )

    # ── get_round_detail ───────────────────────────────────────────────────

    async def get_round_detail(
        self, session: AsyncSession, debate_id: str, round_number: int
    ) -> DebateRoundDetailRead:
        """获取单轮详情"""
        debate = await self._get_session_or_raise(session, debate_id)
        rounds = await self._load_rounds(session, debate_id)

        round_records = [r for r in rounds if r.round_number == round_number]
        if not round_records:
            raise LookupError(
                f"Round {round_number} not found in debate {debate_id}."
            )

        entries = [self._round_to_entry(r) for r in round_records]

        return DebateRoundDetailRead(
            debate_id=debate.id,
            topic=debate.topic,
            round_number=round_number,
            speeches=[
                {
                    "role": e.role,
                    "position": e.position,
                    "confidence": e.confidence,
                    "arguments": e.arguments,
                    "rebuttals": e.rebuttals,
                    "concessions": e.concessions,
                    "timestamp": e.created_at.isoformat(),
                }
                for e in entries
            ],
            created_at=round_records[0].created_at,
        )

    # ── get_debate_timeline ────────────────────────────────────────────────

    async def get_debate_timeline(
        self, session: AsyncSession, debate_id: str
    ) -> DebateTimelineRead:
        """获取辩论时间线（每个发言和插话的时间戳）"""
        debate = await self._get_session_or_raise(session, debate_id)
        rounds = await self._load_rounds(session, debate_id)
        interrupts = await self._load_interrupts(session, debate_id)

        events: list[dict[str, Any]] = []
        for r in rounds:
            events.append({
                "event_type": "speech",
                "round_number": r.round_number,
                "role": r.role,
                "position": r.position,
                "confidence": r.confidence,
                "timestamp": r.created_at.isoformat(),
                "argument_count": len(r.arguments or []),
                "rebuttal_count": len(r.rebuttals or []),
                "concession_count": len(r.concessions or []),
            })

        for intr in interrupts:
            events.append({
                "event_type": "interrupt",
                "interrupt_id": intr.id,
                "interrupt_type": intr.interrupt_type,
                "message": intr.message,
                "status": intr.status,
                "timestamp": intr.created_at.isoformat(),
            })

        # Sort by timestamp
        events.sort(key=lambda e: e["timestamp"])

        verdict = await self._load_verdict(session, debate_id)
        verdict_event = None
        if verdict is not None:
            verdict_event = {
                "event_type": "verdict",
                "verdict": verdict.verdict,
                "confidence": verdict.confidence,
                "timestamp": verdict.created_at.isoformat(),
            }

        return DebateTimelineRead(
            debate_id=debate.id,
            topic=debate.topic,
            event_count=len(events),
            events=events,
            verdict_event=verdict_event,
            started_at=debate.created_at,
            completed_at=verdict.created_at if verdict else debate.updated_at,
        )

    # ── compare_debates ────────────────────────────────────────────────────

    async def compare_debates(
        self,
        session: AsyncSession,
        debate_id_1: str,
        debate_id_2: str,
    ) -> DebateComparisonRead:
        """对比两场辩论"""
        debate1 = await self._get_session_or_raise(session, debate_id_1)
        debate2 = await self._get_session_or_raise(session, debate_id_2)

        rounds1 = await self._load_rounds(session, debate_id_1)
        rounds2 = await self._load_rounds(session, debate_id_2)
        verdict1 = await self._load_verdict(session, debate_id_1)
        verdict2 = await self._load_verdict(session, debate_id_2)

        def _round_count(recs: list[DebateRoundRecord]) -> int:
            return max((r.round_number for r in recs), default=0)

        def _avg_confidence(recs: list[DebateRoundRecord]) -> float:
            if not recs:
                return 0.0
            return round(sum(r.confidence for r in recs) / len(recs), 4)

        def _total_arguments(recs: list[DebateRoundRecord]) -> int:
            return sum(len(r.arguments or []) for r in recs)

        def _total_rebuttals(recs: list[DebateRoundRecord]) -> int:
            return sum(len(r.rebuttals or []) for r in recs)

        def _total_concessions(recs: list[DebateRoundRecord]) -> int:
            return sum(len(r.concessions or []) for r in recs)

        debate1_summary = {
            "debate_id": debate1.id,
            "topic": debate1.topic,
            "trigger_type": debate1.trigger_type,
            "total_rounds": _round_count(rounds1),
            "average_confidence": _avg_confidence(rounds1),
            "total_arguments": _total_arguments(rounds1),
            "total_rebuttals": _total_rebuttals(rounds1),
            "total_concessions": _total_concessions(rounds1),
            "verdict": verdict1.verdict if verdict1 else None,
            "verdict_confidence": verdict1.confidence if verdict1 else None,
        }

        debate2_summary = {
            "debate_id": debate2.id,
            "topic": debate2.topic,
            "trigger_type": debate2.trigger_type,
            "total_rounds": _round_count(rounds2),
            "average_confidence": _avg_confidence(rounds2),
            "total_arguments": _total_arguments(rounds2),
            "total_rebuttals": _total_rebuttals(rounds2),
            "total_concessions": _total_concessions(rounds2),
            "verdict": verdict2.verdict if verdict2 else None,
            "verdict_confidence": verdict2.confidence if verdict2 else None,
        }

        return DebateComparisonRead(
            debate_1=debate1_summary,
            debate_2=debate2_summary,
            differences={
                "round_count_diff": _round_count(rounds1) - _round_count(rounds2),
                "confidence_diff": round(
                    _avg_confidence(rounds1) - _avg_confidence(rounds2), 4
                ),
                "arguments_diff": _total_arguments(rounds1) - _total_arguments(rounds2),
                "rebuttals_diff": _total_rebuttals(rounds1) - _total_rebuttals(rounds2),
                "concessions_diff": _total_concessions(rounds1) - _total_concessions(rounds2),
                "same_verdict": (
                    (verdict1.verdict if verdict1 else None)
                    == (verdict2.verdict if verdict2 else None)
                ),
            },
        )

    # ── summary ────────────────────────────────────────────────────────────

    async def get_summary(
        self, session: AsyncSession, debate_id: str
    ) -> DebateReplaySummaryRead:
        """辩论摘要（包含关键转折点）"""
        debate = await self._get_session_or_raise(session, debate_id)
        rounds = await self._load_rounds(session, debate_id)
        verdict = await self._load_verdict(session, debate_id)

        # Build round summaries
        round_summaries: list[dict[str, Any]] = []
        rounds_by_number: dict[int, list[DebateRoundRecord]] = defaultdict(list)
        for r in rounds:
            rounds_by_number[r.round_number].append(r)

        for rnd_num in sorted(rounds_by_number.keys()):
            recs = rounds_by_number[rnd_num]
            round_summaries.append({
                "round_number": rnd_num,
                "roles": [r.role for r in recs],
                "positions": {r.role: r.position for r in recs},
                "confidences": {r.role: r.confidence for r in recs},
                "argument_count": sum(len(r.arguments or []) for r in recs),
                "rebuttal_count": sum(len(r.rebuttals or []) for r in recs),
                "concession_count": sum(len(r.concessions or []) for r in recs),
            })

        # Detect key turning points:
        # 1. Significant confidence drops between consecutive rounds
        # 2. Concessions appearing
        # 3. Role position changes
        turning_points: list[dict[str, Any]] = []

        sorted_nums = sorted(rounds_by_number.keys())
        for i in range(1, len(sorted_nums)):
            prev_num = sorted_nums[i - 1]
            curr_num = sorted_nums[i]
            prev_recs = rounds_by_number[prev_num]
            curr_recs = rounds_by_number[curr_num]

            # Check for confidence drops per role
            for curr_r in curr_recs:
                prev_r = next(
                    (p for p in prev_recs if p.role == curr_r.role), None
                )
                if prev_r is not None:
                    delta = curr_r.confidence - prev_r.confidence
                    if abs(delta) >= 0.15:
                        turning_points.append({
                            "type": "confidence_shift",
                            "round_number": curr_num,
                            "role": curr_r.role,
                            "previous_confidence": prev_r.confidence,
                            "current_confidence": curr_r.confidence,
                            "delta": round(delta, 4),
                            "description": (
                                f"{curr_r.role} confidence "
                                f"{'dropped' if delta < 0 else 'rose'} "
                                f"from {prev_r.confidence:.2f} to {curr_r.confidence:.2f}"
                            ),
                        })

            # Check for concessions
            for curr_r in curr_recs:
                if curr_r.concessions:
                    turning_points.append({
                        "type": "concession",
                        "round_number": curr_num,
                        "role": curr_r.role,
                        "concessions": curr_r.concessions,
                        "description": f"{curr_r.role} made {len(curr_r.concessions)} concession(s)",
                    })

        # Sort turning points by round
        turning_points.sort(key=lambda tp: tp["round_number"])

        return DebateReplaySummaryRead(
            debate_id=debate.id,
            topic=debate.topic,
            trigger_type=debate.trigger_type,
            status=debate.status,
            total_rounds=max((int(k) for k in rounds_by_number.keys()), default=0),
            verdict=verdict.verdict if verdict else None,
            verdict_confidence=verdict.confidence if verdict else None,
            winning_arguments=verdict.winning_arguments if verdict else [],
            conclusion_summary=verdict.conclusion_summary if verdict else None,
            minority_opinion=verdict.minority_opinion if verdict else None,
            round_summaries=round_summaries,
            turning_points=turning_points,
            created_at=debate.created_at,
        )
