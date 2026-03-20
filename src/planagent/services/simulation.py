from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from sqlalchemy import and_, or_, select
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
        if parent_run.domain_id != "military":
            raise ValueError("Scenario branching is implemented for military runs only.")
        if parent_run.force_id is None:
            raise ValueError("Military scenario branching requires a force-backed baseline run.")
        if parent_run.status != SimulationRunStatus.COMPLETED.value:
            raise ValueError("Scenario branching requires a completed baseline run.")

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
            company_id=None,
            force_id=parent_run.force_id,
            domain_id="military",
            actor_template=parent_run.actor_template,
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
            },
            summary={"scenario_id": scenario_id},
        )
        session.add(run)
        await session.flush()
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

    async def process_queued_runs(self, session: AsyncSession, limit: int = 10) -> int:
        runs = list(
            (
                await session.scalars(
                    select(SimulationRun)
                    .where(SimulationRun.status == SimulationRunStatus.PENDING.value)
                    .order_by(SimulationRun.created_at.asc())
                    .limit(limit)
                )
            ).all()
        )
        processed = 0
        for run in runs:
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
            processed += 1
        await session.commit()
        return processed

    async def generate_pending_reports(self, session: AsyncSession, limit: int = 10) -> int:
        runs = list(
            (
                await session.scalars(
                    select(SimulationRun)
                    .outerjoin(GeneratedReport, GeneratedReport.run_id == SimulationRun.id)
                    .where(
                        and_(
                            SimulationRun.status == SimulationRunStatus.COMPLETED.value,
                            GeneratedReport.id.is_(None),
                        )
                    )
                    .order_by(SimulationRun.completed_at.asc())
                    .limit(limit)
                )
            ).all()
        )
        generated = 0
        for run in runs:
            await self._generate_report(session, run)
            generated += 1
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
    ) -> GeneratedReport | None:
        return (
            await session.scalars(
                select(GeneratedReport)
                .where(GeneratedReport.company_id == company_id)
                .order_by(GeneratedReport.created_at.desc())
            )
        ).first()

    async def latest_military_report(
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
        metric_names = sorted(
            {
                metric["metric"]
                for branch in branch_records
                for metric in branch.kpi_trajectory
                if "metric" in metric
            }
            | set(baseline_final_state.keys())
        )
        branches: list[dict[str, Any]] = []
        for branch in branch_records:
            branch_run = await session.get(SimulationRun, branch.run_id)
            branch_report = await self.latest_military_report(session, branch.id)
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
                }
            )
        return {
            "baseline_run_id": baseline_run.id,
            "domain_id": baseline_run.domain_id,
            "branch_count": len(branches),
            "metric_names": metric_names,
            "baseline_final_state": baseline_final_state,
            "branches": branches,
        }

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
            domain_id="corporate",
            actor_template=payload.actor_template,
            execution_mode=execution_mode.value,
            status=SimulationRunStatus.PENDING.value,
            tick_count=payload.tick_count or self.settings.default_corporate_ticks,
            seed=payload.seed,
            configuration={
                "initial_state": payload.initial_state,
                "market": payload.market,
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
        run = SimulationRun(
            company_id=None,
            force_id=force.id,
            domain_id="military",
            actor_template=payload.actor_template,
            execution_mode=execution_mode.value,
            status=SimulationRunStatus.PENDING.value,
            tick_count=payload.tick_count or self.settings.default_military_ticks,
            seed=payload.seed,
            configuration={
                "initial_state": payload.initial_state,
                "theater": payload.theater or force.theater,
            },
            summary={},
        )
        session.add(run)
        await session.flush()
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

        session.add(StateSnapshotRecord(run_id=run.id, tick=0, actor_id=actor_id, state=deepcopy(current_state)))

        for tick in range(1, run.tick_count + 1):
            active_claim = claims[(tick - 1) % len(claims)] if claims else None
            if active_claim is not None:
                shock_count += await self._record_external_shock(session, run, tick, active_claim)
                self._apply_external_shock(run.domain_id, current_state, active_claim.statement)
            selected = self._select_action(run.domain_id, current_state, active_claim, rules)
            matched_rules.extend(selected.rule_ids)
            self._apply_effects(current_state, selected.actual_effect)
            session.add(
                DecisionRecordRecord(
                    run_id=run.id,
                    tick=tick,
                    sequence=1,
                    actor_id=actor_id,
                    action_id=selected.action_id,
                    why_selected=selected.why_selected,
                    evidence_ids=selected.evidence_ids,
                    policy_rule_ids=selected.rule_ids,
                    expected_effect=selected.expected_effect,
                    actual_effect=selected.actual_effect,
                )
            )
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
        run.summary = {
            **run.summary,
            "ticks_completed": run.tick_count,
            "evidence_count": len(claims),
            "shock_count": shock_count,
            "evidence_ids": sorted({claim.evidence_item_id for claim in claims}),
            "evidence_statements": [claim.statement for claim in claims[:5]],
            "matched_rules": sorted(set(matched_rules)),
            "final_state": deepcopy(current_state),
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

        branch.kpi_trajectory = self._build_branch_trajectory(
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
                "name": "Civilian District Alpha",
                "asset_type": "civilian_area",
                "latitude_offset": -0.0900,
                "longitude_offset": 0.1100,
                "properties": {"role": "protection", "population_index": 0.72},
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
        if asset_type == "civilian_area" and float(state.get("civilian_risk", 0.0)) > 0.55:
            properties["status"] = "at_risk"
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

    def _build_branch_trajectory(
        self,
        parent_final: dict[str, Any],
        branch_final: dict[str, Any],
    ) -> list[dict[str, Any]]:
        tracked = [
            "readiness",
            "logistics_throughput",
            "isr_coverage",
            "air_defense",
            "civilian_risk",
            "escalation_index",
        ]
        return [
            {
                "metric": metric,
                "baseline_end": float(parent_final.get(metric, 0.0)),
                "scenario_end": float(branch_final.get(metric, 0.0)),
            }
            for metric in tracked
            if metric in parent_final or metric in branch_final
        ]

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
        query = select(Claim).where(Claim.status == ClaimStatus.ACCEPTED.value)
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
        if claims:
            return claims
        return list(
            (
                await session.scalars(
                    select(Claim)
                    .where(Claim.status == ClaimStatus.ACCEPTED.value)
                    .order_by(Claim.created_at.asc())
                )
            ).all()
        )

    async def _subject_terms(self, session: AsyncSession, run: SimulationRun) -> list[str]:
        if run.domain_id == "corporate" and run.company_id:
            company = await session.get(CompanyProfile, run.company_id)
            if company is None:
                return []
            return [company.name, company.id, company.market]
        if run.domain_id == "military" and run.force_id:
            force = await session.get(ForceProfile, run.force_id)
            if force is None:
                return []
            return [force.name, force.id, force.theater]
        return []

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
            if any(keyword in lowered for keyword in ["ship", "launch", "release"]):
                state["brand_index"] = state.get("brand_index", 1.0) + 0.05
                state["market_share"] = state.get("market_share", 0.05) + 0.01
            if any(keyword in lowered for keyword in ["demand", "adoption", "growth"]):
                state["delivery_velocity"] = state.get("delivery_velocity", 1.0) - 0.01
                state["market_share"] = state.get("market_share", 0.05) + 0.015
            return

        if any(keyword in lowered for keyword in ["supply", "bridge", "port", "convoy"]):
            state["logistics_throughput"] = state.get("logistics_throughput", 1.0) - 0.12
            state["ammo"] = state.get("ammo", 1.0) - 0.06
            state["readiness"] = state.get("readiness", 1.0) - 0.04
        if any(keyword in lowered for keyword in ["weather", "storm", "fog"]):
            state["mobility"] = state.get("mobility", 1.0) - 0.10
            state["isr_coverage"] = state.get("isr_coverage", 1.0) - 0.05
        if any(keyword in lowered for keyword in ["drone", "swarm", "strike"]):
            state["air_defense"] = state.get("air_defense", 1.0) - 0.08
            state["civilian_risk"] = state.get("civilian_risk", 0.25) + 0.06
            state["escalation_index"] = state.get("escalation_index", 0.3) + 0.05
        if any(keyword in lowered for keyword in ["isr", "satellite", "recon"]):
            state["isr_coverage"] = state.get("isr_coverage", 1.0) + 0.10
            state["information_advantage"] = state.get("information_advantage", 1.0) + 0.08
        if any(keyword in lowered for keyword in ["jam", "electronic", "cyber"]):
            state["ew_control"] = state.get("ew_control", 1.0) - 0.08
            state["command_cohesion"] = state.get("command_cohesion", 1.0) - 0.05

    def _select_action(
        self,
        domain_id: str,
        state: dict[str, float],
        active_claim: Claim | None,
        rules: list[RuleSpec],
    ) -> SelectedAction:
        if active_claim is not None:
            for rule in rules:
                if rule.matches(active_claim.statement):
                    why = rule.explanation_template.format(
                        statement=normalize_text(active_claim.statement),
                        action_id=rule.action_id,
                        rule_id=rule.rule_id,
                    )
                    expected = self._effects_to_mapping(rule.effects)
                    return SelectedAction(
                        action_id=rule.action_id,
                        why_selected=why,
                        rule_ids=[rule.rule_id],
                        evidence_ids=[active_claim.evidence_item_id],
                        expected_effect=expected,
                        actual_effect=expected,
                    )

        fallback_effect = self._fallback_effect(domain_id, state)
        return SelectedAction(
            action_id=fallback_effect["action_id"],
            why_selected=fallback_effect["why_selected"],
            rule_ids=[],
            evidence_ids=[active_claim.evidence_item_id] if active_claim is not None else [],
            expected_effect=fallback_effect["effects"],
            actual_effect=fallback_effect["effects"],
        )

    def _effects_to_mapping(self, effects: tuple[Any, ...]) -> dict[str, float]:
        result: dict[str, float] = {}
        for effect in effects:
            if effect.op != "add":
                continue
            result[effect.target] = result.get(effect.target, 0.0) + float(effect.value)
        return result

    def _fallback_effect(self, domain_id: str, state: dict[str, float]) -> dict[str, Any]:
        if domain_id == "corporate":
            if state.get("infra_cost_index", 1.0) > 1.1:
                return {
                    "action_id": "optimize_cost",
                    "why_selected": "Fallback policy detected sustained cost pressure and protected runway.",
                    "effects": {"infra_cost_index": -0.05, "runway_weeks": 2.0, "delivery_velocity": -0.01},
                }
            return {
                "action_id": "monitor",
                "why_selected": "No rule crossed the action threshold, so the baseline policy held position.",
                "effects": {"brand_index": 0.01},
            }

        if state.get("civilian_risk", 0.0) > 0.55:
            return {
                "action_id": "protect_civilians",
                "why_selected": "Fallback policy prioritized civilian protection after risk crossed the alert line.",
                "effects": {"civilian_risk": -0.08, "readiness": -0.01, "escalation_index": -0.04},
            }
        if state.get("logistics_throughput", 1.0) < 0.82:
            return {
                "action_id": "open_supply_line",
                "why_selected": "Fallback policy restored the supply corridor to recover readiness.",
                "effects": {"logistics_throughput": 0.10, "ammo": 0.05, "readiness": 0.03},
            }
        if state.get("air_defense", 1.0) < 0.85:
            return {
                "action_id": "rebalance_air_defense",
                "why_selected": "Fallback policy shifted coverage to reduce incoming drone exposure.",
                "effects": {"air_defense": 0.09, "mobility": -0.02},
            }
        return {
            "action_id": "fortify",
            "why_selected": "No military rule crossed the threshold, so the force hardened its current position.",
            "effects": {"readiness": 0.02, "air_defense": 0.03},
        }

    def _apply_effects(self, state: dict[str, float], effect: dict[str, float]) -> None:
        for key, delta in effect.items():
            state[key] = round(float(state.get(key, 0.0)) + float(delta), 4)
