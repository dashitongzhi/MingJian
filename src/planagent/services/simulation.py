from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import timedelta
import re
from typing import Any

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from planagent.config import Settings
from planagent.domain.api import ScenarioRunCreate, SimulationRunCreate
from planagent.domain.enums import ClaimStatus, EventTopic, ExecutionMode, SimulationRunStatus
from planagent.domain.models import (
    Claim,
    CompanyProfile,
    DecisionRecordRecord,
    EventArchive,
    ExternalShockRecord,
    ForceProfile,
    GeoAssetRecord,
    GeneratedReport,
    ScenarioBranchRecord,
    SimulationRun,
    StateSnapshotRecord,
    generate_id,
    utc_now,
)
from planagent.events.bus import EventBus
from planagent.services.openai_client import OpenAIService
from planagent.services.pipeline import normalize_text
from planagent.services.reporting import ReportService
from planagent.services.simulation_branching import (
    _STATE_POLICIES,
    MetricPolicy,
    build_branch_trajectory,
    build_scenario_compare_summary,
    score_branch_delta,
    summarize_branch_trajectory,
)
from planagent.services.simulation_military import MilitaryCombatResolver
from planagent.services.startup import normalize_tenant_id, startup_preset_config
from planagent.simulation.domain_packs import registry
from planagent.simulation.rules import RuleRegistry, RuleSpec


@dataclass(frozen=True)
class SelectedAction:
    action_id: str
    why_selected: str
    rule_ids: list[str]
    evidence_ids: list[str]
    expected_effect: dict[str, float]
    actual_effect: dict[str, float]
    decision_method: str = "rule_engine"


@dataclass(frozen=True)
class RuleScore:
    rule: RuleSpec
    claim: Claim
    score: float
    matched_keywords: tuple[str, ...]


@dataclass
class ActionCandidate:
    action_id: str
    rule_scores: list[RuleScore] = field(default_factory=list)
    base_score: float = 0.0
    state_adjustment: float = 0.0
    history_penalty: float = 0.0

    @property
    def total_score(self) -> float:
        return round(self.base_score + self.state_adjustment - self.history_penalty, 4)


@dataclass(frozen=True)
class OperationalResponse:
    action_id: str
    why_selected: str
    effects: dict[str, float]


@dataclass(frozen=True)
class MilitaryResolution:
    actual_effect: dict[str, float]
    enemy_action_id: str
    enemy_reason: str
    fire_balance: float
    objective_delta: float
    supply_delta: float
    recovery_delta: float


