from __future__ import annotations

import re
from collections import defaultdict
from datetime import timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from planagent.config import Settings
from planagent.db import get_database
from planagent.domain.models import (
    CalibrationRecord,
    Claim,
    DecisionRecordRecord,
    Hypothesis,
    PredictionBacktestRecord,
    PredictionSeries,
    PredictionVersion,
    SimulationRun,
    utc_now,
)
from planagent.services.pipeline import normalize_text
from planagent.simulation.rules import RuleRegistry
from planagent.workers.base import Worker, WorkerDescription

_TIME_HORIZON_DAYS: dict[str, int] = {
    "1_month": 30,
    "3_months": 90,
    "6_months": 180,
    "1_year": 365,
}
_MIN_HYPOTHESES_FOR_CALIBRATION = 3
_CALIBRATION_WINDOW_DAYS = 90
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_CALIBRATION_STOPWORDS = {
    "the", "and", "for", "with", "this", "that", "from", "after", "before",
    "into", "across", "over", "under", "still", "remain", "remained",
    "during", "through", "their", "there", "about", "will", "would",
    "could", "should", "may", "might", "has", "have", "been", "was",
    "were", "are", "is", "be", "being",
}


class CalibrationWorker(Worker):
    description = WorkerDescription(
        worker_id="calibration-worker",
        summary=(
            "Verifies pending hypotheses against recent evidence, "
            "records calibration stats per domain, and adjusts rule weights."
        ),
        consumes=(),
        produces=(),
    )

    def __init__(
        self,
        settings: Settings,
        rule_registry: RuleRegistry,
    ) -> None:
        self.settings = settings
        self.rule_registry = rule_registry
        self.worker_instance_id = self.description.worker_id

    async def run_once(self) -> dict[str, object]:
        database = get_database()
        errors: list[str] = []
        async with database.session() as session:
            verified, verify_errors = await self._verify_pending_hypotheses(session)
            verified_predictions, prediction_errors = await self._verify_pending_predictions(session)
            rule_accuracy_count = await self._update_rule_accuracies(session)
            source_trust_count = await self._update_source_trust_scores(session)
            if rule_accuracy_count or source_trust_count:
                await session.commit()
            calibration_records = await self._aggregate_calibration(session)
            rule_accuracies = await self._compute_rule_accuracies(session)
            if rule_accuracies:
                self.rule_registry.apply_calibration(rule_accuracies)
            errors = verify_errors + prediction_errors
        return {
            "verified_hypotheses": verified,
            "verified_predictions": verified_predictions,
            "calibration_records": calibration_records,
            "rules_adjusted": len(rule_accuracies),
            "rule_accuracies_updated": rule_accuracy_count,
            "source_trust_scores_updated": source_trust_count,
            "errors": errors,
        }

    async def _verify_pending_hypotheses(self, session: AsyncSession) -> tuple[int, list[str]]:
        now = utc_now()
        hypotheses = list(
            (
                await session.scalars(
                    select(Hypothesis)
                    .where(Hypothesis.verification_status == "PENDING")
                    .order_by(Hypothesis.created_at.asc())
                    .limit(200)
                )
            ).all()
        )
        verified = 0
        errors: list[str] = []
        for hypo in hypotheses:
            try:
                horizon_days = _TIME_HORIZON_DAYS.get(hypo.time_horizon, 90)
                due_at = (hypo.created_at or utc_now()).replace(tzinfo=timezone.utc) + timedelta(days=horizon_days)
                if now < due_at:
                    continue

                claim = await self._find_verification_claim(session, hypo)
                if claim is not None:
                    hypo.verification_status = self._resolve_verdict(hypo, claim)
                    hypo.actual_outcome = claim.statement[:500]
                    hypo.verified_at = now
                else:
                    hypo.verification_status = "PARTIAL"
                    hypo.actual_outcome = "No confirming or refuting evidence found in the target window."
                    hypo.verified_at = now
                hypo.updated_at = now
                verified += 1
            except Exception as exc:
                errors.append(f"hypothesis:{hypo.id}:{type(exc).__name__}:{exc}")
        await session.commit()
        return verified, errors

    async def _verify_pending_predictions(self, session: AsyncSession) -> tuple[int, list[str]]:
        """验证到期的 PredictionVersion。"""
        now = utc_now()
        versions = list(
            (
                await session.scalars(
                    select(PredictionVersion)
                    .where(PredictionVersion.status == "ACTIVE")
                    .order_by(PredictionVersion.created_at.asc())
                    .limit(200)
                )
            ).all()
        )
        if not versions:
            return 0, []

        series_ids = {version.series_id for version in versions}
        series_map = {
            series.id: series
            for series in (
                (
                    await session.scalars(
                        select(PredictionSeries).where(PredictionSeries.id.in_(series_ids))
                    )
                ).all()
            )
        }
        verified = 0
        errors: list[str] = []
        for version in versions:
            try:
                horizon_days = _TIME_HORIZON_DAYS.get(version.time_horizon, 90)
                due_at = (version.created_at or utc_now()).replace(tzinfo=timezone.utc) + timedelta(days=horizon_days)
                if now < due_at:
                    continue

                existing = (
                    await session.scalars(
                        select(PredictionBacktestRecord)
                        .where(PredictionBacktestRecord.prediction_version_id == version.id)
                        .limit(1)
                    )
                ).first()
                if existing is not None:
                    continue

                status, actual_outcome = await self._resolve_prediction_verdict(session, version)
                series = series_map.get(version.series_id)
                if series is None:
                    raise LookupError(f"Prediction series {version.series_id} was not found.")

                score = 1.0 if status == "CONFIRMED" else 0.5 if status == "PARTIAL" else 0.0
                record = PredictionBacktestRecord(
                    prediction_version_id=version.id,
                    series_id=version.series_id,
                    run_id=version.run_id,
                    domain_id=series.domain_id,
                    tenant_id=series.tenant_id,
                    preset_id=series.preset_id,
                    verification_status=status,
                    actual_outcome=actual_outcome[:1000],
                    score=score,
                    verified_at=now,
                )
                version.status = status
                version.updated_at = now
                version.version_metadata = {
                    **(version.version_metadata or {}),
                    "verification_status": status,
                    "actual_outcome": actual_outcome[:1000],
                    "backtest_score": score,
                    "verified_at": now.isoformat(),
                    "verification_source": "calibration_worker",
                }
                session.add(record)
                verified += 1
            except Exception as exc:
                errors.append(f"prediction:{version.id}:{type(exc).__name__}:{exc}")
        if verified:
            await session.commit()
        return verified, errors

    async def _resolve_prediction_verdict(
        self,
        session: AsyncSession,
        version: PredictionVersion,
    ) -> tuple[str, str]:
        hypothesis = await self._version_hypothesis(session, version)
        if hypothesis is not None and hypothesis.verification_status != "PENDING":
            return (
                hypothesis.verification_status,
                hypothesis.actual_outcome or "Prediction resolved from linked hypothesis.",
            )

        claim = await self._find_prediction_claim(session, version)
        if claim is not None:
            status = self._resolve_prediction_claim_verdict(version, claim)
            return status, claim.statement
        return "PARTIAL", "No confirming or refuting evidence found in the target window."

    async def _version_hypothesis(
        self,
        session: AsyncSession,
        version: PredictionVersion,
    ) -> Hypothesis | None:
        if version.hypothesis_id is not None:
            hypothesis = await session.get(Hypothesis, version.hypothesis_id)
            if hypothesis is not None:
                return hypothesis
        return (
            await session.scalars(
                select(Hypothesis)
                .where(Hypothesis.prediction_version_id == version.id)
                .order_by(Hypothesis.updated_at.desc())
                .limit(1)
            )
        ).first()

    async def _find_prediction_claim(
        self,
        session: AsyncSession,
        version: PredictionVersion,
    ) -> Claim | None:
        horizon_days = _TIME_HORIZON_DAYS.get(version.time_horizon, 90)
        horizon_start = (version.created_at or utc_now()).replace(tzinfo=timezone.utc) + timedelta(days=horizon_days // 2)
        version_tokens = self._text_tokens(version.prediction_text)
        if not version_tokens:
            return None

        candidates = list(
            (
                await session.scalars(
                    select(Claim)
                    .where(
                        Claim.created_at > horizon_start,
                        Claim.confidence >= 0.45,
                    )
                    .order_by(Claim.confidence.desc())
                    .limit(50)
                )
            ).all()
        )
        best: tuple[float, Claim | None] = (0.0, None)
        for candidate in candidates:
            sim = self._token_overlap(version_tokens, self._text_tokens(candidate.statement))
            if sim > best[0]:
                best = (sim, candidate)
        return best[1] if best[0] >= 0.15 else None

    def _resolve_prediction_claim_verdict(self, version: PredictionVersion, claim: Claim) -> str:
        version_tokens = self._text_tokens(version.prediction_text)
        claim_tokens = self._text_tokens(claim.statement)
        overlap = len(version_tokens & claim_tokens)
        union = len(version_tokens | claim_tokens) or 1
        sim = overlap / union
        if sim >= 0.35:
            return "CONFIRMED"
        if sim >= 0.2:
            return "PARTIAL"
        return "REFUTED"

    async def _find_verification_claim(self, session: AsyncSession, hypo: Hypothesis) -> Claim | None:
        horizon_days = _TIME_HORIZON_DAYS.get(hypo.time_horizon, 90)
        horizon_start = (hypo.created_at or utc_now()).replace(tzinfo=timezone.utc) + timedelta(days=horizon_days // 2)
        hypo_tokens = self._text_tokens(hypo.prediction)
        if not hypo_tokens:
            return None

        candidates = list(
            (
                await session.scalars(
                    select(Claim)
                    .where(
                        Claim.created_at > horizon_start,
                        Claim.confidence >= 0.45,
                    )
                    .order_by(Claim.confidence.desc())
                    .limit(50)
                )
            ).all()
        )
        best: tuple[float, Claim | None] = (0.0, None)
        for candidate in candidates:
            sim = self._token_overlap(hypo_tokens, self._text_tokens(candidate.statement))
            if sim > best[0]:
                best = (sim, candidate)
        return best[1] if best[0] >= 0.15 else None

    def _resolve_verdict(self, hypo: Hypothesis, claim: Claim) -> str:
        hypo_tokens = self._text_tokens(hypo.prediction)
        claim_tokens = self._text_tokens(claim.statement)
        overlap = len(hypo_tokens & claim_tokens)
        union = len(hypo_tokens | claim_tokens) or 1
        sim = overlap / union
        if sim >= 0.35:
            return "CONFIRMED"
        if sim >= 0.2:
            return "PARTIAL"
        return "REFUTED"

    async def _aggregate_calibration(self, session: AsyncSession) -> int:
        now = utc_now()
        window_start = now - timedelta(days=_CALIBRATION_WINDOW_DAYS)
        hypotheses = list(
            (
                await session.scalars(
                    select(Hypothesis)
                    .where(
                        Hypothesis.verified_at > window_start,
                        Hypothesis.verification_status.in_(["CONFIRMED", "REFUTED", "PARTIAL"]),
                    )
                    .order_by(Hypothesis.created_at.asc())
                )
            ).all()
        )
        domain_groups: dict[str, list[Hypothesis]] = defaultdict(list)
        # Batch-load SimulationRuns to avoid N+1 per-hypothesis get
        run_ids = [h.run_id for h in hypotheses if h.run_id is not None]
        run_map: dict[str, SimulationRun] = {}
        if run_ids:
            runs = list(
                (
                    await session.scalars(
                        select(SimulationRun).where(SimulationRun.id.in_(run_ids))
                    )
                ).all()
            )
            run_map = {r.id: r for r in runs}

        for hypo in hypotheses:
            domain_id = "general"
            if hypo.run_id is not None:
                run = run_map.get(hypo.run_id)
                if run is not None:
                    domain_id = run.domain_id
            domain_groups[domain_id].append(hypo)

        records = 0
        for domain_id, group in domain_groups.items():
            if len(group) < _MIN_HYPOTHESES_FOR_CALIBRATION:
                continue
            confirmed = sum(1 for h in group if h.verification_status == "CONFIRMED")
            refuted = sum(1 for h in group if h.verification_status == "REFUTED")
            partial = sum(1 for h in group if h.verification_status == "PARTIAL")
            pending = sum(1 for h in group if h.verification_status == "PENDING")
            total = len(group)
            score = round((confirmed + 0.5 * partial) / max(total, 1), 4)
            rule_accuracy = await self._calc_rule_accuracy(session, group)

            record = CalibrationRecord(
                domain_id=domain_id,
                period_start=window_start,
                period_end=now,
                total_hypotheses=total,
                confirmed=confirmed,
                refuted=refuted,
                partial=partial,
                pending=pending,
                calibration_score=score,
                rule_accuracy=rule_accuracy,
            )
            session.add(record)
            records += 1
        if records:
            await session.commit()
        return records

    async def _calc_rule_accuracy(self, session: AsyncSession, hypotheses: list[Hypothesis]) -> dict[str, float]:
        rule_counts: dict[str, list[str]] = defaultdict(list)
        run_ids = [h.run_id for h in hypotheses if h.run_id]
        if not run_ids:
            return {}
        decisions = list(
            (
                await session.scalars(
                    select(DecisionRecordRecord)
                    .where(DecisionRecordRecord.run_id.in_(run_ids))
                    .order_by(DecisionRecordRecord.tick.asc())
                )
            ).all()
        )
        hypo_status = {h.run_id: h.verification_status for h in hypotheses if h.run_id}
        for d in decisions:
            status = hypo_status.get(d.run_id, "PENDING")
            for rule_id in d.policy_rule_ids:
                rule_counts[rule_id].append(status)

        rule_accuracy: dict[str, float] = {}
        for rule_id, statuses in rule_counts.items():
            confirmed = sum(1 for s in statuses if s == "CONFIRMED")
            partial = sum(1 for s in statuses if s == "PARTIAL")
            total = len(statuses) if len(statuses) >= _MIN_HYPOTHESES_FOR_CALIBRATION else 0
            if total > 0:
                rule_accuracy[rule_id] = round((confirmed + 0.5 * partial) / total, 4)
        return rule_accuracy

    async def _compute_rule_accuracies(self, session: AsyncSession) -> dict[str, float]:
        now = utc_now()
        window_start = now - timedelta(days=_CALIBRATION_WINDOW_DAYS)
        records = list(
            (
                await session.scalars(
                    select(CalibrationRecord)
                    .where(
                        CalibrationRecord.period_end > window_start,
                    )
                    .order_by(CalibrationRecord.created_at.desc())
                    .limit(10)
                )
            ).all()
        )
        if not records:
            return {}
        merged: dict[str, float] = {}
        for rec in records:
            for rule_id, accuracy in (rec.rule_accuracy or {}).items():
                merged[rule_id] = max(merged.get(rule_id, 0.0), accuracy)
        return merged

    async def _update_rule_accuracies(self, session: AsyncSession) -> int:
        """根据已验证的预测结果，更新每条规则的准确率"""
        from planagent.domain.models import RuleAccuracy

        verified = list(
            (
                await session.scalars(
                    select(PredictionBacktestRecord)
                    .where(
                        PredictionBacktestRecord.verification_status.in_(
                            ["CONFIRMED", "REFUTED", "PARTIAL"]
                        )
                    )
                    .order_by(PredictionBacktestRecord.verified_at.desc())
                    .limit(500)
                )
            ).all()
        )

        stats: dict[tuple[str, str], dict[str, int]] = {}
        for record in verified:
            version = await session.get(PredictionVersion, record.prediction_version_id)
            if not version:
                continue
            series = await session.get(PredictionSeries, version.series_id)
            if not series:
                continue

            if version.run_id:
                decisions = list(
                    (
                        await session.scalars(
                            select(DecisionRecordRecord).where(
                                DecisionRecordRecord.run_id == version.run_id
                            )
                        )
                    ).all()
                )
                for decision in decisions:
                    for rule_id in decision.policy_rule_ids:
                        key = (series.domain_id, rule_id)
                        if key not in stats:
                            stats[key] = {
                                "confirmed": 0,
                                "refuted": 0,
                                "partial": 0,
                                "total": 0,
                            }
                        stats[key]["total"] += 1
                        if record.verification_status == "CONFIRMED":
                            stats[key]["confirmed"] += 1
                        elif record.verification_status == "REFUTED":
                            stats[key]["refuted"] += 1
                        else:
                            stats[key]["partial"] += 1

        updated = 0
        for (domain_id, rule_id), s in stats.items():
            existing = (
                await session.scalars(
                    select(RuleAccuracy)
                    .where(
                        RuleAccuracy.rule_id == rule_id,
                        RuleAccuracy.domain_id == domain_id,
                    )
                    .limit(1)
                )
            ).first()

            if existing:
                existing.total_predictions = s["total"]
                existing.confirmed = s["confirmed"]
                existing.refuted = s["refuted"]
                existing.partial = s["partial"]
            else:
                existing = RuleAccuracy(
                    rule_id=rule_id,
                    domain_id=domain_id,
                    total_predictions=s["total"],
                    confirmed=s["confirmed"],
                    refuted=s["refuted"],
                    partial=s["partial"],
                )
                session.add(existing)

            if s["total"] > 0:
                existing.accuracy_score = (s["confirmed"] + s["partial"] * 0.5) / s["total"]
                existing.weight_multiplier = max(0.1, min(2.0, existing.accuracy_score * 2))
            existing.last_calculated_at = utc_now()
            updated += 1

        await session.flush()
        return updated

    async def _update_source_trust_scores(self, session: AsyncSession) -> int:
        """根据已验证的预测结果，更新数据来源的可信度"""
        from urllib.parse import urlparse

        from planagent.domain.models import (
            EvidenceItem,
            PredictionEvidenceLink,
            SourceTrustScore,
        )

        verified = list(
            (
                await session.scalars(
                    select(PredictionBacktestRecord)
                    .where(PredictionBacktestRecord.verification_status.in_(["CONFIRMED", "REFUTED"]))
                    .order_by(PredictionBacktestRecord.verified_at.desc())
                    .limit(200)
                )
            ).all()
        )

        source_stats: dict[str, dict[str, int]] = {}
        for record in verified:
            links = list(
                (
                    await session.scalars(
                        select(PredictionEvidenceLink).where(
                            PredictionEvidenceLink.prediction_version_id
                            == record.prediction_version_id
                        )
                    )
                ).all()
            )

            for link in links:
                evidence = await session.get(EvidenceItem, link.evidence_item_id)
                if not evidence:
                    continue
                source_url = evidence.source_url
                try:
                    domain = urlparse(source_url).netloc
                except Exception:
                    domain = source_url[:100]

                if domain not in source_stats:
                    source_stats[domain] = {"confirmed": 0, "refuted": 0, "total": 0}
                source_stats[domain]["total"] += 1
                if record.verification_status == "CONFIRMED":
                    source_stats[domain]["confirmed"] += 1
                else:
                    source_stats[domain]["refuted"] += 1

        updated = 0
        for pattern, s in source_stats.items():
            existing = (
                await session.scalars(
                    select(SourceTrustScore)
                    .where(SourceTrustScore.source_url_pattern == pattern)
                    .limit(1)
                )
            ).first()

            if not existing:
                existing = SourceTrustScore(source_type="mixed", source_url_pattern=pattern)
                session.add(existing)

            existing.total_evidence = s["total"]
            existing.evidence_confirmed = s["confirmed"]
            existing.evidence_refuted = s["refuted"]
            if s["total"] > 0:
                existing.trust_score = max(0.1, min(1.0, s["confirmed"] / s["total"]))
            existing.last_updated_at = utc_now()
            updated += 1

        await session.flush()
        return updated

    def _text_tokens(self, value: str) -> set[str]:
        return {
            token
            for token in _TOKEN_RE.findall(normalize_text(value).lower())
            if len(token) > 2 and token not in _CALIBRATION_STOPWORDS
        }

    def _token_overlap(self, base: set[str], candidate: set[str]) -> float:
        if not base or not candidate:
            return 0.0
        return len(base & candidate) / max(len(base | candidate), 1)
