from __future__ import annotations

from planagent.simulation.domain_packs import DomainPack, registry
from planagent.simulation.specs import ActionSpec, ActorTemplate, EntityTypeSpec, EventTypeSpec, StateFieldSpec


class MilitaryDomainPack(DomainPack):
    @property
    def domain_id(self) -> str:
        return "military"

    @property
    def entity_types(self) -> list[EntityTypeSpec]:
        return [
            EntityTypeSpec("force_unit", "Deployable force element."),
            EntityTypeSpec("base", "Airbase, port, or logistics hub."),
        ]

    @property
    def state_fields(self) -> list[StateFieldSpec]:
        return [
            StateFieldSpec("readiness", "Current operational readiness.", 1.0),
            StateFieldSpec("ammo", "Available munitions index.", 1.0),
            StateFieldSpec("fuel", "Available fuel index.", 1.0),
            StateFieldSpec("isr_coverage", "Reconnaissance and sensor coverage.", 1.0),
            StateFieldSpec("ew_control", "Electronic warfare control.", 1.0),
            StateFieldSpec("air_defense", "Air and counter-drone coverage.", 1.0),
            StateFieldSpec("logistics_throughput", "Available logistics throughput.", 1.0),
            StateFieldSpec("mobility", "Freedom of maneuver.", 1.0),
            StateFieldSpec("command_cohesion", "Command and control coherence.", 1.0),
            StateFieldSpec("civilian_risk", "Civilian exposure risk.", 0.25),
            StateFieldSpec("escalation_index", "Current escalation pressure.", 0.3),
            StateFieldSpec("ally_support", "External support confidence.", 0.7),
            StateFieldSpec("attrition_rate", "Operating loss rate.", 0.2),
            StateFieldSpec("information_advantage", "Relative information advantage.", 1.0),
        ]

    @property
    def action_library(self) -> list[ActionSpec]:
        return [
            ActionSpec("redeploy", "Reposition forces to a new area."),
            ActionSpec("fortify", "Increase protection around a critical asset."),
            ActionSpec("increase_isr", "Improve reconnaissance and targeting awareness."),
            ActionSpec("rebalance_air_defense", "Shift air defense coverage to the threatened axis."),
            ActionSpec("open_supply_line", "Restore or create logistics access."),
            ActionSpec("commit_reserves", "Commit reserve units to stabilize the front."),
            ActionSpec("protect_civilians", "Reduce exposure around civilian areas."),
            ActionSpec("deescalate_posture", "Reduce visible posture to manage escalation."),
        ]

    @property
    def event_types(self) -> list[EventTypeSpec]:
        return [
            EventTypeSpec("supply_disruption", "A logistics path was interrupted."),
            EventTypeSpec("weather_window", "Weather changed operational constraints."),
            EventTypeSpec("drone_swarm", "Drone activity changed the local threat picture."),
            EventTypeSpec("electronic_attack", "Electronic or cyber pressure disrupted command systems."),
        ]

    @property
    def actor_templates(self) -> list[ActorTemplate]:
        return [
            ActorTemplate(
                "brigade",
                {
                    "readiness": 0.9,
                    "ammo": 0.8,
                    "fuel": 0.85,
                    "isr_coverage": 0.8,
                    "ew_control": 0.75,
                    "air_defense": 0.78,
                    "logistics_throughput": 0.9,
                    "mobility": 0.88,
                    "command_cohesion": 0.86,
                    "civilian_risk": 0.28,
                    "escalation_index": 0.35,
                    "ally_support": 0.72,
                    "attrition_rate": 0.18,
                    "information_advantage": 0.82,
                },
            ),
            ActorTemplate(
                "air_defense_battalion",
                {
                    "readiness": 0.95,
                    "ammo": 0.7,
                    "fuel": 0.8,
                    "isr_coverage": 0.85,
                    "ew_control": 0.82,
                    "air_defense": 0.92,
                    "logistics_throughput": 0.8,
                    "mobility": 0.7,
                    "command_cohesion": 0.84,
                    "civilian_risk": 0.24,
                    "escalation_index": 0.32,
                    "ally_support": 0.75,
                    "attrition_rate": 0.16,
                    "information_advantage": 0.88,
                },
            ),
        ]


registry.register(MilitaryDomainPack())
