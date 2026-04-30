"""Military combat resolution logic extracted from SimulationService.

Contains enemy response selection, fire exchange resolution, force recovery,
and operational picture building for military domain simulations.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from planagent.domain.models import GeoAssetRecord, MilitaryResolution, SimulationRun, generate_id, utc_now
from planagent.services.simulation import OperationalResponse, SelectedAction, Claim


class MilitaryCombatResolver:
    """Encapsulates military combat resolution logic for simulation runs."""

    def resolve_military_action_outcome(
        self,
        state: dict[str, float],
        selected: SelectedAction,
        active_claim: Claim | None,
        enemy_history: list[str],
    ) -> MilitaryResolution:
        projected_state = deepcopy(state)
        _apply_effects(projected_state, selected.actual_effect)

        enemy_response = self._select_enemy_response(projected_state, active_claim, enemy_history)
        _apply_effects(projected_state, enemy_response.effects)

        exchange_effect, fire_balance = self._resolve_fire_exchange(
            projected_state,
            selected.action_id,
            enemy_response.action_id,
        )
        _apply_effects(projected_state, exchange_effect)

        recovery_effect = self._resolve_force_recovery(
            projected_state,
            selected.action_id,
            enemy_response.action_id,
        )

        combined_effect = _merge_effects(
            selected.actual_effect,
            enemy_response.effects,
            exchange_effect,
            recovery_effect,
        )
        return MilitaryResolution(
            actual_effect=combined_effect,
            enemy_action_id=enemy_response.action_id,
            enemy_reason=enemy_response.why_selected,
            fire_balance=fire_balance,
            objective_delta=round(combined_effect.get("objective_control", 0.0), 4),
            supply_delta=round(combined_effect.get("supply_network", 0.0), 4),
            recovery_delta=round(
                combined_effect.get("recovery_capacity", 0.0) - combined_effect.get("attrition_rate", 0.0),
                4,
            ),
        )

    def _select_enemy_response(
        self,
        state: dict[str, float],
        active_claim: Claim | None,
        enemy_history: list[str],
    ) -> OperationalResponse:
        lowered = active_claim.statement.lower() if active_claim is not None else ""
        candidates: list[tuple[float, OperationalResponse]] = []

        def add_candidate(
            action_id: str,
            score: float,
            why_selected: str,
            effects: dict[str, float],
        ) -> None:
            penalty = _response_history_penalty(action_id, enemy_history)
            candidates.append(
                (
                    round(score - penalty, 4),
                    OperationalResponse(
                        action_id=action_id,
                        why_selected=why_selected,
                        effects=_clean_effects(effects),
                    ),
                )
            )

        if (
            any(keyword in lowered for keyword in ["supply", "bridge", "convoy", "corridor", "port"])
            or float(state.get("logistics_throughput", 1.0)) < 0.82
            or float(state.get("supply_network", 0.84)) < 0.78
        ):
            supply_gap = max(
                0.0,
                max(0.82 - float(state.get("logistics_throughput", 1.0)), 0.78 - float(state.get("supply_network", 0.84))),
            )
            add_candidate(
                "enemy_probe_supply",
                0.82 + (supply_gap * 0.45),
                "Enemy pressure stayed focused on corridors and depots to keep the force undersupplied.",
                {
                    "logistics_throughput": -0.08,
                    "supply_network": -0.09,
                    "objective_control": -0.04,
                    "enemy_pressure": 0.05,
                    "attrition_rate": 0.02,
                },
            )

        if (
            any(keyword in lowered for keyword in ["drone", "swarm", "strike", "civilian"])
            or float(state.get("air_defense", 1.0)) < 0.84
            or float(state.get("civilian_risk", 0.25)) > 0.42
        ):
            air_gap = max(
                0.0,
                max(0.84 - float(state.get("air_defense", 1.0)), float(state.get("civilian_risk", 0.25)) - 0.42),
            )
            add_candidate(
                "enemy_fire_raid",
                0.8 + (air_gap * 0.45),
                "Enemy fires and drones exploited gaps in air defense and civilian protection.",
                {
                    "readiness": -0.06,
                    "air_defense": -0.05,
                    "civilian_risk": 0.05,
                    "escalation_index": 0.04,
                    "enemy_pressure": 0.06,
                    "attrition_rate": 0.03,
                },
            )

        if (
            any(keyword in lowered for keyword in ["jam", "electronic", "cyber"])
            or float(state.get("command_cohesion", 1.0)) < 0.8
            or float(state.get("ew_control", 1.0)) < 0.76
        ):
            c2_gap = max(
                0.0,
                max(0.8 - float(state.get("command_cohesion", 1.0)), 0.76 - float(state.get("ew_control", 1.0))),
            )
            add_candidate(
                "enemy_jam_c2",
                0.76 + (c2_gap * 0.45),
                "Enemy electronic pressure targeted the command loop to slow response times.",
                {
                    "ew_control": -0.06,
                    "command_cohesion": -0.05,
                    "information_advantage": -0.05,
                    "enemy_pressure": 0.04,
                    "objective_control": -0.02,
                },
            )

        if (
            any(keyword in lowered for keyword in ["crossing", "objective", "district", "axis", "sector"])
            or float(state.get("objective_control", 0.5)) < 0.54
        ):
            objective_gap = max(0.0, 0.54 - float(state.get("objective_control", 0.5)))
            add_candidate(
                "enemy_press_objective",
                0.78 + (objective_gap * 0.5),
                "Enemy maneuver stayed fixed on the contested objective network and its approaches.",
                {
                    "objective_control": -0.08,
                    "mobility": -0.04,
                    "enemy_pressure": 0.06,
                    "civilian_risk": 0.03,
                    "attrition_rate": 0.02,
                },
            )

        if float(state.get("enemy_readiness", 0.82)) < 0.7:
            add_candidate(
                "enemy_regroup",
                0.64 + max(0.0, 0.72 - float(state.get("enemy_readiness", 0.82))) * 0.35,
                "Enemy paused the tempo long enough to rotate forces and regenerate combat power.",
                {
                    "enemy_readiness": 0.06,
                    "enemy_pressure": -0.03,
                    "objective_control": 0.01,
                },
            )

        if not candidates:
            return OperationalResponse(
                action_id="enemy_press_objective",
                why_selected="Enemy kept steady positional pressure against the contested objective.",
                effects=_clean_effects(
                    {
                        "objective_control": -0.05,
                        "enemy_pressure": 0.04,
                        "attrition_rate": 0.02,
                    }
                ),
            )
        return max(candidates, key=lambda item: item[0])[1]

    def _resolve_fire_exchange(
        self,
        state: dict[str, float],
        friendly_action_id: str,
        enemy_action_id: str,
    ) -> tuple[dict[str, float], float]:
        friendly_action_bonus = {
            "open_supply_line": 0.08,
            "rebalance_air_defense": 0.05,
            "increase_isr": 0.06,
            "fortify": 0.03,
            "commit_reserves": 0.05,
            "protect_civilians": -0.01,
            "deescalate_posture": -0.03,
            "secure_objective": 0.09,
            "suppress_enemy_fires": 0.07,
            "rotate_and_repair": -0.02,
        }
        enemy_action_bonus = {
            "enemy_probe_supply": 0.07,
            "enemy_fire_raid": 0.08,
            "enemy_jam_c2": 0.06,
            "enemy_press_objective": 0.09,
            "enemy_regroup": -0.03,
        }

        command_delay = max(0.0, 0.82 - float(state.get("command_cohesion", 0.82))) * 0.35
        ew_delay = max(0.0, 0.78 - float(state.get("ew_control", 0.78))) * 0.22
        route_friction = (
            max(0.0, 0.8 - float(state.get("logistics_throughput", 0.8))) * 0.28
            + max(0.0, 0.78 - float(state.get("supply_network", 0.78))) * 0.24
        )
        friendly_power = (
            (float(state.get("readiness", 0.9)) * 0.24)
            + (float(state.get("ammo", 0.8)) * 0.08)
            + (float(state.get("isr_coverage", 0.8)) * 0.14)
            + (float(state.get("ew_control", 0.75)) * 0.08)
            + (float(state.get("air_defense", 0.78)) * 0.1)
            + (float(state.get("logistics_throughput", 0.9)) * 0.12)
            + (float(state.get("supply_network", 0.84)) * 0.07)
            + (float(state.get("mobility", 0.88)) * 0.08)
            + (float(state.get("command_cohesion", 0.86)) * 0.08)
            + (float(state.get("objective_control", 0.52)) * 0.09)
            + (float(state.get("recovery_capacity", 0.68)) * 0.06)
            + (float(state.get("information_advantage", 0.82)) * 0.08)
            + friendly_action_bonus.get(friendly_action_id, 0.0)
            - (float(state.get("attrition_rate", 0.18)) * 0.18)
            - (float(state.get("civilian_risk", 0.28)) * 0.06)
            - command_delay
            - ew_delay
            - route_friction
        )
        enemy_power = (
            (float(state.get("enemy_readiness", 0.82)) * 0.42)
            + (float(state.get("enemy_pressure", 0.66)) * 0.28)
            + ((1.0 - float(state.get("objective_control", 0.52))) * 0.12)
            + ((1.0 - float(state.get("air_defense", 0.78))) * 0.07)
            + ((1.0 - float(state.get("supply_network", 0.84))) * 0.05)
            + enemy_action_bonus.get(enemy_action_id, 0.0)
        )
        fire_balance = round(max(-0.75, min(0.75, friendly_power - enemy_power)), 4)
        positive_balance = max(fire_balance, 0.0)
        negative_balance = max(-fire_balance, 0.0)
        return (
            _clean_effects(
                {
                    "readiness": (0.035 * positive_balance) - (0.06 * negative_balance),
                    "enemy_readiness": (-0.08 * positive_balance) + (0.03 * negative_balance),
                    "attrition_rate": (-0.05 * positive_balance) + (0.07 * negative_balance),
                    "objective_control": 0.075 * fire_balance,
                    "enemy_pressure": (-0.07 * positive_balance) + (0.06 * negative_balance),
                    "supply_network": 0.05 * fire_balance,
                    "logistics_throughput": 0.035 * fire_balance,
                    "civilian_risk": (0.04 * negative_balance) - (0.025 * positive_balance),
                    "escalation_index": (0.03 * negative_balance) - (0.018 * positive_balance),
                }
            ),
            fire_balance,
        )

    def _resolve_force_recovery(
        self,
        state: dict[str, float],
        friendly_action_id: str,
        enemy_action_id: str,
    ) -> dict[str, float]:
        recovery_window = (
            (float(state.get("recovery_capacity", 0.68)) * 0.35)
            + (float(state.get("logistics_throughput", 0.9)) * 0.25)
            + (float(state.get("supply_network", 0.84)) * 0.2)
            + (float(state.get("command_cohesion", 0.86)) * 0.1)
            - (float(state.get("attrition_rate", 0.18)) * 0.25)
            - (float(state.get("enemy_pressure", 0.66)) * 0.08)
        )
        recovery_gain = max(0.0, recovery_window - 0.32)
        repair_bonus = 0.03 if friendly_action_id in {"commit_reserves", "rotate_and_repair", "open_supply_line"} else 0.0
        recovery_capacity_delta = 0.0
        if friendly_action_id in {"commit_reserves", "rotate_and_repair"}:
            recovery_capacity_delta += 0.02
        if enemy_action_id == "enemy_fire_raid":
            recovery_capacity_delta -= 0.015
        return _clean_effects(
            {
                "readiness": (recovery_gain * 0.05) + repair_bonus,
                "attrition_rate": -(recovery_gain * 0.06) - (0.03 if friendly_action_id == "rotate_and_repair" else 0.0),
                "recovery_capacity": recovery_capacity_delta,
                "enemy_pressure": -(recovery_gain * 0.03),
                "objective_control": (0.02 * recovery_gain) if friendly_action_id == "secure_objective" else 0.0,
            }
        )

    def build_military_operational_picture(
        self,
        run: SimulationRun,
        geo_assets: list[GeoAssetRecord],
        state: dict[str, float],
        *,
        enemy_action_id: str | None,
        enemy_reason: str | None,
    ) -> dict[str, Any]:
        objective_network = self._build_objective_network(geo_assets, state)
        enemy_order_of_battle = self._build_enemy_order_of_battle(
            run.actor_template,
            str(run.configuration.get("theater") or "unknown-theater"),
            state,
            objective_network,
        )
        enemy_posture = self._build_enemy_posture(
            state,
            objective_network,
            enemy_order_of_battle,
            enemy_action_id=enemy_action_id,
            enemy_reason=enemy_reason,
        )
        return {
            "objective_network": objective_network,
            "enemy_posture": enemy_posture,
            "enemy_order_of_battle": enemy_order_of_battle,
        }

    def _build_objective_network(
        self,
        geo_assets: list[GeoAssetRecord],
        state: dict[str, float],
    ) -> dict[str, Any]:
        if not geo_assets:
            return {}

        assets_by_name = {asset.name: asset for asset in geo_assets}
        route_nodes: list[dict[str, Any]] = []
        objective_nodes: list[dict[str, Any]] = []
        edge_keys: set[tuple[str, str, str]] = set()
        edges: list[dict[str, Any]] = []
        contested_asset_ids: list[str] = []

        for asset in geo_assets:
            status = _operational_asset_status(asset, state)
            connected_to = [
                str(name)
                for name in asset.properties.get("connected_to", [])
                if name in assets_by_name
            ]
            if status in {"contested", "at_risk", "degraded"}:
                contested_asset_ids.append(asset.id)
            for neighbor_name in connected_to:
                neighbor = assets_by_name[neighbor_name]
                edge_type = "route_link" if asset.asset_type in {"supply_hub", "supply_route", "bridge"} else "support_link"
                edge_key = tuple(sorted((asset.id, neighbor.id)) + [edge_type])
                if edge_key in edge_keys:
                    continue
                edge_keys.add(edge_key)
                edges.append(
                    {
                        "source_id": asset.id,
                        "target_id": neighbor.id,
                        "edge_type": edge_type,
                    }
                )

            if asset.asset_type in {"supply_hub", "supply_route", "bridge"}:
                route_nodes.append(
                    {
                        "asset_id": asset.id,
                        "name": asset.name,
                        "asset_type": asset.asset_type,
                        "status": status,
                        "connected_to": connected_to,
                        "route_health": _route_health(asset.asset_type, state),
                        "interdiction_risk": _route_interdiction_risk(asset.asset_type, state),
                    }
                )
            if asset.asset_type in {"objective_zone", "civilian_area", "command_post", "staging_area", "isr_node"}:
                objective_nodes.append(
                    {
                        "asset_id": asset.id,
                        "name": asset.name,
                        "asset_type": asset.asset_type,
                        "status": status,
                        "connected_to": connected_to,
                        "control_score": _objective_control_score(asset.asset_type, state),
                        "pressure_score": _objective_pressure_score(asset.asset_type, state),
                    }
                )

        critical_route = min(
            route_nodes,
            key=lambda item: (item["route_health"] - item["interdiction_risk"], item["route_health"]),
            default=None,
        )
        critical_objective = min(
            objective_nodes,
            key=lambda item: (item["control_score"] - item["pressure_score"], item["control_score"]),
            default=None,
        )
        return {
            "route_health_index": _clamp(
                (float(state.get("supply_network", 0.84)) * 0.55)
                + (float(state.get("logistics_throughput", 0.9)) * 0.45)
            ),
            "objective_pressure_index": _clamp(
                (float(state.get("enemy_pressure", 0.66)) * 0.55)
                + ((1.0 - float(state.get("objective_control", 0.5))) * 0.45)
            ),
            "routes": route_nodes,
            "objectives": objective_nodes,
            "edges": edges,
            "critical_route_id": critical_route["asset_id"] if critical_route is not None else None,
            "critical_objective_id": critical_objective["asset_id"] if critical_objective is not None else None,
            "contested_asset_ids": contested_asset_ids,
        }

    def _build_enemy_order_of_battle(
        self,
        actor_template: str,
        theater: str,
        state: dict[str, float],
        objective_network: dict[str, Any],
    ) -> list[dict[str, Any]]:
        templates = {
            "brigade": [
                ("Red Recon Group", "targeting", "objective_zone"),
                ("Red Fires Battalion", "counter_mobility", "supply_route"),
                ("Red Drone Strike Cell", "air_pressure", "civilian_area"),
                ("Red EW Detachment", "c2_disruption", "command_post"),
                ("Red Reserve Company", "objective_seizure", "objective_zone"),
            ],
            "air_defense_battalion": [
                ("Strike Aviation Cell", "air_suppression", "air_defense_site"),
                ("Rocket Fires Battery", "corridor_interdiction", "supply_route"),
                ("EW Assault Team", "c2_disruption", "command_post"),
                ("Drone Saturation Group", "civilian_pressure", "civilian_area"),
            ],
        }
        units = templates.get(actor_template, templates["brigade"])
        target_lookup = {
            node["asset_type"]: node["name"]
            for node in objective_network.get("objectives", []) + objective_network.get("routes", [])
        }
        pressure_band = _band_label(float(state.get("enemy_pressure", 0.66)), high=0.7, low=0.52)
        readiness_band = _band_label(float(state.get("enemy_readiness", 0.82)), high=0.8, low=0.66)
        order_of_battle: list[dict[str, Any]] = []
        for index, (unit_name, role, preferred_target_type) in enumerate(units):
            status = "committed"
            if role in {"objective_seizure", "air_suppression"} and readiness_band == "high":
                status = "surging"
            elif role in {"targeting", "c2_disruption"} and pressure_band == "medium":
                status = "probing"
            elif readiness_band == "low":
                status = "regenerating"
            order_of_battle.append(
                {
                    "unit_id": f"enemy-{actor_template}-{index + 1}",
                    "name": unit_name,
                    "role": role,
                    "theater": theater,
                    "status": status,
                    "strength_band": readiness_band,
                    "pressure_band": pressure_band,
                    "target_asset_type": preferred_target_type,
                    "target_asset_name": target_lookup.get(preferred_target_type),
                }
            )
        return order_of_battle

    def _build_enemy_posture(
        self,
        state: dict[str, float],
        objective_network: dict[str, Any],
        enemy_order_of_battle: list[dict[str, Any]],
        *,
        enemy_action_id: str | None,
        enemy_reason: str | None,
    ) -> dict[str, Any]:
        action_focus = {
            "enemy_probe_supply": {
                "focus": "logistics interdiction",
                "target_asset_types": ["supply_route", "bridge", "supply_hub"],
                "likely_next_actions": ["enemy_probe_supply", "enemy_fire_raid", "enemy_jam_c2"],
            },
            "enemy_fire_raid": {
                "focus": "fire strikes and air pressure",
                "target_asset_types": ["civilian_area", "objective_zone", "air_defense_site"],
                "likely_next_actions": ["enemy_fire_raid", "enemy_press_objective", "enemy_probe_supply"],
            },
            "enemy_jam_c2": {
                "focus": "command-loop disruption",
                "target_asset_types": ["command_post", "isr_node"],
                "likely_next_actions": ["enemy_jam_c2", "enemy_probe_supply", "enemy_press_objective"],
            },
            "enemy_press_objective": {
                "focus": "objective seizure",
                "target_asset_types": ["objective_zone", "staging_area", "civilian_area"],
                "likely_next_actions": ["enemy_press_objective", "enemy_fire_raid", "enemy_probe_supply"],
            },
            "enemy_regroup": {
                "focus": "combat regeneration",
                "target_asset_types": ["staging_area", "command_post"],
                "likely_next_actions": ["enemy_regroup", "enemy_press_objective", "enemy_fire_raid"],
            },
        }
        selected_profile = action_focus.get(
            enemy_action_id or "",
            {
                "focus": "positional pressure",
                "target_asset_types": ["objective_zone", "supply_route"],
                "likely_next_actions": ["enemy_press_objective", "enemy_probe_supply", "enemy_fire_raid"],
            },
        )
        target_asset_ids = [
            node["asset_id"]
            for node in objective_network.get("objectives", []) + objective_network.get("routes", [])
            if node["asset_type"] in selected_profile["target_asset_types"]
        ]
        critical_axis = (
            objective_network.get("critical_objective_id")
            or objective_network.get("critical_route_id")
        )
        readiness_band = _band_label(float(state.get("enemy_readiness", 0.82)), high=0.8, low=0.66)
        pressure_band = _band_label(float(state.get("enemy_pressure", 0.66)), high=0.7, low=0.52)
        return {
            "dominant_action": enemy_action_id or "enemy_press_objective",
            "focus": selected_profile["focus"],
            "readiness_band": readiness_band,
            "pressure_band": pressure_band,
            "critical_axis_asset_id": critical_axis,
            "target_asset_ids": target_asset_ids[:4],
            "likely_next_actions": selected_profile["likely_next_actions"],
            "summary": enemy_reason
            or f"Enemy posture remains centered on {selected_profile['focus']} across the contested axis.",
            "order_of_battle": enemy_order_of_battle,
        }


# ── Module-level helper functions ──────────────────────────────────────────


def _response_history_penalty(action_id: str, enemy_history: list[str]) -> float:
    penalty = 0.0
    for distance, previous_action in enumerate(reversed(enemy_history[-2:]), start=1):
        if previous_action != action_id:
            continue
        penalty += 0.18 if distance == 1 else 0.08
    return round(penalty, 4)


def _merge_effects(*effects: dict[str, float]) -> dict[str, float]:
    merged: dict[str, float] = {}
    for effect in effects:
        for key, value in effect.items():
            merged[key] = merged.get(key, 0.0) + float(value)
    return _clean_effects(merged)


def _clean_effects(effect: dict[str, float]) -> dict[str, float]:
    return {
        key: round(float(value), 4)
        for key, value in effect.items()
        if abs(float(value)) >= 0.0001
    }


def _operational_asset_status(
    asset: GeoAssetRecord,
    state: dict[str, float],
) -> str:
    if asset.asset_type in {"supply_hub", "bridge"} and float(state.get("logistics_throughput", 1.0)) < 0.8:
        return "contested"
    if asset.asset_type == "supply_route" and float(state.get("supply_network", 0.84)) < 0.78:
        return "contested"
    if asset.asset_type == "objective_zone" and float(state.get("objective_control", 0.5)) < 0.5:
        return "contested"
    if asset.asset_type == "civilian_area" and float(state.get("civilian_risk", 0.0)) > 0.55:
        return "at_risk"
    if asset.asset_type in {"air_defense_site", "command_post"} and float(state.get("air_defense", 1.0)) < 0.85:
        return "degraded"
    return "active"


def _route_health(
    asset_type: str,
    state: dict[str, float],
) -> float:
    modifier = {
        "supply_hub": 0.02,
        "bridge": -0.03,
        "supply_route": -0.01,
    }.get(asset_type, 0.0)
    return _clamp(
        (float(state.get("supply_network", 0.84)) * 0.45)
        + (float(state.get("logistics_throughput", 0.9)) * 0.35)
        + (float(state.get("mobility", 0.88)) * 0.1)
        + (float(state.get("command_cohesion", 0.86)) * 0.1)
        + modifier
    )


def _route_interdiction_risk(
    asset_type: str,
    state: dict[str, float],
) -> float:
    modifier = {
        "bridge": 0.05,
        "supply_route": 0.04,
        "supply_hub": -0.02,
    }.get(asset_type, 0.0)
    return _clamp(
        (float(state.get("enemy_pressure", 0.66)) * 0.42)
        + ((1.0 - float(state.get("air_defense", 0.78))) * 0.16)
        + ((1.0 - float(state.get("information_advantage", 0.82))) * 0.12)
        + ((1.0 - float(state.get("objective_control", 0.5))) * 0.1)
        + modifier
    )


def _objective_control_score(
    asset_type: str,
    state: dict[str, float],
) -> float:
    modifier = {
        "objective_zone": -0.04,
        "command_post": 0.02,
        "civilian_area": -0.02,
        "staging_area": 0.01,
        "isr_node": 0.02,
    }.get(asset_type, 0.0)
    return _clamp(
        (float(state.get("objective_control", 0.5)) * 0.55)
        + (float(state.get("readiness", 0.9)) * 0.15)
        + (float(state.get("information_advantage", 0.82)) * 0.12)
        + (float(state.get("mobility", 0.88)) * 0.08)
        + (float(state.get("command_cohesion", 0.86)) * 0.1)
        + modifier
    )


def _objective_pressure_score(
    asset_type: str,
    state: dict[str, float],
) -> float:
    modifier = {
        "objective_zone": 0.05,
        "civilian_area": 0.04,
        "command_post": 0.03,
        "staging_area": 0.02,
        "isr_node": -0.02,
    }.get(asset_type, 0.0)
    return _clamp(
        (float(state.get("enemy_pressure", 0.66)) * 0.48)
        + (float(state.get("enemy_readiness", 0.82)) * 0.18)
        + (float(state.get("civilian_risk", 0.28)) * 0.08)
        + ((1.0 - float(state.get("air_defense", 0.78))) * 0.1)
        + ((1.0 - float(state.get("objective_control", 0.5))) * 0.16)
        + modifier
    )


def _band_label(
    value: float,
    *,
    high: float,
    low: float,
) -> str:
    if value >= high:
        return "high"
    if value <= low:
        return "low"
    return "medium"


def _clamp(
    value: float,
    *,
    minimum: float = 0.0,
    maximum: float = 1.0,
) -> float:
    return round(max(minimum, min(maximum, float(value))), 4)


def _apply_effects(state: dict[str, float], effect: dict[str, float]) -> None:
    """Apply effect deltas to state in-place."""
    for key, delta in effect.items():
        current = float(state.get(key, 0.0))
        state[key] = round(current + float(delta), 4)
