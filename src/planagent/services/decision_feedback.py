"""Decision feedback service — track decision outcomes and verify prediction accuracy.

Addresses the audit gap: UserDecision model exists but lacks accuracy tracking.
This service closes the loop by:
1. Linking decisions to predictions/hypotheses
2. Tracking outcomes
3. Scoring accuracy over time
4. Triggering calibration when accuracy drops
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from planagent.domain.models import (
    DecisionRecordRecord,
    Hypothesis,
    PredictionVersion,
    UserDecision,
    utc_now,
)

_logger = logging.getLogger(__name__)


@dataclass
class AccuracyReport:
    """Summary of prediction accuracy."""
    total_decisions: int = 0
    verified_outcomes: int = 0
    correct_predictions: int = 0
    accuracy_rate: float = 0.0
    avg_confidence: float = 0.0
    calibration_needed: bool = False
    details: list[dict[str, Any]] = field(default_factory=list)


class DecisionFeedbackService:
    """Tracks decision outcomes and verifies prediction accuracy.

    Workflow:
    1. When a user makes a decision → record it with linked prediction
    2. When outcome data arrives → verify against prediction
    3. Periodically → compute accuracy report
    4. If accuracy drops below threshold → trigger recalibration
    """

    def __init__(self, accuracy_threshold: float = 0.6) -> None:
        self.accuracy_threshold = accuracy_threshold

    async def record_decision(
        self,
        session: AsyncSession,
        *,
        user_id: str,
        topic: str,
        decision_text: str,
        chosen_option: str,
        prediction_id: str | None = None,
        hypothesis_id: str | None = None,
        run_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> UserDecision:
        """Record a user's decision with optional link to prediction."""
        decision = UserDecision(
            user_id=user_id,
            topic=topic,
            decision_text=decision_text,
            chosen_option=chosen_option,
            prediction_id=prediction_id,
            hypothesis_id=hypothesis_id,
            run_id=run_id,
            outcome_status="pending",
            metadata=metadata or {},
        )
        session.add(decision)
        await session.flush()
        _logger.info("Decision recorded: %s for topic '%s'", decision.id, topic)
        return decision

    async def record_outcome(
        self,
        session: AsyncSession,
        decision_id: str,
        outcome_text: str,
        outcome_rating: float | None = None,  # 0.0 to 1.0
    ) -> UserDecision | None:
        """Record the outcome of a previous decision.

        Args:
            decision_id: The decision to update
            outcome_text: Description of what actually happened
            outcome_rating: How well the prediction matched (0=wrong, 1=perfect)
        """
        decision = await session.get(UserDecision, decision_id)
        if decision is None:
            return None

        decision.outcome_text = outcome_text
        decision.outcome_status = "verified"
        decision.outcome_rating = outcome_rating
        decision.outcome_recorded_at = utc_now()

        # Update linked prediction version if exists
        if decision.prediction_id:
            pred = await session.get(PredictionVersion, decision.prediction_id)
            if pred and outcome_rating is not None:
                pred.accuracy_score = outcome_rating
                if outcome_rating < 0.3:
                    pred.status = "SUPERSEDED"
                    _logger.warning(
                        "Prediction %s superseded due to low accuracy (%.2f)",
                        pred.id, outcome_rating,
                    )

        # Update linked hypothesis if exists
        if decision.hypothesis_id:
            hyp = await session.get(Hypothesis, decision.hypothesis_id)
            if hyp and outcome_rating is not None:
                hyp.outcome_score = outcome_rating
                hyp.status = "verified" if outcome_rating >= 0.5 else "disproven"

        await session.flush()
        return decision

    async def compute_accuracy(
        self,
        session: AsyncSession,
        *,
        user_id: str | None = None,
        run_id: str | None = None,
        days: int = 30,
    ) -> AccuracyReport:
        """Compute prediction accuracy over a time window."""
        cutoff = utc_now() - timedelta(days=days)

        query = select(UserDecision).where(
            UserDecision.outcome_status == "verified",
            UserDecision.outcome_recorded_at >= cutoff,
        )
        if user_id:
            query = query.where(UserDecision.user_id == user_id)
        if run_id:
            query = query.where(UserDecision.run_id == run_id)

        results = list((await session.scalars(query)).all())

        if not results:
            return AccuracyReport(calibration_needed=False)

        total = len(results)
        correct = sum(1 for r in results if (r.outcome_rating or 0) >= 0.5)
        avg_conf = sum(r.outcome_rating or 0 for r in results) / total
        accuracy = correct / total if total > 0 else 0.0

        report = AccuracyReport(
            total_decisions=total,
            verified_outcomes=total,
            correct_predictions=correct,
            accuracy_rate=accuracy,
            avg_confidence=avg_conf,
            calibration_needed=accuracy < self.accuracy_threshold,
            details=[
                {
                    "id": r.id,
                    "topic": r.topic,
                    "chosen_option": r.chosen_option,
                    "outcome_rating": r.outcome_rating,
                    "outcome_text": r.outcome_text,
                }
                for r in results
            ],
        )

        if report.calibration_needed:
            _logger.warning(
                "Accuracy %.1f%% below threshold %.1f%% — calibration recommended",
                accuracy * 100, self.accuracy_threshold * 100,
            )

        return report

    async def get_pending_verifications(
        self,
        session: AsyncSession,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get decisions awaiting outcome verification."""
        query = (
            select(UserDecision)
            .where(UserDecision.outcome_status == "pending")
            .order_by(UserDecision.created_at.desc())
            .limit(limit)
        )
        results = list((await session.scalars(query)).all())
        return [
            {
                "id": r.id,
                "user_id": r.user_id,
                "topic": r.topic,
                "decision_text": r.decision_text,
                "chosen_option": r.chosen_option,
                "prediction_id": r.prediction_id,
                "created_at": r.created_at.isoformat(),
                "days_since": (utc_now() - r.created_at).days,
            }
            for r in results
        ]
