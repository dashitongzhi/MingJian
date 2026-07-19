from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from planagent.domain.models import DebateRoundRecord

from .contracts import DebateStreamEvent


class DebateRoundMixin:
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
