from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from planagent.domain.api import SimulationRunCreate
from planagent.domain.models import (
    CompanyProfile,
    ExternalShockRecord,
    ForceProfile,
    GeoAssetRecord,
    SimulationRun,
    utc_now,
)
from planagent.services.pipeline import normalize_text


class SimulationDomainPacksMixin:
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

    async def _ensure_geo_assets_for_run(
        self,
        session: AsyncSession,
        run: SimulationRun,
        force: ForceProfile,
    ) -> None:
        existing = (
            await session.scalars(
                select(GeoAssetRecord).where(GeoAssetRecord.run_id == run.id).limit(1)
            )
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
                    properties=self._decorate_asset_properties(
                        run, seed["asset_type"], seed["properties"]
                    ),
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
                "properties": {
                    "role": "route_network",
                    "route_id": "corridor-east",
                    "connected_to": ["Primary Supply Hub", "River Crossing Bridge"],
                },
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
                "properties": {
                    "role": "decisive_terrain",
                    "objective_id": "bastion",
                    "connected_to": ["Civilian District Alpha", "Command Post Echo"],
                },
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
        if (
            asset_type in {"supply_hub", "bridge"}
            and float(state.get("logistics_throughput", 1.0)) < 0.8
        ):
            properties["status"] = "contested"
        if asset_type == "supply_route" and float(state.get("supply_network", 0.84)) < 0.78:
            properties["status"] = "contested"
        if asset_type == "civilian_area" and float(state.get("civilian_risk", 0.0)) > 0.55:
            properties["status"] = "at_risk"
        if asset_type == "objective_zone" and float(state.get("objective_control", 0.5)) < 0.5:
            properties["status"] = "contested"
        if (
            asset_type in {"air_defense_site", "command_post"}
            and float(state.get("air_defense", 1.0)) < 0.85
        ):
            properties["status"] = "degraded"
        return properties

    async def _upsert_company(
        self, session: AsyncSession, payload: SimulationRunCreate
    ) -> CompanyProfile:
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

    async def _upsert_force(
        self, session: AsyncSession, payload: SimulationRunCreate
    ) -> ForceProfile:
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
        template_map = {
            template.actor_type: template.default_state for template in pack.actor_templates
        }
        return {
            **default_state,
            **{key: float(value) for key, value in template_map.get(actor_template, {}).items()},
        }

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
