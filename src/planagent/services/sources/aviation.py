"""OpenSky aviation data source provider."""

from __future__ import annotations

from typing import Any

import httpx

from planagent.domain.api import AnalysisSourceRead
from planagent.services.sources.base import DataSourceProvider


class AviationProvider(DataSourceProvider):
    key = "aviation"
    label = "OpenSky Aviation"
    default_enabled = False
    default_limit = 1
    agent_name = "航空探员"
    agent_icon = "✈️"
    task_desc = "正在获取航空数据"

    async def fetch(
        self, query: str, limit: int, domain_id: str,
    ) -> list[AnalysisSourceRead]:
        if limit <= 0 or domain_id != "military":
            return []

        bbox = self._bbox(query)
        if bbox is None:
            return []
        lamin, lomin, lamax, lomax, label = bbox
        async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
            response = await client.get(
                "https://opensky-network.org/api/states/all",
                params={
                    "lamin": str(lamin),
                    "lomin": str(lomin),
                    "lamax": str(lamax),
                    "lomax": str(lomax),
                },
                headers={"User-Agent": "PlanAgent/0.1"},
            )
            response.raise_for_status()
        payload = response.json()
        states = payload.get("states") or []
        if not isinstance(states, list):
            states = []
        aircraft_count = len(states)
        airborne = sum(
            1 for state in states if isinstance(state, list) and len(state) > 8 and state[8] is False
        )
        sample_callsigns = [
            self.clean_text(str(state[1]))
            for state in states[: min(5, len(states))]
            if isinstance(state, list) and len(state) > 1 and state[1]
        ]
        summary = (
            f"aircraft_count={aircraft_count}; airborne={airborne}; "
            f"sample_callsigns={', '.join(sample_callsigns) if sample_callsigns else 'none'}"
        )
        return [
            AnalysisSourceRead(
                source_type="opensky_air_traffic",
                title=f"OpenSky aviation snapshot near {label}",
                url="https://opensky-network.org/",
                summary=summary,
                published_at=self.timestamp_to_iso(payload.get("time")),
                metadata={
                    "platform": "opensky",
                    "provider": "opensky",
                    "engagement": {"aircraft_count": aircraft_count, "airborne": airborne},
                    "query_used": query,
                },
            )
        ][:limit]

    def _bbox(self, query: str) -> tuple[float, float, float, float, str] | None:
        lowered = query.lower()
        if any(token in lowered for token in ["taiwan", "台海", "台湾", "taipei"]):
            return (21.5, 118.0, 26.5, 123.5, "Taiwan Strait")
        if any(token in lowered for token in ["odessa", "ukraine", "black sea", "乌克兰", "敖德萨"]):
            return (44.0, 28.0, 49.8, 38.0, "Ukraine and Black Sea")
        if any(token in lowered for token in ["red sea", "yemen", "hormuz", "红海", "也门", "霍尔木兹"]):
            return (11.0, 32.0, 28.5, 58.5, "Red Sea and Gulf lanes")
        if any(token in lowered for token in ["eastern-sector", "eastern sector"]):
            return (46.0, 31.0, 50.5, 38.5, "Eastern sector")
        return None
