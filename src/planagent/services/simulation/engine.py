from __future__ import annotations

from copy import deepcopy
from datetime import timedelta
from typing import Any

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from planagent.domain.api import SimulationRunCreate
from planagent.domain.enums import ClaimStatus, EventTopic, ExecutionMode, SimulationRunStatus
from planagent.domain.models import (
    Claim,
    DecisionRecordRecord,
    EventArchive,
    ExternalShockRecord,
    GeneratedReport,
    ScenarioBranchRecord,
    SimulationRun,
    StateSnapshotRecord,
    utc_now,
)
from planagent.services.pipeline import normalize_text
from planagent.services.simulation_branching import (
    _STATE_POLICIES,
)
from planagent.services.startup import normalize_tenant_id, startup_preset_config
from planagent.simulation.domain_packs import registry
from .impact import _DECISION_EVIDENCE_WINDOW


class SimulationEngineMixin:
    async def run_simulation(self, session: AsyncSession, run: SimulationRun) -> None:
        await self._execute_run(session, run)

    async def _execute_scenario(self, session: AsyncSession, run: SimulationRun) -> None:
        await self._execute_run(session, run)

    async def create_simulation_run(
        self,
        session: AsyncSession,
        payload: SimulationRunCreate,
    ) -> SimulationRun:
        execution_mode = payload.execution_mode or (
            ExecutionMode.INLINE
            if self.settings.inline_simulation_default
            else ExecutionMode.QUEUED
        )
        if payload.domain_id == "corporate":
            run = await self._create_corporate_run(session, payload, execution_mode)
        elif payload.domain_id == "military":
            run = await self._create_military_run(session, payload, execution_mode)
        else:
            raise ValueError(f"Domain {payload.domain_id} is not implemented yet.")

        if execution_mode == ExecutionMode.INLINE:
            await self._execute_run(session, run)
            await self._generate_report(session, run)

        await session.commit()
        await session.refresh(run)
        return run

    async def process_queued_runs(
        self,
        session: AsyncSession,
        limit: int = 10,
        worker_id: str | None = None,
    ) -> int:
        runs = await self._claim_simulation_runs(
            session,
            limit=limit,
            worker_id=worker_id or "simulation-worker",
        )
        processed = 0
        for run in runs:
            try:
                await self._execute_run(session, run)
                branch = (
                    await session.scalars(
                        select(ScenarioBranchRecord).where(ScenarioBranchRecord.run_id == run.id)
                    )
                ).first()
                if branch is not None and run.parent_run_id is not None:
                    parent_run = await session.get(SimulationRun, run.parent_run_id)
                    if parent_run is not None:
                        await self._refresh_scenario_branch(session, branch, parent_run, run)
                run.last_error = None
                processed += 1
            except Exception as exc:
                run.last_error = f"{type(exc).__name__}: {normalize_text(str(exc))[:300]}"
                run.status = (
                    SimulationRunStatus.FAILED.value
                    if run.processing_attempts >= self.settings.worker_max_attempts
                    else SimulationRunStatus.PENDING.value
                )
            finally:
                run.lease_owner = None
                run.lease_expires_at = None
                run.updated_at = utc_now()
        await session.commit()
        return processed

    async def _create_corporate_run(
        self,
        session: AsyncSession,
        payload: SimulationRunCreate,
        execution_mode: ExecutionMode,
    ) -> SimulationRun:
        company = await self._upsert_company(session, payload)
        run = SimulationRun(
            company_id=company.id,
            force_id=None,
            tenant_id=normalize_tenant_id(payload.tenant_id),
            preset_id=payload.preset_id,
            domain_id="corporate",
            actor_template=payload.actor_template,
            military_use_mode=None,
            execution_mode=execution_mode.value,
            status=SimulationRunStatus.PENDING.value,
            tick_count=payload.tick_count or self.settings.default_corporate_ticks,
            seed=payload.seed,
            configuration={
                "initial_state": payload.initial_state,
                "market": payload.market,
                **startup_preset_config(payload.tenant_id, payload.preset_id),
            },
            summary={},
        )
        session.add(run)
        await session.flush()
        return run

    async def _create_military_run(
        self,
        session: AsyncSession,
        payload: SimulationRunCreate,
        execution_mode: ExecutionMode,
    ) -> SimulationRun:
        force = await self._upsert_force(session, payload)
        military_use_mode = payload.military_use_mode or "full_domain"
        run = SimulationRun(
            company_id=None,
            force_id=force.id,
            tenant_id=normalize_tenant_id(payload.tenant_id),
            preset_id=payload.preset_id,
            domain_id="military",
            actor_template=payload.actor_template,
            military_use_mode=military_use_mode,
            execution_mode=execution_mode.value,
            status=SimulationRunStatus.PENDING.value,
            tick_count=payload.tick_count or self.settings.default_military_ticks,
            seed=payload.seed,
            configuration={
                "initial_state": payload.initial_state,
                "theater": payload.theater or force.theater,
                "military_use_mode": military_use_mode,
                "simulation_only": True,
                **startup_preset_config(payload.tenant_id, payload.preset_id),
            },
            summary={},
        )
        session.add(run)
        await session.flush()
        if military_use_mode == "full_domain":
            session.add(
                EventArchive(
                    topic="military.full_domain.audit",
                    payload={
                        "run_id": run.id,
                        "force_id": force.id,
                        "tenant_id": run.tenant_id,
                        "simulation_only": True,
                        "military_use_mode": military_use_mode,
                    },
                )
            )
        await self._ensure_geo_assets_for_run(session, run, force)
        return run

    async def _execute_run(self, session: AsyncSession, run: SimulationRun) -> None:
        run.status = SimulationRunStatus.PROCESSING.value
        run.updated_at = utc_now()

        pack = registry.get(run.domain_id)
        initial_state = self._resolve_initial_state(pack, run.actor_template)
        initial_state.update(
            {key: float(value) for key, value in run.configuration.get("initial_state", {}).items()}
        )
        claims = await self._fetch_relevant_claims(session, run)
        rules = self.rule_registry.get_rules(run.domain_id)
        matched_rules: list[str] = []
        shock_count = 0
        current_state = deepcopy(initial_state)
        actor_id = f"{self._subject_id(run)}:{run.actor_template}"
        recent_claims: list[Claim] = []
        action_history: list[str] = []
        enemy_history: list[str] = []
        recent_decision_records: list[DecisionRecordRecord] = []
        military_tick_summaries: list[dict[str, Any]] = []
        geo_assets = (
            await self.list_geo_assets(session, run.id) if run.domain_id == "military" else []
        )
        calibration_ctx = await self._build_calibration_context(session, run.domain_id, run.id)

        session.add(
            StateSnapshotRecord(
                run_id=run.id, tick=0, actor_id=actor_id, state=deepcopy(current_state)
            )
        )

        for tick in range(1, run.tick_count + 1):
            active_claim = claims[(tick - 1) % len(claims)] if claims else None
            if active_claim is not None:
                shock_count += await self._record_external_shock(session, run, tick, active_claim)
                self._apply_external_shock(run.domain_id, current_state, active_claim.statement)
                recent_claims.append(active_claim)
                recent_claims = recent_claims[-_DECISION_EVIDENCE_WINDOW:]
            selected = await self._select_action(
                run.domain_id,
                current_state,
                active_claim,
                rules,
                recent_claims=recent_claims,
                action_history=action_history,
                recent_decisions=recent_decision_records,
                calibration_context_text=calibration_ctx["context_text"],
                session=session,
            )
            matched_rules.extend(selected.rule_ids)
            actual_effect = selected.actual_effect
            why_selected = selected.why_selected
            if run.domain_id == "military":
                military_resolution = self._military.resolve_military_action_outcome(
                    current_state,
                    selected,
                    active_claim,
                    enemy_history,
                )
                actual_effect = military_resolution.actual_effect
                why_selected = (
                    f"{selected.why_selected} Enemy response {military_resolution.enemy_action_id} "
                    f"produced fire balance {military_resolution.fire_balance:+.2f}; objective control moved "
                    f"{military_resolution.objective_delta:+.3f} and the supply network moved "
                    f"{military_resolution.supply_delta:+.3f}."
                )
                enemy_history.append(military_resolution.enemy_action_id)
            self._apply_effects(current_state, actual_effect)
            if run.domain_id == "military":
                operational_picture = self._military.build_military_operational_picture(
                    run,
                    geo_assets,
                    current_state,
                    enemy_action_id=military_resolution.enemy_action_id,
                    enemy_reason=military_resolution.enemy_reason,
                )
                military_tick_summaries.append(
                    {
                        "tick": tick,
                        "enemy_action_id": military_resolution.enemy_action_id,
                        "enemy_reason": military_resolution.enemy_reason,
                        "fire_balance": military_resolution.fire_balance,
                        "objective_delta": military_resolution.objective_delta,
                        "supply_delta": military_resolution.supply_delta,
                        "recovery_delta": military_resolution.recovery_delta,
                        "enemy_posture": operational_picture["enemy_posture"],
                        "objective_snapshot": {
                            "critical_objective_id": operational_picture["objective_network"].get(
                                "critical_objective_id"
                            ),
                            "critical_route_id": operational_picture["objective_network"].get(
                                "critical_route_id"
                            ),
                            "contested_asset_ids": operational_picture["objective_network"].get(
                                "contested_asset_ids", []
                            ),
                        },
                    }
                )
            action_history.append(selected.action_id)
            decision_record = DecisionRecordRecord(
                run_id=run.id,
                tick=tick,
                sequence=1,
                actor_id=actor_id,
                action_id=selected.action_id,
                why_selected=why_selected,
                evidence_ids=selected.evidence_ids,
                policy_rule_ids=selected.rule_ids,
                expected_effect=selected.expected_effect,
                actual_effect=actual_effect,
                decision_method=selected.decision_method,
            )
            session.add(decision_record)
            recent_decision_records.append(decision_record)
            session.add(
                StateSnapshotRecord(
                    run_id=run.id,
                    tick=tick,
                    actor_id=actor_id,
                    state=deepcopy(current_state),
                )
            )

        run.status = SimulationRunStatus.COMPLETED.value
        run.completed_at = utc_now()
        run.updated_at = utc_now()
        final_operational_picture = (
            self._military.build_military_operational_picture(
                run,
                geo_assets,
                current_state,
                enemy_action_id=military_tick_summaries[-1]["enemy_action_id"]
                if military_tick_summaries
                else None,
                enemy_reason=military_tick_summaries[-1]["enemy_reason"]
                if military_tick_summaries
                else None,
            )
            if run.domain_id == "military"
            else {}
        )
        run.summary = {
            **run.summary,
            "ticks_completed": run.tick_count,
            "evidence_count": len(claims),
            "shock_count": shock_count,
            "evidence_ids": sorted({claim.evidence_item_id for claim in claims}),
            "evidence_statements": [claim.statement for claim in claims[:5]],
            "matched_rules": sorted(set(matched_rules)),
            "final_state": deepcopy(current_state),
            "military_tick_summaries": military_tick_summaries
            if run.domain_id == "military"
            else [],
            "objective_network": (
                final_operational_picture.get("objective_network", {})
                if run.domain_id == "military"
                else {}
            ),
            "enemy_posture": (
                final_operational_picture.get("enemy_posture", {})
                if run.domain_id == "military"
                else {}
            ),
            "enemy_order_of_battle": (
                final_operational_picture.get("enemy_order_of_battle", [])
                if run.domain_id == "military"
                else []
            ),
        }

        event_topic = (
            EventTopic.SCENARIO_COMPLETED.value
            if run.parent_run_id is not None
            else EventTopic.SIMULATION_COMPLETED.value
        )
        event_payload = {
            "run_id": run.id,
            "company_id": run.company_id,
            "force_id": run.force_id,
            "scenario_id": run.summary.get("scenario_id"),
        }
        session.add(EventArchive(topic=event_topic, payload=event_payload))
        await self.event_bus.publish(event_topic, event_payload)

        await self._generate_decision_options(session, run, current_state)
        from planagent.services.prediction import PredictionService

        prediction_service = PredictionService(self.settings, self.event_bus)
        versions = await prediction_service.create_initial_versions_for_run(session, run_id=run.id)
        await self._apply_calibrated_confidence(session, versions, calibration_ctx)

    async def _build_calibration_context(
        self,
        session: AsyncSession,
        domain_id: str,
        run_id: str,
    ) -> dict[str, Any]:
        """Build the calibration context injected into simulation prompts."""
        from planagent.domain.models import (
            PredictionCalibrationContext,
            PredictionSeries,
            PredictionVersion,
            RuleAccuracy,
        )

        rule_accuracies = list(
            (
                await session.scalars(
                    select(RuleAccuracy)
                    .where(RuleAccuracy.domain_id == domain_id, RuleAccuracy.total_predictions >= 3)
                    .order_by(RuleAccuracy.accuracy_score.desc())
                )
            ).all()
        )

        run = await session.get(SimulationRun, run_id)
        subject_id = self._subject_id(run) if run is not None else None
        historical_query = (
            select(PredictionVersion)
            .join(PredictionSeries, PredictionSeries.id == PredictionVersion.series_id)
            .where(PredictionSeries.domain_id == domain_id)
        )
        if subject_id:
            historical_query = historical_query.where(PredictionSeries.subject_id == subject_id)
        historical_versions = list(
            (
                await session.scalars(
                    historical_query.where(
                        or_(PredictionVersion.run_id.is_(None), PredictionVersion.run_id != run_id)
                    )
                    .order_by(PredictionVersion.created_at.desc())
                    .limit(5)
                )
            ).all()
        )

        context_parts: list[str] = []
        if rule_accuracies:
            context_parts.append("## 历史规则准确率（基于过往验证）")
            for ra in rule_accuracies[:10]:
                context_parts.append(
                    f"- 规则 {ra.rule_id}: 准确率 {ra.accuracy_score:.1%} "
                    f"(验证{ra.total_predictions}次, 对{ra.confirmed}次, "
                    f"错{ra.refuted}次, 部分对{ra.partial}次)"
                )
            context_parts.append(
                "准确率高的规则应给予更高权重，准确率低的规则应谨慎使用或标记不确定性。"
            )

        if historical_versions:
            context_parts.append("\n## 同主题历史预测（供参考）")
            for hv in historical_versions:
                status_label = (
                    "[SUPERSEDED]"
                    if hv.status == "SUPERSEDED"
                    else "[ACTIVE]"
                    if hv.status == "ACTIVE"
                    else "[UNKNOWN]"
                )
                context_parts.append(
                    f"- {status_label} v{hv.version_number}: {hv.prediction_text[:200]} "
                    f"(概率:{hv.probability:.0%}, 置信度:{hv.confidence:.0%}, 触发:{hv.trigger_type})"
                )
            context_parts.append(
                "请参考历史预测的验证结果，避免重复已知错误，强化已验证的正确判断。"
            )

        rule_weights = {
            ra.rule_id: float(ra.weight_multiplier if ra.weight_multiplier is not None else 1.0)
            for ra in rule_accuracies
        }
        cal_ctx = PredictionCalibrationContext(
            run_id=run_id,
            historical_versions_injected=len(historical_versions),
            rule_weights_applied={
                ra.rule_id: rule_weights[ra.rule_id] for ra in rule_accuracies[:20]
            },
            confidence_adjustment=0.0,
        )
        session.add(cal_ctx)
        await session.flush()

        return {
            "context_text": "\n".join(context_parts),
            "rule_weights": rule_weights,
            "historical_count": len(historical_versions),
            "context_record_id": cal_ctx.id,
        }

    async def _apply_calibrated_confidence(
        self,
        session: AsyncSession,
        versions: list[Any],
        calibration_ctx: dict[str, Any],
    ) -> None:
        rule_weights = calibration_ctx.get("rule_weights") or {}
        if not versions or not rule_weights:
            return

        avg_weight = sum(float(weight) for weight in rule_weights.values()) / len(rule_weights)
        adjusted_versions = []
        for version in versions:
            original_confidence = float(version.confidence)
            adjusted_confidence = min(1.0, original_confidence * avg_weight)
            version.confidence = adjusted_confidence
            version.version_metadata = {
                **(version.version_metadata or {}),
                "calibration_avg_rule_weight": round(avg_weight, 4),
                "calibration_original_confidence": round(original_confidence, 4),
                "calibration_adjusted_confidence": round(adjusted_confidence, 4),
            }
            adjusted_versions.append(version)

        from planagent.domain.models import PredictionCalibrationContext

        context_record_id = calibration_ctx.get("context_record_id")
        if context_record_id:
            context_record = await session.get(PredictionCalibrationContext, context_record_id)
            if context_record is not None:
                context_record.prediction_version_id = adjusted_versions[0].id
                context_record.confidence_adjustment = round(avg_weight - 1.0, 4)

    async def _generate_decision_options(
        self,
        session: AsyncSession,
        run: SimulationRun,
        final_state: dict[str, float],
    ) -> None:
        from planagent.domain.models import DecisionOption, Hypothesis

        pack = registry.get(run.domain_id)
        decisions = list(
            (
                await session.scalars(
                    select(DecisionRecordRecord)
                    .where(DecisionRecordRecord.run_id == run.id)
                    .order_by(DecisionRecordRecord.tick.asc())
                )
            ).all()
        )
        if not decisions:
            return

        unique_actions: dict[str, DecisionRecordRecord] = {}
        for d in decisions:
            if d.action_id not in unique_actions:
                unique_actions[d.action_id] = d
        top_actions = list(unique_actions.values())[:3]

        existing_count = int(
            await session.scalar(
                select(func.count())
                .select_from(DecisionOption)
                .where(DecisionOption.run_id == run.id)
            )
        )
        if existing_count > 0:
            return

        for ranking, decision in enumerate(top_actions, start=1):
            action_spec = None
            for a in pack.action_library:
                if a.action_id == decision.action_id:
                    action_spec = a
                    break
            title = action_spec.description if action_spec else decision.action_id
            description = (
                decision.why_selected
                or f"Action {decision.action_id} selected at tick {decision.tick}."
            )
            expected_effects = dict(decision.expected_effect) if decision.expected_effect else {}
            risks: list[str] = []
            for metric, value in expected_effects.items():
                policy = _STATE_POLICIES.get(run.domain_id, {}).get(metric)
                if policy is not None:
                    if policy.preferred_direction == "increase" and value < -0.02:
                        risks.append(f"{metric} may decrease ({value:+.3f}).")
                    elif policy.preferred_direction == "decrease" and value > 0.02:
                        risks.append(f"{metric} may increase ({value:+.3f}).")
            confidence = round(
                min(0.95, max(0.3, 0.5 + len(decision.policy_rule_ids or []) * 0.1)), 2
            )
            conditions: list[str] = []
            if run.domain_id == "military" and final_state.get("escalation_index", 0) > 0.6:
                conditions.append("Escalation risk should be monitored if this option is pursued.")

            option = DecisionOption(
                run_id=run.id,
                tenant_id=run.tenant_id,
                preset_id=run.preset_id,
                title=title[:255],
                description=description[:2000],
                expected_effects=expected_effects,
                risks=risks,
                evidence_ids=decision.evidence_ids or [],
                confidence=confidence,
                conditions=conditions,
                ranking=ranking,
            )
            session.add(option)
            await session.flush()

            horizon = "1_week" if run.domain_id == "military" else "3_months"
            prediction = f"If '{decision.action_id}' continues, {', '.join(f'{k} will move toward {v:+.2f}' for k, v in list(expected_effects.items())[:3])}."
            hypothesis = Hypothesis(
                run_id=run.id,
                decision_option_id=option.id,
                tenant_id=run.tenant_id,
                preset_id=run.preset_id,
                prediction=prediction[:2000],
                time_horizon=horizon,
            )
            session.add(hypothesis)

    async def _record_external_shock(
        self,
        session: AsyncSession,
        run: SimulationRun,
        tick: int,
        claim: Claim,
    ) -> int:
        shocks = self._derive_shocks(run.domain_id, claim.statement, claim.evidence_item_id)
        for shock in shocks:
            session.add(
                ExternalShockRecord(
                    run_id=run.id,
                    tick=tick,
                    domain=run.domain_id,
                    shock_type=shock["shock_type"],
                    summary=shock["summary"],
                    evidence_ids=[claim.evidence_item_id],
                    payload=shock["payload"],
                )
            )
        return len(shocks)

    async def _fetch_relevant_claims(
        self,
        session: AsyncSession,
        run: SimulationRun,
    ) -> list[Claim]:
        tenant_id = normalize_tenant_id(run.tenant_id or run.configuration.get("tenant_id"))
        preset_id = run.preset_id or run.configuration.get("preset_id")
        query = select(Claim).where(Claim.status == ClaimStatus.ACCEPTED.value)
        if tenant_id is not None:
            query = query.where(Claim.tenant_id == tenant_id)
        if preset_id is not None:
            query = query.where(or_(Claim.preset_id == preset_id, Claim.preset_id.is_(None)))
        terms = await self._subject_terms(session, run)
        if terms:
            predicates = []
            for term in terms:
                lowered = term.lower()
                predicates.extend(
                    [
                        Claim.statement.ilike(f"%{lowered}%"),
                        Claim.subject.ilike(f"%{lowered}%"),
                        Claim.object_text.ilike(f"%{lowered}%"),
                    ]
                )
            query = query.where(or_(*predicates))

        claims = list((await session.scalars(query.order_by(Claim.created_at.asc()))).all())
        minimum_claims = max(4, run.tick_count)
        if len(claims) >= minimum_claims:
            return claims

        recent_query = select(Claim).where(Claim.status == ClaimStatus.ACCEPTED.value)
        if tenant_id is not None:
            recent_query = recent_query.where(Claim.tenant_id == tenant_id)
        if preset_id is not None:
            recent_query = recent_query.where(
                or_(Claim.preset_id == preset_id, Claim.preset_id.is_(None))
            )
        if claims:
            recent_query = recent_query.where(Claim.created_at >= claims[0].created_at)
        recent_claims = list(
            (await session.scalars(recent_query.order_by(Claim.created_at.asc()).limit(25))).all()
        )
        selected_by_id = {claim.id: claim for claim in claims}
        for claim in recent_claims:
            selected_by_id.setdefault(claim.id, claim)
            if len(selected_by_id) >= minimum_claims:
                break
        return list(selected_by_id.values())

    async def _claim_simulation_runs(
        self,
        session: AsyncSession,
        limit: int,
        worker_id: str,
    ) -> list[SimulationRun]:
        now = utc_now()
        lease_expires_at = now + timedelta(seconds=self.settings.worker_lease_seconds)
        candidate_ids = list(
            (
                await session.scalars(
                    select(SimulationRun.id)
                    .where(
                        or_(
                            SimulationRun.status == SimulationRunStatus.PENDING.value,
                            and_(
                                SimulationRun.status == SimulationRunStatus.PROCESSING.value,
                                or_(
                                    SimulationRun.lease_expires_at.is_(None),
                                    SimulationRun.lease_expires_at < now,
                                ),
                            ),
                        )
                    )
                    .order_by(SimulationRun.created_at.asc())
                    .limit(limit * 3)
                )
            ).all()
        )
        claimed: list[SimulationRun] = []
        for run_id in candidate_ids:
            result = await session.execute(
                update(SimulationRun)
                .where(
                    SimulationRun.id == run_id,
                    or_(
                        SimulationRun.status == SimulationRunStatus.PENDING.value,
                        and_(
                            SimulationRun.status == SimulationRunStatus.PROCESSING.value,
                            or_(
                                SimulationRun.lease_expires_at.is_(None),
                                SimulationRun.lease_expires_at < now,
                            ),
                        ),
                    ),
                )
                .values(
                    status=SimulationRunStatus.PROCESSING.value,
                    lease_owner=worker_id,
                    lease_expires_at=lease_expires_at,
                    processing_attempts=SimulationRun.processing_attempts + 1,
                    updated_at=now,
                )
            )
            if result.rowcount:
                run = await session.get(SimulationRun, run_id)
                if run is not None:
                    claimed.append(run)
            if len(claimed) >= limit:
                break
        return claimed

    async def _claim_report_runs(
        self,
        session: AsyncSession,
        limit: int,
        worker_id: str,
    ) -> list[SimulationRun]:
        now = utc_now()
        lease_expires_at = now + timedelta(seconds=self.settings.worker_lease_seconds)
        candidate_ids = list(
            (
                await session.scalars(
                    select(SimulationRun.id)
                    .outerjoin(GeneratedReport, GeneratedReport.run_id == SimulationRun.id)
                    .where(
                        SimulationRun.status == SimulationRunStatus.COMPLETED.value,
                        GeneratedReport.id.is_(None),
                        or_(
                            SimulationRun.lease_expires_at.is_(None),
                            SimulationRun.lease_expires_at < now,
                        ),
                    )
                    .order_by(SimulationRun.completed_at.asc(), SimulationRun.created_at.asc())
                    .limit(limit * 3)
                )
            ).all()
        )
        claimed: list[SimulationRun] = []
        for run_id in candidate_ids:
            result = await session.execute(
                update(SimulationRun)
                .where(
                    SimulationRun.id == run_id,
                    SimulationRun.status == SimulationRunStatus.COMPLETED.value,
                    or_(
                        SimulationRun.lease_expires_at.is_(None),
                        SimulationRun.lease_expires_at < now,
                    ),
                )
                .values(
                    lease_owner=worker_id,
                    lease_expires_at=lease_expires_at,
                    processing_attempts=SimulationRun.processing_attempts + 1,
                    updated_at=now,
                )
            )
            if result.rowcount:
                run = await session.get(SimulationRun, run_id)
                if run is not None:
                    claimed.append(run)
            if len(claimed) >= limit:
                break
        return claimed
