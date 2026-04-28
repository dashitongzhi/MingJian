from __future__ import annotations

from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from planagent.domain.api import (
    DebateSummaryRead,
    EvidenceGraphEdgeRead,
    EvidenceGraphNodeRead,
    EvidenceGraphRead,
    GeoMapRead,
    KPIComparatorRead,
    KPIMetricRead,
    ReviewItemRead,
    RunWorkbenchRead,
    ScenarioTreeRead,
    TimelineEventRead,
)
from planagent.domain.models import (
    Claim,
    CompanyProfile,
    DebateSessionRecord,
    DebateVerdictRecord,
    DecisionRecordRecord,
    EvidenceItem,
    ExternalShockRecord,
    ForceProfile,
    GeneratedReport,
    ReviewItem,
    ScenarioBranchRecord,
    SimulationRun,
    StateSnapshotRecord,
)
from planagent.services.startup import build_startup_kpi_pack, resolve_run_preset_id, resolve_run_tenant_id


class WorkbenchService:
    async def build_run_workbench(
        self,
        session: AsyncSession,
        run_id: str,
    ) -> RunWorkbenchRead:
        run = await session.get(SimulationRun, run_id)
        if run is None:
            raise LookupError(f"Simulation run {run_id} was not found.")

        decision_trace = list(
            (
                await session.scalars(
                    select(DecisionRecordRecord)
                    .where(DecisionRecordRecord.run_id == run.id)
                    .order_by(DecisionRecordRecord.tick.asc(), DecisionRecordRecord.sequence.asc())
                )
            ).all()
        )
        state_snapshots = list(
            (
                await session.scalars(
                    select(StateSnapshotRecord)
                    .where(StateSnapshotRecord.run_id == run.id)
                    .order_by(StateSnapshotRecord.tick.asc())
                )
            ).all()
        )
        latest_report = (
            await session.scalars(
                select(GeneratedReport)
                .where(GeneratedReport.run_id == run.id)
                .order_by(GeneratedReport.created_at.desc())
                .limit(1)
            )
        ).first()

        review_queue = await self._load_review_queue(session, run)
        graph = await self._build_evidence_graph(session, run)
        geo_map = self._build_geo_map(run, latest_report)
        scenario_tree = await self._build_scenario_tree(session, run)
        comparator = await self._build_kpi_comparator(session, run, state_snapshots)
        debates = await self._list_run_debates(session, run.id)
        timeline = await self._build_timeline(session, run, decision_trace, debates, latest_report)
        start_state = state_snapshots[0].state if state_snapshots else {}
        final_state = state_snapshots[-1].state if state_snapshots else {}
        startup_kpi_pack = build_startup_kpi_pack(
            run,
            start_state,
            final_state,
            run.summary.get("matched_rules", []),
        )

        return RunWorkbenchRead(
            run_id=run.id,
            domain_id=run.domain_id,
            tenant_id=resolve_run_tenant_id(run),
            preset_id=resolve_run_preset_id(run),
            latest_report_id=latest_report.id if latest_report is not None else None,
            review_queue=review_queue,
            evidence_graph=graph,
            timeline=timeline,
            geo_map=geo_map,
            scenario_tree=scenario_tree,
            decision_trace=[
                {
                    "id": record.id,
                    "tick": record.tick,
                    "sequence": record.sequence,
                    "actor_id": record.actor_id,
                    "action_id": record.action_id,
                    "why_selected": record.why_selected,
                    "evidence_ids": record.evidence_ids,
                    "policy_rule_ids": record.policy_rule_ids,
                    "expected_effect": record.expected_effect,
                    "actual_effect": record.actual_effect,
                    "debate_verdict_id": record.debate_verdict_id,
                    "created_at": record.created_at,
                }
                for record in decision_trace
            ],
            kpi_comparator=comparator,
            startup_kpi_pack=startup_kpi_pack,
            debate_records=debates,
        )

    async def _load_review_queue(
        self,
        session: AsyncSession,
        run: SimulationRun,
    ) -> list[ReviewItemRead]:
        evidence_ids = [str(value) for value in run.summary.get("evidence_ids", [])]
        predicates = await self._claim_predicates_for_run(session, run)
        query = (
            select(ReviewItem)
            .join(Claim, Claim.id == ReviewItem.claim_id)
            .order_by(ReviewItem.created_at.desc())
        )
        tenant_filters: list[Any] = []
        relevance_filters: list[Any] = []
        if run.tenant_id is not None:
            tenant_filters.append(ReviewItem.tenant_id == run.tenant_id)
        if run.preset_id is not None:
            tenant_filters.append(ReviewItem.preset_id == run.preset_id)
        if evidence_ids:
            relevance_filters.append(Claim.evidence_item_id.in_(evidence_ids))
        if predicates:
            relevance_filters.append(or_(*predicates))
        if tenant_filters:
            query = query.where(*tenant_filters)
        if relevance_filters:
            query = query.where(or_(*relevance_filters))
        items = list((await session.scalars(query)).all())
        return [ReviewItemRead.model_validate(item) for item in items]

    async def _build_evidence_graph(
        self,
        session: AsyncSession,
        run: SimulationRun,
    ) -> EvidenceGraphRead:
        claims = await self._load_relevant_claims(session, run)
        evidence_ids = sorted({claim.evidence_item_id for claim in claims})
        evidence_items = []
        if evidence_ids:
            evidence_items = list(
                (
                    await session.scalars(
                        select(EvidenceItem)
                        .where(EvidenceItem.id.in_(evidence_ids))
                    )
                ).all()
            )
        nodes: list[EvidenceGraphNodeRead] = []
        edges: list[EvidenceGraphEdgeRead] = []
        subject_nodes: set[str] = set()
        object_nodes: set[str] = set()

        for evidence in evidence_items:
            nodes.append(
                EvidenceGraphNodeRead(
                    node_id=evidence.id,
                    label=evidence.title,
                    node_type="evidence",
                    metadata={"source_url": evidence.source_url, "confidence": evidence.confidence},
                )
            )

        for claim in claims:
            nodes.append(
                EvidenceGraphNodeRead(
                    node_id=claim.id,
                    label=claim.statement,
                    node_type="claim",
                    metadata={"confidence": claim.confidence, "status": claim.status},
                )
            )
            edges.append(
                EvidenceGraphEdgeRead(
                    source_id=claim.evidence_item_id,
                    target_id=claim.id,
                    relation_type="supports",
                    metadata={},
                )
            )
            subject_id = f"subject:{claim.subject}"
            object_id = f"object:{claim.object_text}"
            if subject_id not in subject_nodes:
                subject_nodes.add(subject_id)
                nodes.append(
                    EvidenceGraphNodeRead(
                        node_id=subject_id,
                        label=claim.subject,
                        node_type="entity",
                        metadata={"role": "subject"},
                    )
                )
            if object_id not in object_nodes:
                object_nodes.add(object_id)
                nodes.append(
                    EvidenceGraphNodeRead(
                        node_id=object_id,
                        label=claim.object_text,
                        node_type="entity",
                        metadata={"role": "object"},
                    )
                )
            edges.append(
                EvidenceGraphEdgeRead(
                    source_id=claim.id,
                    target_id=subject_id,
                    relation_type="mentions_subject",
                    metadata={"predicate": claim.predicate},
                )
            )
            edges.append(
                EvidenceGraphEdgeRead(
                    source_id=claim.id,
                    target_id=object_id,
                    relation_type="mentions_object",
                    metadata={"predicate": claim.predicate},
                )
            )

        return EvidenceGraphRead(nodes=nodes, edges=edges)

    def _build_geo_map(
        self,
        run: SimulationRun,
        latest_report: GeneratedReport | None,
    ) -> GeoMapRead:
        if run.domain_id != "military":
            return GeoMapRead(
                mode="abstract",
                note="Corporate geo assets are not materialized in the Phase 4 MVP workbench yet.",
                assets=[],
                network={},
                overlays={},
            )

        geo_map = (latest_report.sections.get("geo_map") if latest_report is not None else None) or {}
        return GeoMapRead(
            mode="geo",
            theater=geo_map.get("theater") or run.configuration.get("theater"),
            assets=geo_map.get("assets", []),
            network=latest_report.sections.get("objective_network", {}) if latest_report is not None else {},
            overlays=(
                {
                    "enemy_posture": latest_report.sections.get("enemy_posture", {}),
                    "enemy_order_of_battle": latest_report.sections.get("enemy_order_of_battle", []),
                    "combat_exchange": latest_report.sections.get("combat_exchange", []),
                }
                if latest_report is not None
                else {}
            ),
            note=None if geo_map.get("assets") else "No geo assets available for this run.",
        )

    async def _build_scenario_tree(
        self,
        session: AsyncSession,
        run: SimulationRun,
    ) -> ScenarioTreeRead:
        baseline_run = run
        active_branch_id: str | None = None
        if run.parent_run_id is not None:
            parent_run = await session.get(SimulationRun, run.parent_run_id)
            if parent_run is not None:
                baseline_run = parent_run
            branch = (
                await session.scalars(
                    select(ScenarioBranchRecord).where(ScenarioBranchRecord.run_id == run.id).limit(1)
                )
            ).first()
            active_branch_id = branch.id if branch is not None else None

        branches = list(
            (
                await session.scalars(
                    select(ScenarioBranchRecord)
                    .where(ScenarioBranchRecord.parent_run_id == baseline_run.id)
                    .order_by(ScenarioBranchRecord.created_at.asc())
                )
            ).all()
        )
        nodes = [
            {
                "node_type": "baseline",
                "run_id": baseline_run.id,
                "branch_id": None,
                "parent_run_id": None,
                "fork_step": None,
                "active": baseline_run.id == run.id,
            }
        ]
        for branch in branches:
            nodes.append(
                {
                    "node_type": "branch",
                    "run_id": branch.run_id,
                    "branch_id": branch.id,
                    "parent_run_id": branch.parent_run_id,
                    "fork_step": branch.fork_step,
                    "probability_band": branch.probability_band,
                    "active": branch.run_id == run.id,
                }
            )
        return ScenarioTreeRead(
            baseline_run_id=baseline_run.id,
            active_run_id=run.id,
            active_branch_id=active_branch_id,
            nodes=nodes,
        )

    async def _build_kpi_comparator(
        self,
        session: AsyncSession,
        run: SimulationRun,
        state_snapshots: list[StateSnapshotRecord],
    ) -> KPIComparatorRead:
        baseline_run = run
        if run.parent_run_id is not None:
            parent_run = await session.get(SimulationRun, run.parent_run_id)
            if parent_run is not None:
                baseline_run = parent_run

        baseline_state = (
            await session.scalars(
                select(StateSnapshotRecord)
                .where(StateSnapshotRecord.run_id == baseline_run.id)
                .order_by(StateSnapshotRecord.tick.desc())
                .limit(1)
            )
        ).first()
        start_state = state_snapshots[0].state if state_snapshots else {}
        final_state = state_snapshots[-1].state if state_snapshots else {}
        baseline_final = baseline_state.state if baseline_state is not None else {}

        keys = sorted(
            {
                key
                for key, value in {**start_state, **final_state, **baseline_final}.items()
                if isinstance(value, (int, float))
            }
        )
        metrics = [
            KPIMetricRead(
                metric=key,
                start=float(start_state.get(key, 0.0)) if key in start_state else None,
                end=float(final_state.get(key, 0.0)) if key in final_state else None,
                baseline_end=float(baseline_final.get(key, 0.0)) if key in baseline_final else None,
                delta=(
                    round(float(final_state.get(key, 0.0)) - float(start_state.get(key, 0.0)), 4)
                    if key in start_state or key in final_state
                    else None
                ),
            )
            for key in keys
        ]
        return KPIComparatorRead(
            baseline_run_id=baseline_run.id,
            current_run_id=run.id,
            metrics=metrics,
        )

    async def _list_run_debates(
        self,
        session: AsyncSession,
        run_id: str,
    ) -> list[DebateSummaryRead]:
        debates = list(
            (
                await session.scalars(
                    select(DebateSessionRecord)
                    .where(DebateSessionRecord.run_id == run_id)
                    .order_by(DebateSessionRecord.created_at.desc())
                )
            ).all()
        )
        verdicts = {
            item.debate_id: item
            for item in (
                await session.scalars(
                    select(DebateVerdictRecord).where(
                        DebateVerdictRecord.debate_id.in_([debate.id for debate in debates] or [""])
                    )
                )
            ).all()
        }
        return [
            DebateSummaryRead(
                debate_id=debate.id,
                topic=debate.topic,
                trigger_type=debate.trigger_type,
                verdict=verdicts.get(debate.id).verdict if debate.id in verdicts else None,
                confidence=verdicts.get(debate.id).confidence if debate.id in verdicts else None,
                created_at=debate.created_at,
            )
            for debate in debates
        ]

    async def _build_timeline(
        self,
        session: AsyncSession,
        run: SimulationRun,
        decision_trace: list[DecisionRecordRecord],
        debates: list[DebateSummaryRead],
        latest_report: GeneratedReport | None,
    ) -> list[TimelineEventRead]:
        timeline: list[TimelineEventRead] = []
        shocks = list(
            (
                await session.scalars(
                    select(ExternalShockRecord)
                    .where(ExternalShockRecord.run_id == run.id)
                    .order_by(ExternalShockRecord.tick.asc(), ExternalShockRecord.created_at.asc())
                )
            ).all()
        )
        child_branches = list(
            (
                await session.scalars(
                    select(ScenarioBranchRecord)
                    .where(ScenarioBranchRecord.parent_run_id == run.id)
                    .order_by(ScenarioBranchRecord.created_at.asc())
                )
            ).all()
        )

        for shock in shocks:
            timeline.append(
                TimelineEventRead(
                    event_id=shock.id,
                    event_type="external_shock",
                    tick=shock.tick,
                    title=shock.shock_type,
                    detail=shock.summary,
                    related_ids=shock.evidence_ids,
                    created_at=shock.created_at,
                )
            )
        for record in decision_trace:
            related_ids = [*record.evidence_ids]
            if record.debate_verdict_id:
                related_ids.append(record.debate_verdict_id)
            timeline.append(
                TimelineEventRead(
                    event_id=record.id,
                    event_type="decision",
                    tick=record.tick,
                    title=record.action_id,
                    detail=record.why_selected,
                    related_ids=related_ids,
                    created_at=record.created_at,
                )
            )
        for debate in debates:
            timeline.append(
                TimelineEventRead(
                    event_id=debate.debate_id,
                    event_type="debate",
                    tick=None,
                    title=debate.topic,
                    detail=f"Verdict={debate.verdict or 'pending'}",
                    related_ids=[debate.debate_id],
                    created_at=debate.created_at,
                )
            )
        for branch in child_branches:
            timeline.append(
                TimelineEventRead(
                    event_id=branch.id,
                    event_type="scenario_branch_created",
                    tick=branch.fork_step,
                    title=f"Scenario branch {branch.id}",
                    detail=branch.evidence_summary,
                    related_ids=[branch.run_id],
                    created_at=branch.created_at,
                )
            )
        if latest_report is not None:
            timeline.append(
                TimelineEventRead(
                    event_id=latest_report.id,
                    event_type="report_generated",
                    tick=run.tick_count,
                    title=latest_report.title,
                    detail=latest_report.summary,
                    related_ids=[latest_report.id],
                    created_at=latest_report.created_at,
                )
            )
        return sorted(
            timeline,
            key=lambda item: (item.tick is None, item.tick or 10**9, item.created_at),
        )

    async def _load_relevant_claims(
        self,
        session: AsyncSession,
        run: SimulationRun,
    ) -> list[Claim]:
        evidence_ids = [str(value) for value in run.summary.get("evidence_ids", [])]
        query = select(Claim).order_by(Claim.created_at.asc())
        if run.tenant_id is not None:
            query = query.where(Claim.tenant_id == run.tenant_id)
        if run.preset_id is not None:
            query = query.where(Claim.preset_id == run.preset_id)
        if evidence_ids:
            query = query.where(Claim.evidence_item_id.in_(evidence_ids))
        else:
            predicates = await self._claim_predicates_for_run(session, run)
            if predicates:
                query = query.where(or_(*predicates))
        return list((await session.scalars(query)).all())

    async def _claim_predicates_for_run(
        self,
        session: AsyncSession,
        run: SimulationRun,
    ) -> list[Any]:
        terms = await self._subject_terms(session, run)
        predicates: list[Any] = []
        for term in terms:
            lowered = term.lower()
            predicates.extend(
                [
                    Claim.statement.ilike(f"%{lowered}%"),
                    Claim.subject.ilike(f"%{lowered}%"),
                    Claim.object_text.ilike(f"%{lowered}%"),
                ]
            )
        return predicates

    async def _subject_terms(self, session: AsyncSession, run: SimulationRun) -> list[str]:
        if run.company_id:
            company = await session.get(CompanyProfile, run.company_id)
            if company is not None:
                return [company.name, company.id, company.market]
        if run.force_id:
            force = await session.get(ForceProfile, run.force_id)
            if force is not None:
                return [force.name, force.id, force.theater]
        return [run.id]
