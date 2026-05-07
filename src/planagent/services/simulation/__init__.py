from __future__ import annotations

from planagent.config import Settings
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
from planagent.services.evidence_weighting import EvidenceWeightingService
from planagent.services.openai_client import OpenAIService
from planagent.services.reporting import ReportService
from planagent.services.simulation_military import MilitaryCombatResolver
from planagent.simulation.domain_packs import registry
from planagent.simulation.rules import RuleRegistry, RuleSpec

from .domain_packs import SimulationDomainPacksMixin
from .engine import SimulationEngineMixin
from .impact import ActionCandidate, RuleScore, SelectedAction, SimulationImpactMixin
from .report import SimulationReportMixin
from .scenarios import SimulationScenariosMixin


class SimulationService(
    SimulationEngineMixin,
    SimulationScenariosMixin,
    SimulationImpactMixin,
    SimulationReportMixin,
    SimulationDomainPacksMixin,
):
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
        self.evidence_weighting = EvidenceWeightingService(settings)


__all__ = [
    "ActionCandidate",
    "Claim",
    "CompanyProfile",
    "DecisionRecordRecord",
    "EventArchive",
    "ExternalShockRecord",
    "ForceProfile",
    "GeoAssetRecord",
    "GeneratedReport",
    "RuleScore",
    "RuleSpec",
    "ScenarioBranchRecord",
    "SelectedAction",
    "SimulationService",
    "SimulationRun",
    "StateSnapshotRecord",
    "generate_id",
    "registry",
    "utc_now",
]