_DECISION_EVIDENCE_WINDOW = 3
_DECISION_RECENCY_WEIGHTS = (1.0, 0.65, 0.45)
_DECISION_MIN_SCORE = 0.6
class SimulationService:
    def __init__(
        self,
        settings: Settings,
        event_bus: EventBus,
        rule_registry: RuleRegistry,
        openai_service: OpenAIService | None = None,
    ) -> None:
        self.settings = settings
        self.event_bus = event_bus
        self.rule_registry = rule_registry
        self.openai_service = openai_service
        self.report_service = ReportService(openai_service)
        self._military = MilitaryCombatResolver()

    async def create_simulation_run(
        self,
        session: AsyncSession,
        payload: SimulationRunCreate,
    ) -> SimulationRun:
        execution_mode = payload.execution_mode or (
            ExecutionMode.INLINE if self.settings.inline_simulation_default else ExecutionMode.QUEUED
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

    async def create_scenario_run(
        self,
        session: AsyncSession,
        parent_run_id: str,
        payload: ScenarioRunCreate,
    ) -> ScenarioBranchRecord:
        parent_run = await session.get(SimulationRun, parent_run_id)
        if parent_run is None:
            raise LookupError(f"Simulation run {parent_run_id} was not found.")
        if parent_run.status != SimulationRunStatus.COMPLETED.value:
            raise ValueError("Scenario branching requires a completed baseline run.")
        if parent_run.domain_id == "military":
            if parent_run.force_id is None:
                raise ValueError("Military scenario branching requires a force-backed baseline run.")
        elif parent_run.domain_id == "corporate":
            if parent_run.company_id is None:
                raise ValueError("Corporate scenario branching requires a company-backed baseline run.")
        else:
            raise ValueError(f"Scenario branching is not implemented for domain {parent_run.domain_id}.")

        fork_step = payload.fork_step or max(1, parent_run.tick_count // 2)
        source_snapshot = (
            await session.scalars(
                select(StateSnapshotRecord)
                .where(
                    and_(
                        StateSnapshotRecord.run_id == parent_run.id,
                        StateSnapshotRecord.tick == fork_step,
                    )
                )
                .limit(1)
            )
        ).first()
        if source_snapshot is None:
            raise LookupError(f"No state snapshot found at fork step {fork_step} for run {parent_run.id}.")

        scenario_id = generate_id()
        execution_mode = (
            parent_run.execution_mode
            if parent_run.execution_mode in {ExecutionMode.INLINE.value, ExecutionMode.QUEUED.value}
            else ExecutionMode.INLINE.value
        )
        remaining_ticks = max(1, parent_run.tick_count - fork_step)
        run = SimulationRun(
            company_id=parent_run.company_id,
            force_id=parent_run.force_id,
            tenant_id=parent_run.tenant_id,
            preset_id=parent_run.preset_id,
            domain_id=parent_run.domain_id,
            actor_template=parent_run.actor_template,
            military_use_mode=parent_run.military_use_mode,
            parent_run_id=parent_run.id,
            execution_mode=execution_mode,
            status=SimulationRunStatus.PENDING.value,
            tick_count=payload.tick_count or remaining_ticks,
            seed=parent_run.seed,
            configuration={
                **parent_run.configuration,
                "initial_state": {
                    **source_snapshot.state,
                    **{key: float(value) for key, value in payload.state_overrides.items()},
                },
                "scenario": {
                    "id": scenario_id,
                    "fork_step": fork_step,
                    "assumptions": payload.assumptions,
                    "decision_deltas": payload.decision_deltas,
                    "state_overrides": payload.state_overrides,
                    "probability_band": payload.probability_band,
                },
                "military_use_mode": parent_run.military_use_mode,
            },
            summary={"scenario_id": scenario_id},
        )
        session.add(run)
        await session.flush()
        if parent_run.domain_id == "military":
            await self._clone_geo_assets_for_scenario(session, parent_run.id, run)

        branch = ScenarioBranchRecord(
            id=scenario_id,
            run_id=run.id,
            parent_run_id=parent_run.id,
            fork_step=fork_step,
            assumptions=payload.assumptions,
            decision_deltas=payload.decision_deltas,
            kpi_trajectory=[],
            probability_band=payload.probability_band,
            notable_events=[],
            evidence_summary=self._build_evidence_summary(parent_run),
        )
        session.add(branch)
        await session.flush()
        parent_run.summary = {
            **parent_run.summary,
            "scenario_branch_ids": sorted(
                {*(parent_run.summary.get("scenario_branch_ids", [])), branch.id}
            ),
        }

        if execution_mode == ExecutionMode.INLINE.value:
            await self._execute_run(session, run)
            await self._refresh_scenario_branch(session, branch, parent_run, run)
            await self._generate_report(session, run)

        await session.commit()
        await session.refresh(branch)
        return branch

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

    async def generate_pending_reports(
        self,
        session: AsyncSession,
        limit: int = 10,
        worker_id: str | None = None,
    ) -> int:
        runs = await self._claim_report_runs(
            session,
            limit=limit,
            worker_id=worker_id or "report-worker",
        )
        generated = 0
        for run in runs:
            try:
                await self._generate_report(session, run)
                run.last_error = None
                generated += 1
            except Exception as exc:
                run.last_error = f"{type(exc).__name__}: {normalize_text(str(exc))[:300]}"
            finally:
                run.lease_owner = None
                run.lease_expires_at = None
                run.updated_at = utc_now()
        await session.commit()
        return generated

    async def list_decision_trace(
        self,
        session: AsyncSession,
        run_id: str,
    ) -> list[DecisionRecordRecord]:
        return list(
            (
                await session.scalars(
                    select(DecisionRecordRecord)
                    .where(DecisionRecordRecord.run_id == run_id)
                    .order_by(DecisionRecordRecord.tick.asc(), DecisionRecordRecord.sequence.asc())
                )
            ).all()
        )

    async def latest_company_report(
        self,
        session: AsyncSession,
        company_id: str,
        tenant_id: str | None = None,
    ) -> GeneratedReport | None:
        normalized_tenant = normalize_tenant_id(tenant_id)
        query = select(GeneratedReport).where(GeneratedReport.company_id == company_id)
        if normalized_tenant is not None:
            query = query.where(GeneratedReport.tenant_id == normalized_tenant)
        return (
            await session.scalars(
                query.order_by(GeneratedReport.created_at.desc())
            )
        ).first()

    async def latest_military_report(
        self,
        session: AsyncSession,
        scenario_id: str,
    ) -> GeneratedReport | None:
        return await self.latest_scenario_report(session, scenario_id)

    async def latest_scenario_report(
        self,
        session: AsyncSession,
        scenario_id: str,
    ) -> GeneratedReport | None:
        return (
            await session.scalars(
                select(GeneratedReport)
                .where(GeneratedReport.scenario_id == scenario_id)
                .order_by(GeneratedReport.created_at.desc())
            )
        ).first()

    async def get_scenario_branch(
        self,
        session: AsyncSession,
        scenario_id: str,
    ) -> ScenarioBranchRecord | None:
        return await session.get(ScenarioBranchRecord, scenario_id)

    async def list_geo_assets(
        self,
        session: AsyncSession,
        run_id: str,
    ) -> list[GeoAssetRecord]:
        return list(
            (
                await session.scalars(
                    select(GeoAssetRecord)
                    .where(GeoAssetRecord.run_id == run_id)
                    .order_by(GeoAssetRecord.asset_type.asc(), GeoAssetRecord.name.asc())
                )
            ).all()
        )

    async def list_external_shocks(
        self,
        session: AsyncSession,
        run_id: str,
    ) -> list[ExternalShockRecord]:
        return list(
            (
                await session.scalars(
                    select(ExternalShockRecord)
                    .where(ExternalShockRecord.run_id == run_id)
                    .order_by(ExternalShockRecord.tick.asc(), ExternalShockRecord.created_at.asc())
                )
            ).all()
        )

    async def build_scenario_compare(
        self,
        session: AsyncSession,
        run_id: str,
    ) -> dict[str, Any]:
        run = await session.get(SimulationRun, run_id)
        if run is None:
            raise LookupError(f"Simulation run {run_id} was not found.")

        baseline_run = run
        if run.parent_run_id is not None:
            parent_run = await session.get(SimulationRun, run.parent_run_id)
            if parent_run is not None:
                baseline_run = parent_run

        branch_records = list(
            (
                await session.scalars(
                    select(ScenarioBranchRecord)
                    .where(ScenarioBranchRecord.parent_run_id == baseline_run.id)
                    .order_by(ScenarioBranchRecord.created_at.asc())
                )
            ).all()
        )
        baseline_state_record = await self._load_latest_state(session, baseline_run.id)
        baseline_final_state = (
            {key: float(value) for key, value in baseline_state_record.state.items()}
            if baseline_state_record is not None
            else {}
        )
        baseline_report = await self._latest_run_report(session, baseline_run.id)
        metric_names = sorted(
            {
                metric["metric"]
                for branch in branch_records
                for metric in branch.kpi_trajectory
                if "metric" in metric
            }
            | set(baseline_final_state.keys())
        )
        subject_name = await self._scenario_subject_name(session, baseline_run)
        branches: list[dict[str, Any]] = []
        best_branch_id: str | None = None
        best_branch_score = 0.0
        for branch in branch_records:
            branch_run = await session.get(SimulationRun, branch.run_id)
            branch_report = await self.latest_scenario_report(session, branch.id)
            branch_final_state = (
                {
                    key: float(value)
                    for key, value in (branch_run.summary.get("final_state", {}) if branch_run is not None else {}).items()
                }
                if branch_run is not None
                else {}
            )
            branch_score = score_branch_delta(
                baseline_run.domain_id,
                baseline_final_state,
                branch_final_state,
            )
            key_deltas = summarize_branch_trajectory(
                baseline_run.domain_id,
                branch.kpi_trajectory,
            )
            recommendation_summary = self._report_recommendations(branch_report)
            if branch_score > best_branch_score:
                best_branch_score = branch_score
                best_branch_id = branch.id
            branches.append(
                {
                    "branch_id": branch.id,
                    "run_id": branch.run_id,
                    "fork_step": branch.fork_step,
                    "probability_band": branch.probability_band,
                    "assumptions": branch.assumptions,
                    "decision_deltas": branch.decision_deltas,
                    "notable_events": branch.notable_events,
                    "kpi_trajectory": branch.kpi_trajectory,
                    "matched_rules": branch_run.summary.get("matched_rules", []) if branch_run is not None else [],
                    "report_id": branch_report.id if branch_report is not None else None,
                    "final_state": branch_final_state,
                    "branch_score": round(branch_score, 4),
                    "key_deltas": key_deltas,
                    "recommendation_summary": recommendation_summary,
                    "debate_suggestion": {
                        "run_id": branch.run_id,
                        "topic": f"Should {subject_name} adopt scenario branch {branch.id} over the baseline plan?",
                        "trigger_type": "branch_evaluation",
                        "target_type": "branch",
                        "target_id": branch.id,
                        "context_lines": [
                            *(key_deltas[:2] or ["Compare this branch against the baseline outcome."]),
                            *recommendation_summary[:1],
                        ],
                    },
                }
            )
        summary = build_scenario_compare_summary(
            baseline_run.domain_id,
            branches,
            best_branch_id,
            best_branch_score,
        )
        return {
            "baseline_run_id": baseline_run.id,
            "domain_id": baseline_run.domain_id,
            "branch_count": len(branches),
            "metric_names": metric_names,
            "baseline_final_state": baseline_final_state,
            "baseline_report_id": baseline_report.id if baseline_report is not None else None,
            "baseline_recommendations": self._report_recommendations(baseline_report),
            "recommended_branch_id": best_branch_id if best_branch_score > 0.08 else None,
            "summary": summary,
            "branches": branches,
        }

    async def _latest_run_report(
        self,
        session: AsyncSession,
        run_id: str,
    ) -> GeneratedReport | None:
        return (
            await session.scalars(
                select(GeneratedReport)
                .where(GeneratedReport.run_id == run_id)
                .order_by(GeneratedReport.created_at.desc())
                .limit(1)
            )
        ).first()

    async def _scenario_subject_name(
        self,
        session: AsyncSession,
        run: SimulationRun,
    ) -> str:
        if run.company_id is not None:
            company = await session.get(CompanyProfile, run.company_id)
            if company is not None:
                return company.name
        if run.force_id is not None:
            force = await session.get(ForceProfile, run.force_id)
            if force is not None:
                return force.name
        return self._subject_id(run)

    def _report_recommendations(self, report: GeneratedReport | None) -> list[str]:
        if report is None:
            return []
        recommendations = report.sections.get("strategy_recommendations", [])
        return [str(item) for item in recommendations[:3]]

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

    async def _generate_report(self, session: AsyncSession, run: SimulationRun) -> GeneratedReport:
        report = await self.report_service.generate_report(session, run)
        run.summary = {**run.summary, "report_id": report.id}
        payload = {
            "run_id": run.id,
            "report_id": report.id,
            "company_id": run.company_id,
            "force_id": run.force_id,
            "scenario_id": report.scenario_id,
        }
        session.add(EventArchive(topic=EventTopic.REPORT_GENERATED.value, payload=payload))
        await self.event_bus.publish(EventTopic.REPORT_GENERATED.value, payload)
        return report

    async def _execute_run(self, session: AsyncSession, run: SimulationRun) -> None:
        run.status = SimulationRunStatus.PROCESSING.value
        run.updated_at = utc_now()

        pack = registry.get(run.domain_id)
        initial_state = self._resolve_initial_state(pack, run.actor_template)
        initial_state.update(
            {
                key: float(value)
                for key, value in run.configuration.get("initial_state", {}).items()
            }
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
        geo_assets = await self.list_geo_assets(session, run.id) if run.domain_id == "military" else []

        session.add(StateSnapshotRecord(run_id=run.id, tick=0, actor_id=actor_id, state=deepcopy(current_state)))

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
                            "critical_objective_id": operational_picture["objective_network"].get("critical_objective_id"),
                            "critical_route_id": operational_picture["objective_network"].get("critical_route_id"),
                            "contested_asset_ids": operational_picture["objective_network"].get("contested_asset_ids", []),
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
                enemy_action_id=military_tick_summaries[-1]["enemy_action_id"] if military_tick_summaries else None,
                enemy_reason=military_tick_summaries[-1]["enemy_reason"] if military_tick_summaries else None,
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
            "military_tick_summaries": military_tick_summaries if run.domain_id == "military" else [],
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
                select(func.count()).select_from(DecisionOption).where(DecisionOption.run_id == run.id)
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
            description = decision.why_selected or f"Action {decision.action_id} selected at tick {decision.tick}."
            expected_effects = dict(decision.expected_effect) if decision.expected_effect else {}
            risks: list[str] = []
            for metric, value in expected_effects.items():
                policy = _STATE_POLICIES.get(run.domain_id, {}).get(metric)
                if policy is not None:
                    if policy.preferred_direction == "increase" and value < -0.02:
                        risks.append(f"{metric} may decrease ({value:+.3f}).")
                    elif policy.preferred_direction == "decrease" and value > 0.02:
                        risks.append(f"{metric} may increase ({value:+.3f}).")
            confidence = round(min(0.95, max(0.3, 0.5 + len(decision.policy_rule_ids or []) * 0.1)), 2)
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

    async def _refresh_scenario_branch(
        self,
        session: AsyncSession,
        branch: ScenarioBranchRecord,
        parent_run: SimulationRun,
        branch_run: SimulationRun,
    ) -> None:
        parent_final = await self._load_latest_state(session, parent_run.id)
        branch_final = await self._load_latest_state(session, branch_run.id)
        if branch_final is None:
            return

        branch.kpi_trajectory = build_branch_trajectory(
            branch_run.domain_id,
            parent_final.state if parent_final is not None else {},
            branch_final.state,
        )
        shocks = await self.list_external_shocks(session, branch_run.id)
        branch.notable_events = [shock.summary for shock in shocks[:3]] or [
            f"Scenario matched {rule_id}" for rule_id in branch_run.summary.get("matched_rules", [])[:3]
        ]
        if not branch.decision_deltas:
            branch.decision_deltas = await self._derive_decision_deltas(
                session,
                parent_run.id,
                branch_run.id,
                branch.fork_step,
            )
        branch.evidence_summary = self._build_evidence_summary(branch_run)

    async def _load_latest_state(
        self,
        session: AsyncSession,
        run_id: str,
    ) -> StateSnapshotRecord | None:
        return (
            await session.scalars(
                select(StateSnapshotRecord)
                .where(StateSnapshotRecord.run_id == run_id)
                .order_by(StateSnapshotRecord.tick.desc())
                .limit(1)
            )
        ).first()

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

    def _derive_shocks(
        self,
        domain_id: str,
        statement: str,
        evidence_id: str,
    ) -> list[dict[str, Any]]:
        lowered = statement.lower()
        shocks: list[dict[str, Any]] = []
        if domain_id == "corporate":
            if any(keyword in lowered for keyword in ["cost", "price", "gpu"]):
                shocks.append(
                    {
                        "shock_type": "market_cost_pressure",
                        "summary": normalize_text(statement),
                        "payload": {"matched_keywords": ["cost", "price", "gpu"], "evidence_id": evidence_id},
                    }
                )
            if any(keyword in lowered for keyword in ["ship", "launch", "release"]):
                shocks.append(
                    {
                        "shock_type": "product_launch",
                        "summary": normalize_text(statement),
                        "payload": {"matched_keywords": ["ship", "launch", "release"], "evidence_id": evidence_id},
                    }
                )
            if any(keyword in lowered for keyword in ["demand", "adoption", "growth"]):
                shocks.append(
                    {
                        "shock_type": "demand_shift",
                        "summary": normalize_text(statement),
                        "payload": {"matched_keywords": ["demand", "adoption", "growth"], "evidence_id": evidence_id},
                    }
                )
            if any(keyword in lowered for keyword in ["bundled", "native", "copilot", "platform", "workspace"]):
                shocks.append(
                    {
                        "shock_type": "platform_bundling_pressure",
                        "summary": normalize_text(statement),
                        "payload": {
                            "matched_keywords": ["bundled", "native", "copilot", "platform", "workspace"],
                            "evidence_id": evidence_id,
                        },
                    }
                )
            if any(keyword in lowered for keyword in ["security", "compliance", "procurement", "integration", "pilot"]):
                shocks.append(
                    {
                        "shock_type": "enterprise_buying_friction",
                        "summary": normalize_text(statement),
                        "payload": {
                            "matched_keywords": ["security", "compliance", "procurement", "integration", "pilot"],
                            "evidence_id": evidence_id,
                        },
                    }
                )
            if any(keyword in lowered for keyword in ["hallucination", "latency", "outage", "accuracy", "reliability"]):
                shocks.append(
                    {
                        "shock_type": "reliability_incident",
                        "summary": normalize_text(statement),
                        "payload": {
                            "matched_keywords": ["hallucination", "latency", "outage", "accuracy", "reliability"],
                            "evidence_id": evidence_id,
                        },
                    }
                )
            if any(keyword in lowered for keyword in ["roi", "renewal", "expansion", "savings", "hours"]):
                shocks.append(
                    {
                        "shock_type": "validated_roi",
                        "summary": normalize_text(statement),
                        "payload": {
                            "matched_keywords": ["roi", "renewal", "expansion", "savings", "hours"],
                            "evidence_id": evidence_id,
                        },
                    }
                )
            return shocks

        if any(keyword in lowered for keyword in ["supply", "bridge", "port", "convoy"]):
            shocks.append(
                {
                    "shock_type": "supply_disruption",
                    "summary": normalize_text(statement),
                    "payload": {"matched_keywords": ["supply", "bridge", "port", "convoy"], "evidence_id": evidence_id},
                }
            )
        if any(keyword in lowered for keyword in ["weather", "storm", "fog", "mud"]):
            shocks.append(
                {
                    "shock_type": "weather_window",
                    "summary": normalize_text(statement),
                    "payload": {"matched_keywords": ["weather", "storm", "fog", "mud"], "evidence_id": evidence_id},
                }
            )
        if any(keyword in lowered for keyword in ["drone", "swarm", "strike", "airspace"]):
            shocks.append(
                {
                    "shock_type": "air_attack",
                    "summary": normalize_text(statement),
                    "payload": {"matched_keywords": ["drone", "swarm", "strike", "airspace"], "evidence_id": evidence_id},
                }
            )
        if any(keyword in lowered for keyword in ["isr", "satellite", "recon", "radar"]):
            shocks.append(
                {
                    "shock_type": "isr_window",
                    "summary": normalize_text(statement),
                    "payload": {"matched_keywords": ["isr", "satellite", "recon", "radar"], "evidence_id": evidence_id},
                }
            )
        if any(keyword in lowered for keyword in ["jam", "electronic", "cyber"]):
            shocks.append(
                {
                    "shock_type": "electronic_attack",
                    "summary": normalize_text(statement),
                    "payload": {"matched_keywords": ["jam", "electronic", "cyber"], "evidence_id": evidence_id},
                }
            )
        return shocks

    async def _ensure_geo_assets_for_run(
        self,
        session: AsyncSession,
        run: SimulationRun,
        force: ForceProfile,
    ) -> None:
        existing = (
            await session.scalars(select(GeoAssetRecord).where(GeoAssetRecord.run_id == run.id).limit(1))
        ).first()
        if existing is not None:
            return
        base_latitude, base_longitude = self._base_coordinates_for_theater(force.theater)
        for seed in self._build_geo_asset_seed_data(run.actor_template):
            session.add(
                GeoAssetRecord(
                    run_id=run.id,
                    force_id=force.id,
                    name=seed["name"],
                    asset_type=seed["asset_type"],
                    latitude=round(base_latitude + seed["latitude_offset"], 4),
                    longitude=round(base_longitude + seed["longitude_offset"], 4),
                    properties=self._decorate_asset_properties(run, seed["asset_type"], seed["properties"]),
                )
            )

    async def _clone_geo_assets_for_scenario(
        self,
        session: AsyncSession,
        parent_run_id: str,
        child_run: SimulationRun,
    ) -> None:
        parent_assets = list(
            (
                await session.scalars(
                    select(GeoAssetRecord)
                    .where(GeoAssetRecord.run_id == parent_run_id)
                    .order_by(GeoAssetRecord.asset_type.asc(), GeoAssetRecord.name.asc())
                )
            ).all()
        )
        if not parent_assets:
            force = await session.get(ForceProfile, child_run.force_id)
            if force is not None:
                await self._ensure_geo_assets_for_run(session, child_run, force)
            return
        for asset in parent_assets:
            session.add(
                GeoAssetRecord(
                    run_id=child_run.id,
                    force_id=child_run.force_id,
                    name=asset.name,
                    asset_type=asset.asset_type,
                    latitude=asset.latitude,
                    longitude=asset.longitude,
                    properties=self._decorate_asset_properties(
                        child_run,
                        asset.asset_type,
                        {
                            **asset.properties,
                            "parent_run_id": parent_run_id,
                        },
                    ),
                )
            )

    def _base_coordinates_for_theater(self, theater: str) -> tuple[float, float]:
        lookup = {
            "eastern-sector": (48.4800, 37.9400),
            "northern-front": (50.1200, 36.2700),
            "coastal-belt": (46.6200, 31.1000),
            "desert-corridor": (33.5100, 36.2900),
        }
        normalized = theater.strip().lower()
        return lookup.get(normalized, (35.0000, 35.0000))

    def _build_geo_asset_seed_data(self, actor_template: str) -> list[dict[str, Any]]:
        shared = [
            {
                "name": "Primary Supply Hub",
                "asset_type": "supply_hub",
                "latitude_offset": 0.0000,
                "longitude_offset": 0.0000,
                "properties": {"role": "logistics", "coverage_radius_km": 18},
            },
            {
                "name": "River Crossing Bridge",
                "asset_type": "bridge",
                "latitude_offset": 0.1200,
                "longitude_offset": -0.0800,
                "properties": {"role": "mobility", "coverage_radius_km": 6},
            },
            {
                "name": "Eastern Supply Corridor",
                "asset_type": "supply_route",
                "latitude_offset": 0.0800,
                "longitude_offset": -0.0300,
                "properties": {"role": "route_network", "route_id": "corridor-east", "connected_to": ["Primary Supply Hub", "River Crossing Bridge"]},
            },
            {
                "name": "Civilian District Alpha",
                "asset_type": "civilian_area",
                "latitude_offset": -0.0900,
                "longitude_offset": 0.1100,
                "properties": {"role": "protection", "population_index": 0.72},
            },
            {
                "name": "Objective Bastion",
                "asset_type": "objective_zone",
                "latitude_offset": 0.0400,
                "longitude_offset": 0.1200,
                "properties": {"role": "decisive_terrain", "objective_id": "bastion", "connected_to": ["Civilian District Alpha", "Command Post Echo"]},
            },
            {
                "name": "Command Post Echo",
                "asset_type": "command_post",
                "latitude_offset": 0.0600,
                "longitude_offset": 0.0400,
                "properties": {"role": "c2", "coverage_radius_km": 10},
            },
        ]
        if actor_template == "air_defense_battalion":
            return [
                *shared,
                {
                    "name": "Air Defense Belt",
                    "asset_type": "air_defense_site",
                    "latitude_offset": -0.0300,
                    "longitude_offset": -0.1400,
                    "properties": {"role": "counter_drone", "coverage_radius_km": 26},
                },
                {
                    "name": "Radar Ridge",
                    "asset_type": "isr_node",
                    "latitude_offset": 0.1700,
                    "longitude_offset": 0.0900,
                    "properties": {"role": "early_warning", "coverage_radius_km": 32},
                },
            ]
        return [
            *shared,
            {
                "name": "Staging Area Bravo",
                "asset_type": "staging_area",
                "latitude_offset": -0.1300,
                "longitude_offset": -0.0200,
                "properties": {"role": "maneuver", "coverage_radius_km": 14},
            },
            {
                "name": "ISR Ridge",
                "asset_type": "isr_node",
                "latitude_offset": 0.1800,
                "longitude_offset": 0.0700,
                "properties": {"role": "observation", "coverage_radius_km": 28},
            },
        ]

    def _decorate_asset_properties(
        self,
        run: SimulationRun,
        asset_type: str,
        base_properties: dict[str, Any],
    ) -> dict[str, Any]:
        state = run.configuration.get("initial_state", {})
        properties = {
            **base_properties,
            "theater": run.configuration.get("theater"),
            "scenario_id": run.summary.get("scenario_id"),
            "status": "active",
        }
        if asset_type in {"supply_hub", "bridge"} and float(state.get("logistics_throughput", 1.0)) < 0.8:
            properties["status"] = "contested"
        if asset_type == "supply_route" and float(state.get("supply_network", 0.84)) < 0.78:
            properties["status"] = "contested"
        if asset_type == "civilian_area" and float(state.get("civilian_risk", 0.0)) > 0.55:
            properties["status"] = "at_risk"
        if asset_type == "objective_zone" and float(state.get("objective_control", 0.5)) < 0.5:
            properties["status"] = "contested"
        if asset_type in {"air_defense_site", "command_post"} and float(state.get("air_defense", 1.0)) < 0.85:
            properties["status"] = "degraded"
        return properties

    async def _derive_decision_deltas(
        self,
        session: AsyncSession,
        parent_run_id: str,
        branch_run_id: str,
        fork_step: int,
    ) -> list[str]:
        parent_records = list(
            (
                await session.scalars(
                    select(DecisionRecordRecord)
                    .where(
                        and_(
                            DecisionRecordRecord.run_id == parent_run_id,
                            DecisionRecordRecord.tick > fork_step,
                        )
                    )
                    .order_by(DecisionRecordRecord.tick.asc())
                )
            ).all()
        )
        branch_records = list(
            (
                await session.scalars(
                    select(DecisionRecordRecord)
                    .where(DecisionRecordRecord.run_id == branch_run_id)
                    .order_by(DecisionRecordRecord.tick.asc())
                )
            ).all()
        )
        deltas: list[str] = []
        for index, branch_record in enumerate(branch_records):
            parent_action = parent_records[index].action_id if index < len(parent_records) else None
            if branch_record.action_id != parent_action:
                baseline_action = parent_action or "no baseline action"
                deltas.append(
                    f"Tick {branch_record.tick}: scenario chose {branch_record.action_id} instead of {baseline_action}."
                )
        return deltas or ["Scenario followed the baseline action sequence after the fork point."]

    async def _upsert_company(self, session: AsyncSession, payload: SimulationRunCreate) -> CompanyProfile:
        assert payload.company_id is not None
        assert payload.company_name is not None
        company = await session.get(CompanyProfile, payload.company_id)
        if company is None:
            company = CompanyProfile(
                id=payload.company_id,
                name=payload.company_name,
                market=payload.market,
                attributes={"actor_template": payload.actor_template},
            )
            session.add(company)
            await session.flush()
            return company

        company.name = payload.company_name
        company.market = payload.market
        company.attributes = {
            **company.attributes,
            "actor_template": payload.actor_template,
        }
        company.updated_at = utc_now()
        return company

    async def _upsert_force(self, session: AsyncSession, payload: SimulationRunCreate) -> ForceProfile:
        assert payload.force_id is not None
        assert payload.force_name is not None
        force = await session.get(ForceProfile, payload.force_id)
        if force is None:
            force = ForceProfile(
                id=payload.force_id,
                name=payload.force_name,
                theater=payload.theater or "unknown-theater",
                attributes={"actor_template": payload.actor_template},
            )
            session.add(force)
            await session.flush()
            return force

        force.name = payload.force_name
        force.theater = payload.theater or force.theater
        force.attributes = {
            **force.attributes,
            "actor_template": payload.actor_template,
        }
        force.updated_at = utc_now()
        return force

    def _resolve_initial_state(self, pack: Any, actor_template: str) -> dict[str, float]:
        default_state = {field.name: float(field.default) for field in pack.state_fields}
        template_map = {template.actor_type: template.default_state for template in pack.actor_templates}
        return {
            **default_state,
            **{key: float(value) for key, value in template_map.get(actor_template, {}).items()},
        }

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
            recent_query = recent_query.where(or_(Claim.preset_id == preset_id, Claim.preset_id.is_(None)))
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
                                or_(SimulationRun.lease_expires_at.is_(None), SimulationRun.lease_expires_at < now),
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
                            or_(SimulationRun.lease_expires_at.is_(None), SimulationRun.lease_expires_at < now),
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
                        or_(SimulationRun.lease_expires_at.is_(None), SimulationRun.lease_expires_at < now),
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
                    or_(SimulationRun.lease_expires_at.is_(None), SimulationRun.lease_expires_at < now),
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

    async def _subject_terms(self, session: AsyncSession, run: SimulationRun) -> list[str]:
        if run.domain_id == "corporate" and run.company_id:
            company = await session.get(CompanyProfile, run.company_id)
            if company is None:
                return []
            return [company.name, company.id, *self._expand_market_terms(company.market)]
        if run.domain_id == "military" and run.force_id:
            force = await session.get(ForceProfile, run.force_id)
            if force is None:
                return []
            return [force.name, force.id, force.theater]
        return []

    def _expand_market_terms(self, market: str) -> list[str]:
        normalized = normalize_text(market)
        if not normalized:
            return []

        terms = [normalized]
        for token in re.split(r"[^a-z0-9]+", normalized.lower()):
            if len(token) >= 4:
                terms.append(token)
        return list(dict.fromkeys(terms))

    def _subject_id(self, run: SimulationRun) -> str:
        return run.company_id or run.force_id or run.id

    def _build_evidence_summary(self, run: SimulationRun) -> str:
        statements = run.summary.get("evidence_statements", [])
        if not statements:
            return "No accepted evidence was linked to this run."
        return " | ".join(statements[:3])

    def _apply_external_shock(self, domain_id: str, state: dict[str, float], statement: str) -> None:
        lowered = statement.lower()
        if domain_id == "corporate":
            if any(keyword in lowered for keyword in ["cost", "price", "gpu"]):
                state["infra_cost_index"] = state.get("infra_cost_index", 1.0) + 0.08
                state["runway_weeks"] = state.get("runway_weeks", 52.0) - 2.0
                state["gross_margin"] = state.get("gross_margin", 0.62) - 0.05
                state["pipeline"] = state.get("pipeline", 1.0) - 0.02
            if any(keyword in lowered for keyword in ["ship", "launch", "release"]):
                state["brand_index"] = state.get("brand_index", 1.0) + 0.05
                state["market_share"] = state.get("market_share", 0.05) + 0.01
                state["pipeline"] = state.get("pipeline", 1.0) + 0.08
                state["active_deployments"] = state.get("active_deployments", 3.0) + 0.25
                state["support_load"] = state.get("support_load", 0.35) + 0.04
                state["reliability_debt"] = state.get("reliability_debt", 0.28) + 0.02
            if any(keyword in lowered for keyword in ["demand", "adoption", "growth"]):
                state["delivery_velocity"] = state.get("delivery_velocity", 1.0) - 0.01
                state["market_share"] = state.get("market_share", 0.05) + 0.015
                state["pipeline"] = state.get("pipeline", 1.0) + 0.12
                state["active_deployments"] = state.get("active_deployments", 3.0) + 0.3
                state["support_load"] = state.get("support_load", 0.35) + 0.03
            if any(keyword in lowered for keyword in ["bundled", "native", "copilot", "platform", "workspace"]):
                state["brand_index"] = state.get("brand_index", 1.0) - 0.04
                state["market_share"] = state.get("market_share", 0.05) - 0.02
                state["team_morale"] = state.get("team_morale", 1.0) - 0.01
                state["pipeline"] = state.get("pipeline", 1.0) - 0.08
                state["nrr"] = state.get("nrr", 1.02) - 0.03
                state["churn_risk"] = state.get("churn_risk", 0.12) + 0.04
            if any(keyword in lowered for keyword in ["security", "compliance", "procurement", "integration", "pilot"]):
                state["delivery_velocity"] = state.get("delivery_velocity", 1.0) - 0.03
                state["cash"] = state.get("cash", 100.0) - 4.0
                state["runway_weeks"] = state.get("runway_weeks", 52.0) - 1.0
                state["active_deployments"] = state.get("active_deployments", 3.0) + 0.2
                state["support_load"] = state.get("support_load", 0.35) + 0.08
                state["implementation_capacity"] = state.get("implementation_capacity", 3.0) - 0.05
            if any(keyword in lowered for keyword in ["hallucination", "latency", "outage", "accuracy", "reliability"]):
                state["brand_index"] = state.get("brand_index", 1.0) - 0.06
                state["market_share"] = state.get("market_share", 0.05) - 0.015
                state["team_morale"] = state.get("team_morale", 1.0) - 0.03
                state["reliability_debt"] = state.get("reliability_debt", 0.28) + 0.1
                state["support_load"] = state.get("support_load", 0.35) + 0.09
                state["churn_risk"] = state.get("churn_risk", 0.12) + 0.05
                state["nrr"] = state.get("nrr", 1.02) - 0.04
            if any(keyword in lowered for keyword in ["roi", "renewal", "expansion", "savings", "hours"]):
                state["cash"] = state.get("cash", 100.0) + 8.0
                state["brand_index"] = state.get("brand_index", 1.0) + 0.04
                state["market_share"] = state.get("market_share", 0.05) + 0.015
                state["pipeline"] = state.get("pipeline", 1.0) + 0.06
                state["gross_margin"] = state.get("gross_margin", 0.62) + 0.03
                state["nrr"] = state.get("nrr", 1.02) + 0.05
                state["churn_risk"] = state.get("churn_risk", 0.12) - 0.03
            return

        if any(keyword in lowered for keyword in ["supply", "bridge", "port", "convoy"]):
            state["logistics_throughput"] = state.get("logistics_throughput", 1.0) - 0.12
            state["ammo"] = state.get("ammo", 1.0) - 0.06
            state["readiness"] = state.get("readiness", 1.0) - 0.04
            state["supply_network"] = state.get("supply_network", 0.84) - 0.10
            state["objective_control"] = state.get("objective_control", 0.5) - 0.04
            state["enemy_pressure"] = state.get("enemy_pressure", 0.66) + 0.05
        if any(keyword in lowered for keyword in ["weather", "storm", "fog"]):
            state["mobility"] = state.get("mobility", 1.0) - 0.10
            state["isr_coverage"] = state.get("isr_coverage", 1.0) - 0.05
            state["supply_network"] = state.get("supply_network", 0.84) - 0.05
            state["recovery_capacity"] = state.get("recovery_capacity", 0.68) - 0.02
        if any(keyword in lowered for keyword in ["drone", "swarm", "strike"]):
            state["air_defense"] = state.get("air_defense", 1.0) - 0.08
            state["civilian_risk"] = state.get("civilian_risk", 0.25) + 0.06
            state["escalation_index"] = state.get("escalation_index", 0.3) + 0.05
            state["enemy_pressure"] = state.get("enemy_pressure", 0.66) + 0.07
            state["enemy_readiness"] = state.get("enemy_readiness", 0.82) + 0.03
        if any(keyword in lowered for keyword in ["isr", "satellite", "recon"]):
            state["isr_coverage"] = state.get("isr_coverage", 1.0) + 0.10
            state["information_advantage"] = state.get("information_advantage", 1.0) + 0.08
            state["objective_control"] = state.get("objective_control", 0.5) + 0.04
            state["enemy_pressure"] = state.get("enemy_pressure", 0.66) - 0.03
        if any(keyword in lowered for keyword in ["jam", "electronic", "cyber"]):
            state["ew_control"] = state.get("ew_control", 1.0) - 0.08
            state["command_cohesion"] = state.get("command_cohesion", 1.0) - 0.05
            state["objective_control"] = state.get("objective_control", 0.5) - 0.03
            state["supply_network"] = state.get("supply_network", 0.84) - 0.03


    async def _select_action(
        self,
        domain_id: str,
        state: dict[str, float],
        active_claim: Claim | None,
        rules: list[RuleSpec],
        recent_claims: list[Claim] | None = None,
        action_history: list[str] | None = None,
        recent_decisions: list[DecisionRecordRecord] | None = None,
    ) -> SelectedAction:
        evidence_window = self._build_evidence_window(active_claim, recent_claims)
        candidate = self._rank_action_candidates(
            domain_id,
            state,
            evidence_window,
            rules,
            action_history or [],
        )
        if candidate is not None and candidate.total_score >= _DECISION_MIN_SCORE:
            expected = self._aggregate_candidate_effect(candidate)
            return SelectedAction(
                action_id=candidate.action_id,
                why_selected=self._build_selection_explanation(candidate),
                rule_ids=self._candidate_rule_ids(candidate),
                evidence_ids=self._candidate_evidence_ids(candidate),
                expected_effect=expected,
                actual_effect=expected,
                decision_method="rule_engine",
            )

        # Level 2: LLM-assisted decision (when rules produce no strong candidate)
        llm_result = await self._llm_decide_action(
            domain_id,
            state,
            rules,
            evidence_window,
            recent_decisions or [],
            action_history or [],
        )
        if llm_result is not None:
            return llm_result

        # Level 3: Weighted fallback
        fallback_effect = self._fallback_effect(domain_id, state)
        return SelectedAction(
            action_id=fallback_effect["action_id"],
            why_selected=fallback_effect["why_selected"],
            rule_ids=[],
            evidence_ids=[active_claim.evidence_item_id] if active_claim is not None else [],
            expected_effect=fallback_effect["effects"],
            actual_effect=fallback_effect["effects"],
            decision_method="fallback_random",
        )

    async def _llm_decide_action(
        self,
        domain_id: str,
        state: dict[str, float],
        rules: list[RuleSpec],
        evidence_window: list[Claim],
        recent_decisions: list[DecisionRecordRecord],
        action_history: list[str],
    ) -> SelectedAction | None:
        if self.openai_service is None or not self.openai_service.is_configured("report"):
            return None

        pack = registry.get(domain_id)
        available_actions = [
            {"action_id": a.action_id, "description": a.description}
            for a in pack.action_library
        ]
        state_lines = [f"  {k}: {v:.3f}" for k, v in sorted(state.items())]
        state_summary = "\n".join(state_lines)
        recent = [
            {
                "tick": str(rec.tick),
                "action_id": rec.action_id,
                "why": (rec.why_selected or "")[:120],
            }
            for rec in recent_decisions[-3:]
        ]
        evidence = [claim.statement for claim in evidence_window[-3:]]

        try:
            result = await asyncio.wait_for(
                self.openai_service.generate_action_decision(
                    domain_id=domain_id,
                    state_summary=state_summary,
                    available_actions=available_actions,
                    recent_decisions=recent,
                    evidence=evidence,
                    target="report",
                ),
                timeout=10.0,
            )
        except (asyncio.TimeoutError, Exception):
            return None

        if result is None:
            return None

        action_id = result.action_id
        valid_ids = {a.action_id for a in pack.action_library}
        if action_id not in valid_ids:
            matched = [a.action_id for a in pack.action_library if a.action_id in action_id or action_id in a.action_id]
            action_id = matched[0] if matched else None
        if action_id is None:
            return None

        reasoning = result.reasoning or "LLM-assisted action selection."
        expected = dict(result.expected_effect) if result.expected_effect else {}

        return SelectedAction(
            action_id=action_id,
            why_selected=reasoning,
            rule_ids=[],
            evidence_ids=[claim.evidence_item_id for claim in evidence_window if claim.evidence_item_id][:3],
            expected_effect=expected,
            actual_effect=expected,
            decision_method="llm_assisted",
        )

    def _build_evidence_window(
        self,
        active_claim: Claim | None,
        recent_claims: list[Claim] | None,
    ) -> list[Claim]:
        window = list(recent_claims or [])
        if active_claim is not None and (
            not window or self._claim_key(window[-1]) != self._claim_key(active_claim)
        ):
            window.append(active_claim)
        return window[-_DECISION_EVIDENCE_WINDOW:]

    def _rank_action_candidates(
        self,
        domain_id: str,
        state: dict[str, float],
        evidence_window: list[Claim],
        rules: list[RuleSpec],
        action_history: list[str],
    ) -> ActionCandidate | None:
        candidates: dict[str, ActionCandidate] = {}
        for distance, claim in enumerate(reversed(evidence_window)):
            recency_weight = _DECISION_RECENCY_WEIGHTS[min(distance, len(_DECISION_RECENCY_WEIGHTS) - 1)]
            confidence = float(claim.confidence or 0.75)
            confidence_weight = 0.7 + (max(0.0, min(confidence, 1.0)) * 0.4)
            for rule in rules:
                matched_keywords = self._matched_keywords(rule, claim.statement)
                if not matched_keywords:
                    continue
                coverage_bonus = 0.08 * max(0, len(matched_keywords) - 1)
                effective_priority = self.rule_registry.effective_priority(rule)
                score = round(((effective_priority / 100.0) + coverage_bonus) * recency_weight * confidence_weight, 4)
                candidate = candidates.setdefault(rule.action_id, ActionCandidate(action_id=rule.action_id))
                candidate.rule_scores.append(
                    RuleScore(
                        rule=rule,
                        claim=claim,
                        score=score,
                        matched_keywords=matched_keywords,
                    )
                )
                candidate.base_score = round(candidate.base_score + score, 4)

        if not candidates:
            return None

        for candidate in candidates.values():
            aggregated_effect = self._aggregate_candidate_effect(candidate)
            candidate.state_adjustment = self._score_state_alignment(
                domain_id,
                state,
                candidate.action_id,
                aggregated_effect,
            )
            candidate.history_penalty = self._score_history_penalty(candidate.action_id, action_history)

        ranked = sorted(
            candidates.values(),
            key=lambda item: (
                item.total_score,
                item.base_score,
                max((score.score for score in item.rule_scores), default=0.0),
            ),
            reverse=True,
        )
        return ranked[0]

    def _matched_keywords(self, rule: RuleSpec, statement: str) -> tuple[str, ...]:
        lowered = statement.lower()
        return tuple(keyword for keyword in rule.trigger_keywords if keyword.lower() in lowered)

    def _aggregate_candidate_effect(self, candidate: ActionCandidate) -> dict[str, float]:
        aggregated: dict[str, float] = {}
        seen_rules: set[str] = set()
        ranked_scores = sorted(candidate.rule_scores, key=lambda item: item.score, reverse=True)
        for index, score in enumerate(ranked_scores):
            if score.rule.rule_id in seen_rules:
                multiplier = 0.15
            elif index == 0:
                multiplier = 1.0
            else:
                multiplier = 0.35
            seen_rules.add(score.rule.rule_id)
            for target, value in self._effects_to_mapping(score.rule.effects).items():
                aggregated[target] = round(aggregated.get(target, 0.0) + (value * multiplier), 4)

        evidence_count = len({score.claim.evidence_item_id for score in ranked_scores})
        support_multiplier = 1.0 + (0.08 * min(max(evidence_count - 1, 0), 2))
        return {
            target: round(value * support_multiplier, 4)
            for target, value in aggregated.items()
        }

    def _score_state_alignment(
        self,
        domain_id: str,
        state: dict[str, float],
        action_id: str,
        effects: dict[str, float],
    ) -> float:
        policies = _STATE_POLICIES.get(domain_id, {})
        adjustment = 0.0
        urgent_metric_present = False
        for target, delta in effects.items():
            policy = policies.get(target)
            if policy is None or delta == 0:
                continue
            urgency = self._metric_urgency(float(state.get(target, 0.0)), policy)
            urgent_metric_present = urgent_metric_present or urgency >= 0.5
            helps = self._effect_relieves_pressure(delta, policy)
            harms = self._effect_adds_pressure(delta, policy)
            if urgency == 0:
                if helps:
                    adjustment += 0.04
                elif harms:
                    adjustment -= 0.08
                continue
            if helps:
                adjustment += 0.22 + (0.28 * urgency)
                if self._metric_is_critical(float(state.get(target, 0.0)), policy):
                    adjustment += 0.12
            elif harms:
                adjustment -= 0.3 + (0.35 * urgency)
                if self._metric_is_critical(float(state.get(target, 0.0)), policy):
                    adjustment -= 0.2

        if action_id == "monitor" and urgent_metric_present:
            adjustment -= 0.25
        return round(adjustment, 4)

    def _metric_urgency(self, value: float, policy: MetricPolicy) -> float:
        if policy.preferred_direction == "increase":
            if value >= policy.alert_threshold:
                return 0.0
            denominator = max(policy.alert_threshold - policy.critical_threshold, 0.01)
            return min(1.0, max(0.0, (policy.alert_threshold - value) / denominator))

        if value <= policy.alert_threshold:
            return 0.0
        denominator = max(policy.critical_threshold - policy.alert_threshold, 0.01)
        return min(1.0, max(0.0, (value - policy.alert_threshold) / denominator))

    def _metric_is_critical(self, value: float, policy: MetricPolicy) -> bool:
        if policy.preferred_direction == "increase":
            return value <= policy.critical_threshold
        return value >= policy.critical_threshold

    def _effect_relieves_pressure(self, delta: float, policy: MetricPolicy) -> bool:
        return (policy.preferred_direction == "increase" and delta > 0) or (
            policy.preferred_direction == "decrease" and delta < 0
        )

    def _effect_adds_pressure(self, delta: float, policy: MetricPolicy) -> bool:
        return (policy.preferred_direction == "increase" and delta < 0) or (
            policy.preferred_direction == "decrease" and delta > 0
        )

    def _score_history_penalty(self, action_id: str, action_history: list[str]) -> float:
        penalty = 0.0
        for distance, previous_action in enumerate(reversed(action_history[-3:]), start=1):
            if previous_action != action_id:
                continue
            if distance == 1:
                penalty += 0.75
            elif distance == 2:
                penalty += 0.3
            else:
                penalty += 0.15
        return round(penalty, 4)

    def _candidate_rule_ids(self, candidate: ActionCandidate) -> list[str]:
        ordered_rule_ids: list[str] = []
        seen: set[str] = set()
        for score in sorted(candidate.rule_scores, key=lambda item: item.score, reverse=True):
            if score.rule.rule_id in seen:
                continue
            seen.add(score.rule.rule_id)
            ordered_rule_ids.append(score.rule.rule_id)
        return ordered_rule_ids

    def _candidate_evidence_ids(self, candidate: ActionCandidate) -> list[str]:
        ordered_evidence_ids: list[str] = []
        seen: set[str] = set()
        for score in sorted(candidate.rule_scores, key=lambda item: item.score, reverse=True):
            evidence_id = score.claim.evidence_item_id
            if evidence_id in seen:
                continue
            seen.add(evidence_id)
            ordered_evidence_ids.append(evidence_id)
        return ordered_evidence_ids

    def _build_selection_explanation(self, candidate: ActionCandidate) -> str:
        top_score = max(candidate.rule_scores, key=lambda item: item.score)
        rule_ids = self._candidate_rule_ids(candidate)
        evidence_count = len(self._candidate_evidence_ids(candidate))
        return (
            f"Selected {candidate.action_id} from {len(rule_ids)} supporting rule(s) "
            f"across {evidence_count} evidence item(s); top signal was {top_score.rule.rule_id} "
            f"and the final score was {candidate.total_score:.2f} after state and history adjustments."
        )

    def _claim_key(self, claim: Claim) -> str:
        claim_id = getattr(claim, "id", None)
        if claim_id:
            return str(claim_id)
        return f"{claim.evidence_item_id}:{normalize_text(claim.statement).lower()}"

    def _effects_to_mapping(self, effects: tuple[Any, ...]) -> dict[str, float]:
        result: dict[str, float] = {}
        for effect in effects:
            if effect.op != "add":
                continue
            result[effect.target] = result.get(effect.target, 0.0) + float(effect.value)
        return result

    def _fallback_effect(self, domain_id: str, state: dict[str, float]) -> dict[str, Any]:
        if domain_id == "corporate":
            deployment_load = state.get("active_deployments", 3.0) / max(state.get("implementation_capacity", 3.0), 1.0)
            if (
                state.get("pipeline", 1.0) > 1.15
                and deployment_load > 0.95
                and state.get("support_load", 0.35) > 0.48
                and state.get("runway_weeks", 52.0) > 48.0
                and state.get("gross_margin", 0.62) > 0.6
            ):
                return {
                    "action_id": "hire",
                    "why_selected": (
                        "Fallback policy invested in delivery capacity because qualified demand outran "
                        "implementation bandwidth while retention economics stayed healthy."
                    ),
                    "effects": {
                        "delivery_velocity": 0.05,
                        "implementation_capacity": 0.45,
                        "support_load": -0.06,
                        "cash": -8.0,
                        "runway_weeks": -2.0,
                    },
                }
            if state.get("runway_weeks", 52.0) < 28.0 or state.get("cash", 100.0) < 30.0:
                return {
                    "action_id": "tighten_scope",
                    "why_selected": "Fallback policy narrowed scope because liquidity and deployment capacity entered the red zone.",
                    "effects": {
                        "runway_weeks": 4.0,
                        "delivery_velocity": 0.03,
                        "brand_index": 0.01,
                        "market_share": -0.005,
                        "support_load": -0.08,
                        "reliability_debt": -0.04,
                        "active_deployments": -0.2,
                    },
                }
            if (
                state.get("brand_index", 1.0) < 0.88
                or state.get("reliability_debt", 0.28) > 0.44
                or state.get("churn_risk", 0.12) > 0.2
            ):
                return {
                    "action_id": "improve_reliability",
                    "why_selected": (
                        "Fallback policy prioritized trust recovery after reliability debt and renewal risk "
                        "started to outweigh short-term delivery pressure."
                    ),
                    "effects": {
                        "brand_index": 0.05,
                        "market_share": 0.005,
                        "delivery_velocity": -0.04,
                        "team_morale": -0.01,
                        "reliability_debt": -0.1,
                        "support_load": -0.07,
                        "nrr": 0.03,
                        "churn_risk": -0.05,
                    },
                }
            if (
                state.get("market_share", 0.05) < 0.03
                and state.get("brand_index", 1.0) < 0.95
            ) or state.get("pipeline", 1.0) < 0.8:
                return {
                    "action_id": "focus_vertical",
                    "why_selected": (
                        "Fallback policy narrowed the wedge because broad positioning stopped converting into "
                        "qualified pipeline and durable retention."
                    ),
                    "effects": {
                        "brand_index": 0.03,
                        "market_share": 0.01,
                        "delivery_velocity": -0.03,
                        "pipeline": 0.08,
                        "gross_margin": 0.04,
                        "nrr": 0.02,
                        "churn_risk": -0.02,
                    },
                }
            if state.get("infra_cost_index", 1.0) > 1.1 or state.get("gross_margin", 0.62) < 0.55:
                return {
                    "action_id": "optimize_cost",
                    "why_selected": "Fallback policy detected sustained cost pressure and deteriorating unit economics.",
                    "effects": {
                        "infra_cost_index": -0.05,
                        "runway_weeks": 2.0,
                        "delivery_velocity": -0.01,
                        "gross_margin": 0.05,
                        "support_load": -0.02,
                    },
                }
            return {
                "action_id": "monitor",
                "why_selected": "No rule crossed the action threshold, so the baseline policy held position.",
                "effects": {"brand_index": 0.01, "pipeline": 0.01},
            }

        if state.get("civilian_risk", 0.0) > 0.55:
            return {
                "action_id": "protect_civilians",
                "why_selected": "Fallback policy prioritized civilian protection after risk crossed the alert line.",
                "effects": {
                    "civilian_risk": -0.08,
                    "readiness": -0.01,
                    "escalation_index": -0.04,
                    "objective_control": -0.02,
                },
            }
        if state.get("logistics_throughput", 1.0) < 0.82 or state.get("supply_network", 0.84) < 0.76:
            return {
                "action_id": "open_supply_line",
                "why_selected": "Fallback policy restored the supply corridor to recover readiness.",
                "effects": {
                    "logistics_throughput": 0.10,
                    "supply_network": 0.08,
                    "ammo": 0.05,
                    "readiness": 0.03,
                    "recovery_capacity": 0.02,
                },
            }
        if state.get("objective_control", 0.5) < 0.48:
            return {
                "action_id": "secure_objective",
                "why_selected": "Fallback policy stabilized the decisive objective before the force lost positional leverage.",
                "effects": {
                    "objective_control": 0.08,
                    "enemy_pressure": -0.04,
                    "attrition_rate": -0.02,
                    "mobility": -0.02,
                },
            }
        if state.get("enemy_pressure", 0.66) > 0.7 or state.get("enemy_readiness", 0.82) > 0.82:
            return {
                "action_id": "suppress_enemy_fires",
                "why_selected": "Fallback policy disrupted enemy pressure before additional fires stacked onto the corridor fight.",
                "effects": {
                    "enemy_pressure": -0.08,
                    "enemy_readiness": -0.04,
                    "information_advantage": 0.03,
                    "ammo": -0.04,
                    "escalation_index": 0.03,
                },
            }
        if state.get("attrition_rate", 0.18) > 0.28 or state.get("recovery_capacity", 0.68) < 0.58:
            return {
                "action_id": "rotate_and_repair",
                "why_selected": "Fallback policy rotated damaged elements because attrition outpaced recovery capacity.",
                "effects": {
                    "readiness": 0.05,
                    "attrition_rate": -0.05,
                    "recovery_capacity": 0.05,
                    "mobility": -0.03,
                },
            }
        if state.get("air_defense", 1.0) < 0.85:
            return {
                "action_id": "rebalance_air_defense",
                "why_selected": "Fallback policy shifted coverage to reduce incoming drone exposure.",
                "effects": {
                    "air_defense": 0.09,
                    "mobility": -0.02,
                    "enemy_pressure": -0.04,
                    "civilian_risk": -0.03,
                },
            }
        return {
            "action_id": "fortify",
            "why_selected": "No military rule crossed the threshold, so the force hardened its current position.",
            "effects": {
                "readiness": 0.02,
                "air_defense": 0.03,
                "objective_control": 0.03,
                "attrition_rate": -0.02,
            },
        }

    def _apply_effects(self, state: dict[str, float], effect: dict[str, float]) -> None:
        for key, delta in effect.items():
            state[key] = round(float(state.get(key, 0.0)) + float(delta), 4)
