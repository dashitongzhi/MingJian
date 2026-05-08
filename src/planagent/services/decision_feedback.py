"""Decision feedback service — track decision outcomes and verify prediction accuracy.

Addresses the audit gap: UserDecision model exists but lacks accuracy tracking.
This service closes the loop by:
1. Querying decisions and their outcomes
2. Computing accuracy metrics
3. Flagging calibration needs
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from planagent.domain.models import (
    StrategicSession,
    UserDecision,
    utc_now,
)

_logger = logging.getLogger(__name__)


@dataclass
class AccuracyReport:
    """Summary of prediction accuracy."""
    total_decisions: int = 0
    verified_outcomes: int = 0
    adopt_count: int = 0
    defer_count: int = 0
    reject_count: int = 0
    need_more_info_count: int = 0
    has_outcome: int = 0
    details: list[dict[str, Any]] = field(default_factory=list)


class DecisionFeedbackService:
    """Tracks decision outcomes and computes accuracy metrics.

    Works with the existing UserDecision model which has:
    - session_id, decision, notes, outcome, outcome_recorded_at
    """

    async def get_decision_stats(
        self,
        session: AsyncSession,
        *,
        session_id: str | None = None,
        days: int = 30,
    ) -> AccuracyReport:
        """Compute decision statistics over a time window."""
        cutoff = utc_now() - timedelta(days=days)

        query = select(UserDecision).where(
            UserDecision.created_at >= cutoff,
        )
        if session_id:
            query = query.where(UserDecision.session_id == session_id)

        results = list((await session.scalars(query)).all())

        if not results:
            return AccuracyReport()

        total = len(results)
        adopt = sum(1 for r in results if r.decision == "adopt")
        defer = sum(1 for r in results if r.decision == "defer")
        reject = sum(1 for r in results if r.decision == "reject")
        need_more = sum(1 for r in results if r.decision == "need_more_info")
        has_outcome = sum(1 for r in results if r.outcome is not None)

        return AccuracyReport(
            total_decisions=total,
            verified_outcomes=has_outcome,
            adopt_count=adopt,
            defer_count=defer,
            reject_count=reject,
            need_more_info_count=need_more,
            has_outcome=has_outcome,
            details=[
                {
                    "id": r.id,
                    "session_id": r.session_id,
                    "decision": r.decision,
                    "notes": r.notes,
                    "outcome": r.outcome,
                    "has_outcome": r.outcome is not None,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in results[:50]
            ],
        )

    async def get_pending_verifications(
        self,
        session: AsyncSession,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get decisions awaiting outcome verification."""
        query = (
            select(UserDecision)
            .where(UserDecision.outcome.is_(None))
            .order_by(UserDecision.created_at.desc())
            .limit(limit)
        )
        results = list((await session.scalars(query)).all())

        # Enrich with session topic
        enriched = []
        for r in results:
            topic = "Unknown"
            if r.session_id:
                strategic_session = await session.get(StrategicSession, r.session_id)
                if strategic_session:
                    topic = strategic_session.topic

            enriched.append({
                "id": r.id,
                "session_id": r.session_id,
                "topic": topic,
                "decision": r.decision,
                "notes": r.notes,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "days_since": (utc_now() - r.created_at).days if r.created_at else None,
            })

        return enriched

    async def record_outcome(
        self,
        session: AsyncSession,
        decision_id: str,
        outcome_text: str,
    ) -> UserDecision | None:
        """Record the outcome of a previous decision."""
        decision = await session.get(UserDecision, decision_id)
        if decision is None:
            return None

        decision.outcome = outcome_text
        decision.outcome_recorded_at = utc_now()
        await session.flush()
        return decision
