from __future__ import annotations

from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from planagent.domain.api import ScenarioRunCreate
from planagent.domain.enums import ExecutionMode, SimulationRunStatus
from planagent.domain.models import (
    CompanyProfile,
    DecisionRecordRecord,
    ForceProfile,
    ScenarioBranchRecord,
    SimulationRun,
    StateSnapshotRecord,
    generate_id,
)
from planagent.services.simulation_branching import (
    build_branch_trajectory,
    build_scenario_compare_summary,
    score_branch_delta,
    summarize_branch_trajectory,
)


class SimulationScenariosMixin:
    def _build_scenario_template(
        self,
        parent_run: SimulationRun,
        payload: ScenarioRunCreate,
        fork_step: int | None = None,
    ) -> dict[str, Any]:
        resolved_fork_step = fork_step or payload.fork_step or max(1, parent_run.tick_count // 2)
        return {
            "parent_run_id": parent_run.id,
            "domain_id": parent_run.domain_id,
            "actor_template": parent_run.actor_template,
            "fork_step": resolved_fork_step,
            "tick_count": payload.tick_count or max(1, parent_run.tick_count - resolved_fork_step),
            "assumptions": list(payload.assumptions),
            "decision_deltas": list(payload.decision_deltas),
            "state_overrides": dict(payload.state_overrides),
            "probability_band": payload.probability_band,
        }

    def _generate_scenarios(
        self,
        parent_run: SimulationRun,
        payloads: list[ScenarioRunCreate],
    ) -> list[dict[str, Any]]:
        return [self._build_scenario_template(parent_run, payload) for payload in payloads]

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
                raise ValueError(
                    "Military scenario branching requires a force-backed baseline run."
                )
        elif parent_run.domain_id == "corporate":
            if parent_run.company_id is None:
                raise ValueError(
                    "Corporate scenario branching requires a company-backed baseline run."
                )
        else:
            raise ValueError(
                f"Scenario branching is not implemented for domain {parent_run.domain_id}."
            )

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
            raise LookupError(
                f"No state snapshot found at fork step {fork_step} for run {parent_run.id}."
            )

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

    async def get_scenario_branch(
        self,
        session: AsyncSession,
        scenario_id: str,
    ) -> ScenarioBranchRecord | None:
        return await session.get(ScenarioBranchRecord, scenario_id)

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
                    for key, value in (
                        branch_run.summary.get("final_state", {}) if branch_run is not None else {}
                    ).items()
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
                    "matched_rules": branch_run.summary.get("matched_rules", [])
                    if branch_run is not None
                    else [],
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
                            *(
                                key_deltas[:2]
                                or ["Compare this branch against the baseline outcome."]
                            ),
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
            f"Scenario matched {rule_id}"
            for rule_id in branch_run.summary.get("matched_rules", [])[:3]
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
