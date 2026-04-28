from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from planagent.domain.models import (
    CompanyProfile,
    DecisionRecordRecord,
    ExternalShockRecord,
    ForceProfile,
    GeoAssetRecord,
    GeneratedReport,
    ScenarioBranchRecord,
    SimulationRun,
    StateSnapshotRecord,
)
from planagent.services.openai_client import OpenAIService
from planagent.services.startup import build_startup_kpi_pack


class ReportService:
    def __init__(self, openai_service: OpenAIService | None = None) -> None:
        self.openai_service = openai_service

    async def generate_report(
        self,
        session: AsyncSession,
        simulation_run: SimulationRun,
    ) -> GeneratedReport:
        if simulation_run.domain_id == "corporate":
            return await self.generate_company_report(session, simulation_run)
        if simulation_run.domain_id == "military":
            return await self.generate_military_report(session, simulation_run)
        raise ValueError(f"Unsupported report domain: {simulation_run.domain_id}")

    async def generate_company_report(
        self,
        session: AsyncSession,
        simulation_run: SimulationRun,
    ) -> GeneratedReport:
        company = await session.get(CompanyProfile, simulation_run.company_id)
        if company is None:
            raise LookupError(f"Company {simulation_run.company_id} was not found.")

        decision_records, state_snapshots = await self._load_run_materials(session, simulation_run.id)
        scenario_branch = (
            await session.scalars(
                select(ScenarioBranchRecord).where(ScenarioBranchRecord.run_id == simulation_run.id)
            )
        ).first()
        child_branches = list(
            (
                await session.scalars(
                    select(ScenarioBranchRecord)
                    .where(ScenarioBranchRecord.parent_run_id == simulation_run.id)
                    .order_by(ScenarioBranchRecord.created_at.asc())
                )
            ).all()
        )
        initial_state = state_snapshots[0].state if state_snapshots else {}
        final_state = state_snapshots[-1].state if state_snapshots else {}
        actions = [record.action_id for record in decision_records]
        leading_indicators = self._build_indicator_changes(
            initial_state,
            final_state,
            [
                "runway_weeks",
                "delivery_velocity",
                "pipeline",
                "active_deployments",
                "implementation_capacity",
                "support_load",
                "reliability_debt",
                "gross_margin",
                "nrr",
                "churn_risk",
                "brand_index",
                "market_share",
                "cash",
            ],
        )
        matched_rules = simulation_run.summary.get("matched_rules", [])
        startup_kpi_pack = build_startup_kpi_pack(
            simulation_run,
            initial_state,
            final_state,
            matched_rules,
        )
        title_suffix = "scenario report" if scenario_branch is not None else "baseline report"

        summary = (
            f"{company.name} completed {simulation_run.tick_count} corporate ticks with "
            f"{len(actions)} recorded decisions. Final runway is {final_state.get('runway_weeks', 'n/a')} weeks, "
            f"pipeline coverage is {final_state.get('pipeline', 'n/a')}, and support load is {final_state.get('support_load', 'n/a')}."
        )
        recommendations = self._build_company_recommendations(final_state)
        why_this_happened = {
            "key_evidence": simulation_run.summary.get("evidence_statements", []),
            "rules_hit": matched_rules,
            "actions_taken": actions,
            "metric_changes": self._metrics_by_name(leading_indicators),
        }
        if scenario_branch is not None:
            why_this_happened["scenario_assumptions"] = scenario_branch.assumptions
            why_this_happened["decision_deltas"] = scenario_branch.decision_deltas

        if self.openai_service is not None and self.openai_service.is_configured("report"):
            enhancement = await self.openai_service.enhance_company_report(
                company_name=company.name,
                evidence_statements=simulation_run.summary.get("evidence_statements", []),
                actions=actions,
                leading_indicators=leading_indicators,
                matched_rules=matched_rules,
            )
            if enhancement is not None:
                summary = enhancement.executive_summary
                recommendations = enhancement.strategy_recommendations or recommendations
                why_this_happened = {
                    **why_this_happened,
                    "model_narrative": enhancement.why_this_happened,
                }

        sections = {
            "executive_summary": summary,
            "evidence_summary": simulation_run.summary.get("evidence_statements", []),
            "timeline": [
                {
                    "tick": record.tick,
                    "action_id": record.action_id,
                    "why_selected": record.why_selected,
                }
                for record in decision_records
            ],
            "current_signals": matched_rules,
            "scenario_tree": {
                "baseline_only": scenario_branch is None and not child_branches,
                "branch_id": scenario_branch.id if scenario_branch is not None else None,
                "parent_run_id": scenario_branch.parent_run_id if scenario_branch is not None else None,
                "child_branch_ids": [branch.id for branch in child_branches],
            },
            "decision_chain": self._build_decision_chain(decision_records),
            "leading_indicators": leading_indicators,
            "scenario_compare": scenario_branch.kpi_trajectory if scenario_branch is not None else [],
            "strategy_recommendations": recommendations,
            "why_this_happened": why_this_happened,
            "startup_kpi_pack": startup_kpi_pack.model_dump() if startup_kpi_pack is not None else None,
        }

        report = GeneratedReport(
            run_id=simulation_run.id,
            company_id=company.id,
            scenario_id=scenario_branch.id if scenario_branch is not None else None,
            tenant_id=simulation_run.tenant_id,
            preset_id=simulation_run.preset_id,
            title=f"{company.name} corporate {title_suffix}",
            summary=summary,
            report_format="markdown",
            sections=sections,
        )
        session.add(report)
        await session.flush()
        return report

    async def generate_military_report(
        self,
        session: AsyncSession,
        simulation_run: SimulationRun,
    ) -> GeneratedReport:
        force = await session.get(ForceProfile, simulation_run.force_id)
        if force is None:
            raise LookupError(f"Force {simulation_run.force_id} was not found.")

        decision_records, state_snapshots = await self._load_run_materials(session, simulation_run.id)
        scenario_branch = (
            await session.scalars(
                select(ScenarioBranchRecord).where(ScenarioBranchRecord.run_id == simulation_run.id)
            )
        ).first()
        child_branches = list(
            (
                await session.scalars(
                    select(ScenarioBranchRecord)
                    .where(ScenarioBranchRecord.parent_run_id == simulation_run.id)
                    .order_by(ScenarioBranchRecord.created_at.asc())
                )
            ).all()
        )
        geo_assets = list(
            (
                await session.scalars(
                    select(GeoAssetRecord)
                    .where(GeoAssetRecord.run_id == simulation_run.id)
                    .order_by(GeoAssetRecord.asset_type.asc(), GeoAssetRecord.name.asc())
                )
            ).all()
        )
        external_shocks = list(
            (
                await session.scalars(
                    select(ExternalShockRecord)
                    .where(ExternalShockRecord.run_id == simulation_run.id)
                    .order_by(ExternalShockRecord.tick.asc(), ExternalShockRecord.created_at.asc())
                )
            ).all()
        )
        initial_state = state_snapshots[0].state if state_snapshots else {}
        final_state = state_snapshots[-1].state if state_snapshots else {}
        actions = [record.action_id for record in decision_records]
        leading_indicators = self._build_indicator_changes(
            initial_state,
            final_state,
            [
                "readiness",
                "logistics_throughput",
                "supply_network",
                "objective_control",
                "attrition_rate",
                "enemy_readiness",
                "enemy_pressure",
                "isr_coverage",
                "air_defense",
                "civilian_risk",
                "escalation_index",
            ],
        )
        matched_rules = simulation_run.summary.get("matched_rules", [])
        startup_kpi_pack = build_startup_kpi_pack(
            simulation_run,
            initial_state,
            final_state,
            matched_rules,
        )
        objective_network = simulation_run.summary.get("objective_network", {})
        enemy_posture = simulation_run.summary.get("enemy_posture", {})
        enemy_order_of_battle = simulation_run.summary.get("enemy_order_of_battle", [])
        title_suffix = "scenario report" if scenario_branch is not None else "baseline report"
        summary = (
            f"{force.name} in {force.theater} completed {simulation_run.tick_count} military ticks with "
            f"{len(actions)} recorded decisions. Final readiness is {final_state.get('readiness', 'n/a')} and "
            f"logistics throughput is {final_state.get('logistics_throughput', 'n/a')}. "
            f"Objective control closed at {final_state.get('objective_control', 'n/a')} against enemy readiness "
            f"{final_state.get('enemy_readiness', 'n/a')}. "
            f"Enemy posture centered on {enemy_posture.get('focus', 'positional pressure')}."
        )
        recommendations = self._build_military_recommendations(final_state)
        why_this_happened = {
            "key_evidence": simulation_run.summary.get("evidence_statements", []),
            "rules_hit": matched_rules,
            "actions_taken": actions,
            "metric_changes": self._metrics_by_name(leading_indicators),
            "enemy_posture": enemy_posture.get("summary"),
        }
        if scenario_branch is not None:
            why_this_happened["scenario_assumptions"] = scenario_branch.assumptions
            why_this_happened["decision_deltas"] = scenario_branch.decision_deltas
        shock_payloads = [
            {
                "tick": shock.tick,
                "shock_type": shock.shock_type,
                "summary": shock.summary,
                "evidence_ids": shock.evidence_ids,
            }
            for shock in external_shocks
        ]

        if self.openai_service is not None and self.openai_service.is_configured("report"):
            enhancement = await self.openai_service.enhance_military_report(
                force_name=force.name,
                theater=force.theater,
                evidence_statements=simulation_run.summary.get("evidence_statements", []),
                actions=actions,
                leading_indicators=leading_indicators,
                matched_rules=matched_rules,
                external_shocks=shock_payloads,
                scenario_assumptions=scenario_branch.assumptions if scenario_branch is not None else None,
            )
            if enhancement is not None:
                summary = enhancement.executive_summary
                recommendations = enhancement.strategy_recommendations or recommendations
                why_this_happened = {
                    **why_this_happened,
                    "model_narrative": enhancement.why_this_happened,
                }

        sections = {
            "executive_summary": summary,
            "evidence_summary": simulation_run.summary.get("evidence_statements", []),
            "timeline": [
                {
                    "tick": record.tick,
                    "action_id": record.action_id,
                    "why_selected": record.why_selected,
                }
                for record in decision_records
            ],
            "current_signals": matched_rules,
            "combat_exchange": simulation_run.summary.get("military_tick_summaries", []),
            "geo_map": {
                "theater": force.theater,
                "assets": [
                    {
                        "asset_id": asset.id,
                        "name": asset.name,
                        "asset_type": asset.asset_type,
                        "latitude": asset.latitude,
                        "longitude": asset.longitude,
                        "properties": asset.properties,
                    }
                    for asset in geo_assets
                ],
                "network": {
                    "edges": objective_network.get("edges", []),
                    "critical_route_id": objective_network.get("critical_route_id"),
                    "critical_objective_id": objective_network.get("critical_objective_id"),
                },
            },
            "objective_network": {
                "objective_control": final_state.get("objective_control"),
                "supply_network": final_state.get("supply_network"),
                "recovery_capacity": final_state.get("recovery_capacity"),
                "attrition_rate": final_state.get("attrition_rate"),
                "enemy_readiness": final_state.get("enemy_readiness"),
                "enemy_pressure": final_state.get("enemy_pressure"),
                "route_health_index": objective_network.get("route_health_index"),
                "objective_pressure_index": objective_network.get("objective_pressure_index"),
                "critical_route_id": objective_network.get("critical_route_id"),
                "critical_objective_id": objective_network.get("critical_objective_id"),
                "contested_asset_ids": objective_network.get("contested_asset_ids", []),
                "routes": objective_network.get("routes", []),
                "objectives": objective_network.get("objectives", []),
                "edges": objective_network.get("edges", []),
            },
            "enemy_posture": enemy_posture,
            "enemy_order_of_battle": enemy_order_of_battle,
            "scenario_tree": {
                "baseline_only": scenario_branch is None,
                "branch_id": scenario_branch.id if scenario_branch is not None else None,
                "parent_run_id": scenario_branch.parent_run_id if scenario_branch is not None else None,
                "child_branch_ids": [branch.id for branch in child_branches],
            },
            "decision_chain": self._build_decision_chain(decision_records),
            "leading_indicators": leading_indicators,
            "scenario_compare": scenario_branch.kpi_trajectory if scenario_branch is not None else [],
            "external_shocks": shock_payloads,
            "strategy_recommendations": recommendations,
            "why_this_happened": why_this_happened,
            "startup_kpi_pack": startup_kpi_pack.model_dump() if startup_kpi_pack is not None else None,
        }

        report = GeneratedReport(
            run_id=simulation_run.id,
            force_id=force.id,
            scenario_id=scenario_branch.id if scenario_branch is not None else None,
            tenant_id=simulation_run.tenant_id,
            preset_id=simulation_run.preset_id,
            title=f"{force.name} military {title_suffix}",
            summary=summary,
            report_format="markdown",
            sections=sections,
        )
        session.add(report)
        await session.flush()
        return report

    async def _load_run_materials(
        self,
        session: AsyncSession,
        run_id: str,
    ) -> tuple[list[DecisionRecordRecord], list[StateSnapshotRecord]]:
        decision_records = list(
            (
                await session.scalars(
                    select(DecisionRecordRecord)
                    .where(DecisionRecordRecord.run_id == run_id)
                    .order_by(DecisionRecordRecord.tick.asc(), DecisionRecordRecord.sequence.asc())
                )
            ).all()
        )
        state_snapshots = list(
            (
                await session.scalars(
                    select(StateSnapshotRecord)
                    .where(StateSnapshotRecord.run_id == run_id)
                    .order_by(StateSnapshotRecord.tick.asc())
                )
            ).all()
        )
        return decision_records, state_snapshots

    def _build_indicator_changes(
        self,
        initial_state: dict,
        final_state: dict,
        tracked_keys: list[str],
    ) -> list[dict[str, float]]:
        indicators: list[dict[str, float]] = []
        for key in tracked_keys:
            if key in initial_state or key in final_state:
                indicators.append(
                    {
                        "metric": key,
                        "start": float(initial_state.get(key, 0.0)),
                        "end": float(final_state.get(key, 0.0)),
                    }
                )
        return indicators

    def _build_decision_chain(self, decision_records: list[DecisionRecordRecord]) -> list[dict[str, object]]:
        return [
            {
                "tick": record.tick,
                "action_id": record.action_id,
                "evidence_ids": record.evidence_ids,
                "policy_rule_ids": record.policy_rule_ids,
                "expected_effect": record.expected_effect,
                "actual_effect": record.actual_effect,
            }
            for record in decision_records
        ]

    def _metrics_by_name(self, indicators: list[dict[str, float]]) -> dict[str, dict[str, float]]:
        return {
            indicator["metric"]: {
                "start": indicator["start"],
                "end": indicator["end"],
            }
            for indicator in indicators
        }

    def _build_company_recommendations(self, final_state: dict) -> list[str]:
        recommendations: list[str] = []
        if float(final_state.get("infra_cost_index", 1.0)) > 1.1:
            recommendations.append("Reduce infrastructure concentration risk before scaling the next release.")
        if float(final_state.get("runway_weeks", 52)) < 40:
            recommendations.append("Preserve cash and revisit hiring until runway stabilizes.")
        if float(final_state.get("gross_margin", 0.62)) < 0.58:
            recommendations.append("Repair gross margin before layering on more custom delivery work.")
        if float(final_state.get("brand_index", 1.0)) < 0.9:
            recommendations.append("Rebuild trust around one workflow with explicit quality and ROI commitments.")
        if float(final_state.get("market_share", 0.05)) < 0.03:
            recommendations.append("Avoid broad platform positioning and narrow into a vertical wedge with higher urgency.")
        if float(final_state.get("pipeline", 1.0)) < 0.85:
            recommendations.append("Rebuild qualified pipeline inside one wedge instead of widening top-of-funnel spend.")
        if float(final_state.get("support_load", 0.35)) > 0.55:
            recommendations.append("Reduce deployment complexity before adding more live customers to the queue.")
        if float(final_state.get("reliability_debt", 0.28)) > 0.4:
            recommendations.append("Schedule a reliability reset to shrink incident debt before the next launch cycle.")
        if float(final_state.get("nrr", 1.02)) < 1.0 or float(final_state.get("churn_risk", 0.12)) > 0.18:
            recommendations.append("Shift the next cycle toward renewals and expansion quality, not just new logo growth.")
        if float(final_state.get("delivery_velocity", 1.0)) < 0.95:
            recommendations.append("Recover delivery velocity with scoped releases and operational cleanup.")
        if not recommendations:
            recommendations.append("Maintain the current pace and monitor for fresh external shocks.")
        return recommendations

    def _build_military_recommendations(self, final_state: dict) -> list[str]:
        recommendations: list[str] = []
        if float(final_state.get("logistics_throughput", 1.0)) < 0.8:
            recommendations.append("Restore logistics resilience before committing additional maneuver.")
        if float(final_state.get("supply_network", 0.84)) < 0.76:
            recommendations.append("Stabilize the route network and corridor control before extending the line of advance.")
        if float(final_state.get("objective_control", 0.5)) < 0.5:
            recommendations.append("Re-secure the decisive objective because positional control is slipping.")
        if float(final_state.get("air_defense", 1.0)) < 0.85:
            recommendations.append("Rebalance air defense coverage before accepting higher drone exposure.")
        if float(final_state.get("enemy_readiness", 0.82)) > 0.8 or float(final_state.get("enemy_pressure", 0.66)) > 0.68:
            recommendations.append("Suppress enemy fires and command loops before taking on additional exposure.")
        if float(final_state.get("recovery_capacity", 0.68)) < 0.6 or float(final_state.get("attrition_rate", 0.18)) > 0.26:
            recommendations.append("Rotate and repair combat elements before attrition outruns recovery.")
        if float(final_state.get("civilian_risk", 0.0)) > 0.55:
            recommendations.append("Increase civilian protection measures before expanding fires.")
        if float(final_state.get("escalation_index", 0.0)) > 0.75:
            recommendations.append("Shift to a lower-visibility posture to slow escalation.")
        if not recommendations:
            recommendations.append("Hold the current posture and keep ISR focused on early warning.")
        return recommendations
