"""Open-Meteo weather data source provider."""

from __future__ import annotations

import re

import httpx

from planagent.domain.api import AnalysisSourceRead
from planagent.services.sources.base import DataSourceProvider


class WeatherProvider(DataSourceProvider):
    key = "weather"
    label = "Open-Meteo Weather"
    default_enabled = False
    default_limit = 1
    agent_name = "气象探员"
    agent_icon = "🌤️"
    task_desc = "正在获取气象数据"

    async def fetch(
        self, query: str, limit: int, domain_id: str,
    ) -> list[AnalysisSourceRead]:
        if limit <= 0 or domain_id != "military":
            return []

        location = self._extract_location(query)
        if not location:
            return []
        async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
            geo_response = await client.get(
                "https://geocoding-api.open-meteo.com/v1/search",
                params={"name": location, "count": "1", "language": "en", "format": "json"},
                headers={"User-Agent": "PlanAgent/0.1"},
            )
            geo_response.raise_for_status()
            geo_payload = geo_response.json()
            candidates = geo_payload.get("results", [])
            if not candidates:
                return []
            candidate = candidates[0]
            weather_response = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": str(candidate["latitude"]),
                    "longitude": str(candidate["longitude"]),
                    "current": "temperature_2m,precipitation,wind_speed_10m",
                    "timezone": "UTC",
                },
                headers={"User-Agent": "PlanAgent/0.1"},
            )
            weather_response.raise_for_status()
        weather = weather_response.json().get("current", {})
        place = ", ".join(
            part
            for part in [
                self.clean_text(candidate.get("name") or ""),
                self.clean_text(candidate.get("country") or ""),
            ]
            if part
        )
        summary = (
            f"temperature={weather.get('temperature_2m')}; "
            f"precipitation={weather.get('precipitation')}; "
            f"wind_speed={weather.get('wind_speed_10m')}"
        )
        return [
            AnalysisSourceRead(
                source_type="open_meteo_weather",
                title=f"Weather context for {place or location}",
                url="https://open-meteo.com/",
                summary=summary,
                published_at=self.clean_text(weather.get("time") or "") or None,
                metadata={
                    "platform": "open_meteo",
                    "provider": "open_meteo",
                    "query_used": query,
                },
            )
        ]

    def _extract_location(self, query: str) -> str | None:
        match = re.search(r"\b(?:near|around|in|at)\s+([A-Za-z][A-Za-z\s-]{2,40})", query)
        if match:
            return match.group(1).strip()
        tokens = self.ascii_keywords(query)
        if len(tokens) >= 2:
            return " ".join(tokens[:2])
        return tokens[0] if tokens else None
