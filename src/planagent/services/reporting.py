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
        initial_state = state_snapshots[0].state if state_snapshots else {}
        final_state = state_snapshots[-1].state if state_snapshots else {}
        actions = [record.action_id for record in decision_records]
        leading_indicators = self._build_indicator_changes(
            initial_state,
            final_state,
            ["runway_weeks", "delivery_velocity", "brand_index", "market_share", "cash"],
        )
        matched_rules = simulation_run.summary.get("matched_rules", [])

        summary = (
            f"{company.name} completed {simulation_run.tick_count} corporate ticks with "
            f"{len(actions)} recorded decisions. Final runway is {final_state.get('runway_weeks', 'n/a')} weeks "
            f"and delivery velocity is {final_state.get('delivery_velocity', 'n/a')}."
        )
        recommendations = self._build_company_recommendations(final_state)
        why_this_happened = {
            "key_evidence": simulation_run.summary.get("evidence_statements", []),
            "rules_hit": matched_rules,
            "actions_taken": actions,
            "metric_changes": self._metrics_by_name(leading_indicators),
        }

        if self.openai_service is not None and self.openai_service.enabled:
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
            "scenario_tree": {"baseline_only": True, "note": "Branching starts in Phase 3."},
            "decision_chain": self._build_decision_chain(decision_records),
            "leading_indicators": leading_indicators,
            "strategy_recommendations": recommendations,
            "why_this_happened": why_this_happened,
        }

        report = GeneratedReport(
            run_id=simulation_run.id,
            company_id=company.id,
            title=f"{company.name} corporate baseline report",
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
                "isr_coverage",
                "air_defense",
                "civilian_risk",
                "escalation_index",
            ],
        )
        matched_rules = simulation_run.summary.get("matched_rules", [])
        title_suffix = "scenario report" if scenario_branch is not None else "baseline report"
        summary = (
            f"{force.name} in {force.theater} completed {simulation_run.tick_count} military ticks with "
            f"{len(actions)} recorded decisions. Final readiness is {final_state.get('readiness', 'n/a')} and "
            f"logistics throughput is {final_state.get('logistics_throughput', 'n/a')}."
        )
        recommendations = self._build_military_recommendations(final_state)
        why_this_happened = {
            "key_evidence": simulation_run.summary.get("evidence_statements", []),
            "rules_hit": matched_rules,
            "actions_taken": actions,
            "metric_changes": self._metrics_by_name(leading_indicators),
        }
        if scenario_branch is not None:
            why_this_happened["scenario_assumptions"] = scenario_branch.assumptions
            why_this_happened["decision_deltas"] = scenario_branch.decision_deltas

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
            },
            "scenario_tree": {
                "baseline_only": scenario_branch is None,
                "branch_id": scenario_branch.id if scenario_branch is not None else None,
                "parent_run_id": scenario_branch.parent_run_id if scenario_branch is not None else None,
                "child_branch_ids": [branch.id for branch in child_branches],
            },
            "decision_chain": self._build_decision_chain(decision_records),
            "leading_indicators": leading_indicators,
            "scenario_compare": scenario_branch.kpi_trajectory if scenario_branch is not None else [],
            "external_shocks": [
                {
                    "tick": shock.tick,
                    "shock_type": shock.shock_type,
                    "summary": shock.summary,
                    "evidence_ids": shock.evidence_ids,
                }
                for shock in external_shocks
            ],
            "strategy_recommendations": recommendations,
            "why_this_happened": why_this_happened,
        }

        report = GeneratedReport(
            run_id=simulation_run.id,
            force_id=force.id,
            scenario_id=scenario_branch.id if scenario_branch is not None else None,
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
        if float(final_state.get("delivery_velocity", 1.0)) < 0.95:
            recommendations.append("Recover delivery velocity with scoped releases and operational cleanup.")
        if not recommendations:
            recommendations.append("Maintain the current pace and monitor for fresh external shocks.")
        return recommendations

    def _build_military_recommendations(self, final_state: dict) -> list[str]:
        recommendations: list[str] = []
        if float(final_state.get("logistics_throughput", 1.0)) < 0.8:
            recommendations.append("Restore logistics resilience before committing additional maneuver.")
        if float(final_state.get("air_defense", 1.0)) < 0.85:
            recommendations.append("Rebalance air defense coverage before accepting higher drone exposure.")
        if float(final_state.get("civilian_risk", 0.0)) > 0.55:
            recommendations.append("Increase civilian protection measures before expanding fires.")
        if float(final_state.get("escalation_index", 0.0)) > 0.75:
            recommendations.append("Shift to a lower-visibility posture to slow escalation.")
        if not recommendations:
            recommendations.append("Hold the current posture and keep ISR focused on early warning.")
        return recommendations
