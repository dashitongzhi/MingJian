from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timezone
import html
import re
from typing import Any
from urllib.parse import quote_plus
import xml.etree.ElementTree as ET

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from planagent.config import Settings
from planagent.domain.api import AnalysisRequest, AnalysisResponse, AnalysisSourceRead, AnalysisStepRead
from planagent.domain.models import SourceHealth, utc_now
from planagent.services.openai_client import OpenAIService

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class AnalysisEvent:
    event: str
    payload: dict[str, Any]


@dataclass
class SourceFetchBundle:
    sources: list[AnalysisSourceRead]
    steps: list[AnalysisStepRead]


class AutomatedAnalysisService:
    def __init__(
        self,
        settings: Settings,
        openai_service: OpenAIService | None = None,
    ) -> None:
        self.settings = settings
        self.openai_service = openai_service

    async def analyze(self, payload: AnalysisRequest) -> AnalysisResponse:
        final_result: AnalysisResponse | None = None
        async for event in self.stream_analysis(payload):
            if event.event == "result":
                final_result = AnalysisResponse.model_validate(event.payload)
        if final_result is None:
            raise RuntimeError("Analysis finished without a result payload.")
        return final_result

    async def stream_analysis(self, payload: AnalysisRequest) -> AsyncIterator[AnalysisEvent]:
        query = self._build_query(payload.content)
        domain_id = self._resolve_domain(payload)
        reasoning_steps: list[AnalysisStepRead] = []

        start_step = self._step(
            "received",
            "Received analysis request.",
            (
                f"Domain={domain_id}; auto_fetch_news={payload.auto_fetch_news}; "
                f"sources=news:{payload.include_google_news},reddit:{payload.include_reddit},"
                f"hacker_news:{payload.include_hacker_news},github:{payload.include_github},"
                f"rss:{payload.include_rss_feeds},gdelt:{payload.include_gdelt},"
                f"weather:{payload.include_weather},aviation:{payload.include_aviation},"
                f"x:{payload.include_x}"
            ),
        )
        reasoning_steps.append(start_step)
        yield self._event("step", start_step)

        query_step = self._step("query", "Prepared search query.", query)
        reasoning_steps.append(query_step)
        yield self._event("step", query_step)

        sources: list[AnalysisSourceRead] = []
        if payload.auto_fetch_news:
            fetch_step = self._step("fetch", "Fetching related public sources.", None)
            reasoning_steps.append(fetch_step)
            yield self._event("step", fetch_step)

            fetch_bundle = await self._fetch_related_sources(
                payload=payload,
                query=query,
                domain_id=domain_id,
            )
            sources = fetch_bundle.sources
            for provider_step in fetch_bundle.steps:
                reasoning_steps.append(provider_step)
                yield self._event("step", provider_step)
            for source in sources:
                yield self._event("source", source)

            fetched_step = self._step(
                "fetch_complete",
                "Collected related sources.",
                f"Fetched {len(sources)} items.",
            )
            reasoning_steps.append(fetched_step)
            yield self._event("step", fetched_step)

        synth_step = self._step(
            "synthesis",
            "Synthesizing evidence into a result.",
            f"Using {len(sources)} fetched sources plus the user input.",
        )
        reasoning_steps.append(synth_step)
        yield self._event("step", synth_step)

        analysis = await self._build_analysis(payload, domain_id, query, sources, reasoning_steps)
        yield self._event("result", analysis)

    async def _build_analysis(
        self,
        payload: AnalysisRequest,
        domain_id: str,
        query: str,
        sources: list[AnalysisSourceRead],
        reasoning_steps: list[AnalysisStepRead],
    ) -> AnalysisResponse:
        generated_at = datetime.now(timezone.utc)
        source_payload = [
            {
                "source_type": source.source_type,
                "title": source.title,
                "url": source.url,
                "summary": source.summary,
                "published_at": source.published_at,
            }
            for source in sources
        ]

        if self.openai_service is not None and self.openai_service.is_configured("primary"):
            model_result = await self.openai_service.analyze_topic(
                content=payload.content,
                domain_id=domain_id,
                related_sources=source_payload,
            )
            if model_result is not None:
                model_step = self._step(
                    "model_complete",
                    "Model-backed synthesis completed.",
                    "Returned grounded summary and reasoning trace.",
                )
                return AnalysisResponse(
                    query=query,
                    domain_id=domain_id,
                    status="completed",
                    summary=model_result.summary,
                    reasoning_steps=[
                        *reasoning_steps,
                        *[
                            AnalysisStepRead(stage="reasoning", message=step)
                            for step in model_result.reasoning_steps
                        ],
                        model_step,
                    ],
                    findings=model_result.findings,
                    recommendations=model_result.recommendations,
                    sources=source_payload,
                    generated_at=generated_at,
                )

        fallback_step = self._step(
            "fallback",
            "Using heuristic synthesis.",
            "Model output was unavailable, so the response is based on fetched evidence and simple ranking.",
        )
        findings = self._heuristic_findings(payload.content, sources)
        recommendations = self._heuristic_recommendations(domain_id, sources)
        summary = self._heuristic_summary(query, domain_id, sources)
        return AnalysisResponse(
            query=query,
            domain_id=domain_id,
            status="completed",
            summary=summary,
            reasoning_steps=[
                *reasoning_steps,
                AnalysisStepRead(
                    stage="reasoning",
                    message="Grouped the input into a single working query and collected public source matches.",
                ),
                AnalysisStepRead(
                    stage="reasoning",
                    message="Ranked sources by recency and title relevance, then extracted repeated themes.",
                ),
                fallback_step,
            ],
            findings=findings,
            recommendations=recommendations,
            sources=source_payload,
            generated_at=generated_at,
        )

    async def _fetch_related_sources(
        self,
        payload: AnalysisRequest,
        query: str,
        domain_id: str,
    ) -> SourceFetchBundle:
        results: list[AnalysisSourceRead] = []
        steps: list[AnalysisStepRead] = []
        seen: set[tuple[str, str]] = set()
        providers = [
            (
                "google_news",
                "Google News",
                payload.include_google_news,
                payload.max_news_items,
                lambda: self._fetch_google_news(query, payload.max_news_items),
            ),
            (
                "reddit",
                "Reddit",
                payload.include_reddit,
                payload.max_reddit_items,
                lambda: self._fetch_reddit(query, payload.max_reddit_items, domain_id),
            ),
            (
                "hacker_news",
                "Hacker News",
                payload.include_hacker_news,
                payload.max_tech_items,
                lambda: self._fetch_hacker_news(query, payload.max_tech_items, domain_id),
            ),
            (
                "github",
                "GitHub",
                payload.include_github,
                payload.max_github_items,
                lambda: self._fetch_github_repositories(query, payload.max_github_items, domain_id),
            ),
            (
                "rss",
                "Configured RSS Feeds",
                payload.include_rss_feeds,
                payload.max_rss_items,
                lambda: self._fetch_configured_rss(query, payload.max_rss_items, domain_id),
            ),
            (
                "gdelt",
                "GDELT",
                payload.include_gdelt,
                payload.max_gdelt_items,
                lambda: self._fetch_gdelt_documents(query, payload.max_gdelt_items, domain_id),
            ),
            (
                "weather",
                "Open-Meteo Weather",
                payload.include_weather,
                payload.max_weather_items,
                lambda: self._fetch_weather_context(query, payload.max_weather_items, domain_id),
            ),
            (
                "aviation",
                "OpenSky Aviation",
                payload.include_aviation,
                payload.max_aviation_items,
                lambda: self._fetch_aviation_context(query, payload.max_aviation_items, domain_id),
            ),
            (
                "x",
                "X",
                payload.include_x,
                payload.max_x_items,
                lambda: self._fetch_x_sources(query, payload.max_x_items, domain_id),
            ),
        ]

        for provider_key, provider_label, enabled, limit, fetcher in providers:
            if not enabled:
                steps.append(
                    self._step(
                        "source_skip",
                        f"Skipped {provider_label}.",
                        "Disabled in the request payload.",
                    )
                )
                continue
            if limit <= 0:
                steps.append(
                    self._step(
                        "source_skip",
                        f"Skipped {provider_label}.",
                        "Requested limit is 0.",
                    )
                )
                continue
            if provider_key == "x" and not self.settings.x_enabled:
                steps.append(
                    self._step(
                        "source_skip",
                        "Skipped X.",
                        "Neither PLANAGENT_X_BEARER_TOKEN nor PLANAGENT_OPENAI_X_SEARCH_API_KEY is configured.",
                    )
                )
                continue
            try:
                provider_results = await fetcher()
            except Exception as exc:
                steps.append(
                    self._step(
                        "source_error",
                        f"{provider_label} fetch failed.",
                        self._clean_text(str(exc))[:240],
                    )
                )
                continue

            added = 0
            for source in provider_results:
                dedupe_key = (source.title.lower(), source.url)
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                results.append(source)
                added += 1

            steps.append(
                self._step(
                    "source_complete",
                    f"Collected {added} item(s) from {provider_label}.",
                    f"Requested {limit}; deduped total is now {len(results)}.",
                )
            )

        return SourceFetchBundle(sources=results, steps=steps)

    async def record_source_success(self, session: AsyncSession, source_type: str) -> None:
        record = await self._get_source_health(session, source_type)
        record.status = "OK"
        record.consecutive_failures = 0
        record.last_error = None
        record.last_success_at = utc_now()
        record.updated_at = utc_now()

    async def record_source_failure(self, session: AsyncSession, source_type: str, error: str) -> None:
        record = await self._get_source_health(session, source_type)
        record.consecutive_failures += 1
        record.status = (
            "DEGRADED"
            if record.consecutive_failures >= self.settings.source_failure_degraded_threshold
            else "ERROR"
        )
        record.last_error = self._clean_text(error)[:500]
        record.last_failure_at = utc_now()
        record.updated_at = utc_now()

    async def _get_source_health(self, session: AsyncSession, source_type: str) -> SourceHealth:
        record = (
            await session.scalars(
                select(SourceHealth).where(SourceHealth.source_type == source_type).limit(1)
            )
        ).first()
        if record is None:
            record = SourceHealth(source_type=source_type)
            session.add(record)
            await session.flush()
        return record

    async def _fetch_x_sources(
        self,
        query: str,
        limit: int,
        domain_id: str,
    ) -> list[AnalysisSourceRead]:
        if self.openai_service is not None and self.openai_service.is_configured("x_search"):
            model_results = await self.openai_service.search_x_posts(
                self._platform_query(query, domain_id),
                limit,
            )
            if model_results is not None and model_results.posts:
                results: list[AnalysisSourceRead] = []
                for post in model_results.posts[:limit]:
                    title = self._clean_text(post.title)
                    url = self._clean_text(post.url)
                    summary = self._clean_text(post.summary)
                    if not title or not url or not summary:
                        continue
                    results.append(
                        AnalysisSourceRead(
                            source_type="x_model_search",
                            title=title,
                            url=url,
                            summary=summary,
                            published_at=self._clean_text(post.published_at or "") or None,
                        )
                    )
                if results:
                    return results
            if not self.settings.resolved_x_bearer_token:
                last_error = getattr(self.openai_service, "last_error", None)
                if last_error:
                    raise RuntimeError(last_error)
        return await self._fetch_x_posts(query, limit, domain_id)

    async def _fetch_google_news(self, query: str, limit: int) -> list[AnalysisSourceRead]:
        locale = self._google_news_locale(query)
        url = (
            "https://news.google.com/rss/search"
            f"?q={quote_plus(query)}&hl={locale['hl']}&gl={locale['gl']}&ceid={locale['ceid']}"
        )
        async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
            response = await client.get(url, headers={"User-Agent": "PlanAgent/0.1"})
            response.raise_for_status()

        root = ET.fromstring(response.text)
        items = root.findall(".//item")
        results: list[AnalysisSourceRead] = []
        for item in items[:limit]:
            title = self._clean_text(item.findtext("title", default=""))
            link = self._clean_text(item.findtext("link", default=""))
            description = self._clean_text(item.findtext("description", default=""))
            pub_date = self._clean_text(item.findtext("pubDate", default="")) or None
            if not title or not link:
                continue
            results.append(
                AnalysisSourceRead(
                    source_type="google_news_rss",
                    title=title,
                    url=link,
                    summary=description or title,
                    published_at=pub_date,
                )
            )
        return results

    async def _fetch_github_repositories(
        self,
        query: str,
        limit: int,
        domain_id: str,
    ) -> list[AnalysisSourceRead]:
        if limit <= 0:
            return []

        search_query = self._github_query(query, domain_id)
        repo_limit = max(1, min(limit, max(1, limit // 2)))
        update_limit = max(0, limit - repo_limit)
        url = "https://api.github.com/search/repositories"
        params = {
            "q": search_query,
            "sort": "updated",
            "order": "desc",
            "per_page": str(min(max(repo_limit, 1), 10)),
        }
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "PlanAgent/0.1",
        }
        async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
            issue_payload: dict[str, Any] = {}
            if update_limit > 0:
                issue_response = await client.get(
                    "https://api.github.com/search/issues",
                    params={
                        "q": f"{search_query} is:issue OR is:pr",
                        "sort": "updated",
                        "order": "desc",
                        "per_page": str(min(update_limit, 10)),
                    },
                    headers=headers,
                )
                issue_response.raise_for_status()
                issue_payload = issue_response.json()

        payload = response.json()
        results: list[AnalysisSourceRead] = []
        for repo in payload.get("items", [])[:repo_limit]:
            full_name = self._clean_text(repo.get("full_name") or "")
            html_url = self._clean_text(repo.get("html_url") or "")
            description = self._clean_text(repo.get("description") or "")
            language = self._clean_text(repo.get("language") or "")
            stars = repo.get("stargazers_count")
            updated_at = self._clean_text(repo.get("updated_at") or "") or None
            summary_parts = []
            if description:
                summary_parts.append(description)
            if language:
                summary_parts.append(f"language={language}")
            if isinstance(stars, int):
                summary_parts.append(f"stars={stars}")
            if not full_name or not html_url:
                continue
            results.append(
                AnalysisSourceRead(
                    source_type="github_repository",
                    title=full_name,
                    url=html_url,
                    summary=" | ".join(summary_parts) or full_name,
                    published_at=updated_at,
                )
            )
        for issue in issue_payload.get("items", [])[:update_limit]:
            title = self._clean_text(issue.get("title") or "")
            html_url = self._clean_text(issue.get("html_url") or "")
            state = self._clean_text(issue.get("state") or "")
            updated_at = self._clean_text(issue.get("updated_at") or "") or None
            item_type = "github_pull_request" if issue.get("pull_request") else "github_issue"
            if not title or not html_url:
                continue
            results.append(
                AnalysisSourceRead(
                    source_type=item_type,
                    title=title,
                    url=html_url,
                    summary=f"{item_type} | state={state}" if state else item_type,
                    published_at=updated_at,
                )
            )
        return results

    async def _fetch_configured_rss(
        self,
        query: str,
        limit: int,
        domain_id: str,
    ) -> list[AnalysisSourceRead]:
        feed_urls = self._rss_feed_urls(domain_id)
        if limit <= 0 or not feed_urls:
            return []

        results: list[AnalysisSourceRead] = []
        query_tokens = set(self._ascii_keywords(query.lower()))
        async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
            for feed_url in feed_urls:
                if len(results) >= limit:
                    break
                response = await client.get(feed_url, headers={"User-Agent": "PlanAgent/0.1"})
                response.raise_for_status()
                root = ET.fromstring(response.text)
                for item in root.findall(".//item") + root.findall(".//{http://www.w3.org/2005/Atom}entry"):
                    if len(results) >= limit:
                        break
                    title = self._clean_text(
                        item.findtext("title", default="")
                        or item.findtext("{http://www.w3.org/2005/Atom}title", default="")
                    )
                    link = self._rss_link(item)
                    summary = self._clean_text(
                        item.findtext("description", default="")
                        or item.findtext("summary", default="")
                        or item.findtext("{http://www.w3.org/2005/Atom}summary", default="")
                    )
                    published_at = self._clean_text(
                        item.findtext("pubDate", default="")
                        or item.findtext("published", default="")
                        or item.findtext("{http://www.w3.org/2005/Atom}published", default="")
                    ) or None
                    haystack = f"{title} {summary}".lower()
                    if query_tokens and not any(token.lower() in haystack for token in query_tokens):
                        continue
                    if not title or not link:
                        continue
                    results.append(
                        AnalysisSourceRead(
                            source_type="rss_feed",
                            title=title,
                            url=link,
                            summary=summary or title,
                            published_at=published_at,
                        )
                    )
        return results

    async def _fetch_gdelt_documents(
        self,
        query: str,
        limit: int,
        domain_id: str,
    ) -> list[AnalysisSourceRead]:
        if limit <= 0:
            return []

        gdelt_query = self._gdelt_query(query, domain_id)
        url = "https://api.gdeltproject.org/api/v2/doc/doc"
        params = {
            "query": gdelt_query,
            "mode": "ArtList",
            "format": "json",
            "maxrecords": str(min(max(limit, 1), 10)),
            "sort": "HybridRel",
        }
        async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
            response = await client.get(url, params=params, headers={"User-Agent": "PlanAgent/0.1"})
            response.raise_for_status()
        payload = response.json()
        results: list[AnalysisSourceRead] = []
        for article in payload.get("articles", [])[:limit]:
            title = self._clean_text(article.get("title") or "")
            url_value = self._clean_text(article.get("url") or "")
            source_country = self._clean_text(article.get("sourceCountry") or "")
            domain = self._clean_text(article.get("domain") or "")
            seendate = self._clean_text(article.get("seendate") or "") or None
            summary = " | ".join(part for part in [domain, source_country] if part) or title
            if not title or not url_value:
                continue
            results.append(
                AnalysisSourceRead(
                    source_type="gdelt_document",
                    title=title,
                    url=url_value,
                    summary=summary,
                    published_at=seendate,
                )
            )
        return results

    async def _fetch_weather_context(
        self,
        query: str,
        limit: int,
        domain_id: str,
    ) -> list[AnalysisSourceRead]:
        if limit <= 0 or domain_id != "military":
            return []

        location = self._extract_weather_location(query)
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
                self._clean_text(candidate.get("name") or ""),
                self._clean_text(candidate.get("country") or ""),
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
                published_at=self._clean_text(weather.get("time") or "") or None,
            )
        ]

    async def _fetch_aviation_context(
        self,
        query: str,
        limit: int,
        domain_id: str,
    ) -> list[AnalysisSourceRead]:
        if limit <= 0 or domain_id != "military":
            return []

        bbox = self._aviation_bbox(query)
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
        airborne = sum(1 for state in states if isinstance(state, list) and len(state) > 8 and state[8] is False)
        sample_callsigns = [
            self._clean_text(str(state[1]))
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
                published_at=self._timestamp_to_iso(payload.get("time")),
            )
        ][:limit]

    async def _fetch_hacker_news(
        self,
        query: str,
        limit: int,
        domain_id: str,
    ) -> list[AnalysisSourceRead]:
        search_query = self._platform_query(query, domain_id)
        url = (
            "https://hn.algolia.com/api/v1/search"
            f"?tags=story&hitsPerPage={limit}&query={quote_plus(search_query)}"
        )
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(url, headers={"User-Agent": "PlanAgent/0.1"})
            response.raise_for_status()
        payload = response.json()
        results: list[AnalysisSourceRead] = []
        for hit in payload.get("hits", [])[:limit]:
            title = self._clean_text(hit.get("title") or "")
            url_value = self._clean_text(hit.get("url") or hit.get("story_url") or "")
            summary = self._clean_text(hit.get("_highlightResult", {}).get("title", {}).get("value", "")) or title
            published_at = self._clean_text(hit.get("created_at") or "") or None
            if not title or not url_value:
                continue
            results.append(
                AnalysisSourceRead(
                    source_type="hacker_news",
                    title=title,
                    url=url_value,
                    summary=summary,
                    published_at=published_at,
                )
            )
        return results

    async def _fetch_reddit(
        self,
        query: str,
        limit: int,
        domain_id: str,
    ) -> list[AnalysisSourceRead]:
        if limit <= 0:
            return []

        search_query = self._reddit_query(query, domain_id)
        url = (
            "https://www.reddit.com/search.json"
            f"?q={quote_plus(search_query)}&sort=relevance&t=week&type=link&raw_json=1&limit={limit}"
        )
        async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
            response = await client.get(url, headers={"User-Agent": "PlanAgent/0.1"})
            response.raise_for_status()

        payload = response.json()
        results: list[AnalysisSourceRead] = []
        for child in payload.get("data", {}).get("children", [])[:limit]:
            post = child.get("data", {})
            title = self._clean_text(post.get("title") or "")
            permalink = self._clean_text(post.get("permalink") or "")
            subreddit = self._clean_text(post.get("subreddit_name_prefixed") or "")
            selftext = self._clean_text(post.get("selftext") or "")
            external_url = self._clean_text(post.get("url") or "")
            summary_parts = [part for part in [subreddit, selftext or external_url] if part]
            url_value = f"https://www.reddit.com{permalink}" if permalink else external_url
            if not title or not url_value:
                continue
            results.append(
                AnalysisSourceRead(
                    source_type="reddit_search",
                    title=title,
                    url=url_value,
                    summary=" | ".join(summary_parts) or title,
                    published_at=self._timestamp_to_iso(post.get("created_utc")),
                )
            )
        return results

    async def _fetch_x_posts(
        self,
        query: str,
        limit: int,
        domain_id: str,
    ) -> list[AnalysisSourceRead]:
        if limit <= 0:
            return []

        bearer_token = self.settings.resolved_x_bearer_token
        if not bearer_token:
            return []

        max_results = min(max(limit, 10), 100)
        url = f"{self.settings.x_base_url.rstrip('/')}/tweets/search/recent"
        params = {
            "query": self._x_query(query, domain_id),
            "max_results": str(max_results),
            "tweet.fields": "created_at,author_id",
            "expansions": "author_id",
            "user.fields": "username,name",
        }
        headers = {
            "Authorization": f"Bearer {bearer_token}",
            "User-Agent": "PlanAgent/0.1",
        }
        async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()

        payload = response.json()
        includes = payload.get("includes", {})
        users = {
            item.get("id"): item
            for item in includes.get("users", [])
            if isinstance(item, dict) and item.get("id")
        }
        results: list[AnalysisSourceRead] = []
        for post in payload.get("data", [])[:limit]:
            post_id = self._clean_text(post.get("id") or "")
            text = self._clean_text(post.get("text") or "")
            author = users.get(post.get("author_id"), {})
            username = self._clean_text(author.get("username") or "")
            title = f"X post by @{username}" if username else "X post"
            url_value = (
                f"https://x.com/{username}/status/{post_id}"
                if username and post_id
                else f"https://x.com/i/web/status/{post_id}"
            )
            if not post_id or not text:
                continue
            results.append(
                AnalysisSourceRead(
                    source_type="x_recent_search",
                    title=title,
                    url=url_value,
                    summary=text,
                    published_at=self._clean_text(post.get("created_at") or "") or None,
                )
            )
        return results

    def _resolve_domain(self, payload: AnalysisRequest) -> str:
        if payload.domain_id != "auto":
            return payload.domain_id
        lowered = payload.content.lower()
        if any(keyword in lowered for keyword in ["brigade", "drone", "strike", "theater", "supply line"]):
            return "military"
        if any(keyword in lowered for keyword in ["company", "startup", "gpu", "market", "product"]):
            return "corporate"
        return "general"

    def _build_query(self, content: str) -> str:
        cleaned = self._clean_text(content)
        cleaned = re.sub(r"https?://\S+", " ", cleaned)
        tokens = [token for token in re.split(r"[^\w\u4e00-\u9fff\-]+", cleaned) if token]
        if not tokens:
            return "latest developments"
        return " ".join(tokens[:12])

    def _heuristic_summary(
        self,
        query: str,
        domain_id: str,
        sources: list[AnalysisSourceRead],
    ) -> str:
        if not sources:
            return f"No public sources were fetched for '{query}', so the result is based on the input only."
        top_titles = "; ".join(source.title for source in sources[:3])
        return f"Built a {domain_id} analysis for '{query}' using {len(sources)} public sources. Top evidence: {top_titles}."

    def _heuristic_findings(self, content: str, sources: list[AnalysisSourceRead]) -> list[str]:
        findings: list[str] = []
        if sources:
            findings.extend(source.title for source in sources[:5])
        else:
            findings.append(self._clean_text(content)[:180])
        return findings[:5]

    def _heuristic_recommendations(self, domain_id: str, sources: list[AnalysisSourceRead]) -> list[str]:
        if domain_id == "military":
            return [
                "Re-check logistics and threat signals before committing additional maneuver.",
                "Track any fresh ISR, air defense, and civilian-risk indicators over the next cycle.",
            ]
        if domain_id == "corporate":
            return [
                "Validate whether the reported demand or cost signals are sustained across multiple sources.",
                "Map the reported changes to product, pricing, and runway impact before acting.",
            ]
        if sources:
            return ["Review the top repeated themes and decide whether they change the working assessment."]
        return ["Provide a narrower topic or enable auto-fetch to improve coverage."]

    def _google_news_locale(self, query: str) -> dict[str, str]:
        if any("\u4e00" <= char <= "\u9fff" for char in query):
            return {"hl": "zh-CN", "gl": "CN", "ceid": "CN:zh-Hans"}
        return {"hl": "en-US", "gl": "US", "ceid": "US:en"}

    def _reddit_query(self, query: str, domain_id: str) -> str:
        base_query = self._platform_query(query, domain_id)
        if domain_id == "military":
            return f"{base_query} conflict defense military"
        if domain_id == "corporate":
            return f"{base_query} startup company market AI"
        return base_query

    def _x_query(self, query: str, domain_id: str) -> str:
        return f"({self._platform_query(query, domain_id)}) -is:retweet"

    def _github_query(self, query: str, domain_id: str) -> str:
        base_query = self._platform_query(query, domain_id)
        if domain_id == "corporate":
            return f"{base_query} AI startup OR agents"
        if domain_id == "military":
            return f"{base_query} OSINT OR defense"
        return base_query

    def _gdelt_query(self, query: str, domain_id: str) -> str:
        base_query = self._platform_query(query, domain_id)
        if domain_id == "military":
            return f"({base_query}) (military OR defense OR maritime OR aviation OR weather OR OSINT)"
        if domain_id == "corporate":
            return f"({base_query}) (company OR startup OR market OR product OR funding)"
        return base_query

    def _rss_feed_urls(self, domain_id: str) -> list[str]:
        configured = [
            item.strip()
            for item in self.settings.additional_rss_feeds.split(",")
            if item.strip()
        ]
        defaults = {
            "corporate": [
                "https://github.blog/feed/",
                "https://openai.com/news/rss.xml",
            ],
            "military": [
                "https://www.understandingwar.org/feeds.xml",
                "https://www.defense.gov/DesktopModules/ArticleCS/RSS.ashx?ContentType=1&Site=945",
            ],
        }
        return [*configured, *defaults.get(domain_id, [])]

    def _rss_link(self, item: ET.Element) -> str:
        link = self._clean_text(item.findtext("link", default=""))
        if link:
            return link
        atom_link = item.find("{http://www.w3.org/2005/Atom}link")
        if atom_link is not None:
            return self._clean_text(atom_link.attrib.get("href", ""))
        return ""

    def _extract_weather_location(self, query: str) -> str | None:
        match = re.search(r"\b(?:near|around|in|at)\s+([A-Za-z][A-Za-z\s-]{2,40})", query)
        if match:
            return match.group(1).strip()
        tokens = self._ascii_keywords(query)
        if len(tokens) >= 2:
            return " ".join(tokens[:2])
        return tokens[0] if tokens else None

    def _aviation_bbox(self, query: str) -> tuple[float, float, float, float, str] | None:
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

    def _platform_query(self, query: str, domain_id: str) -> str:
        if not self._contains_cjk(query):
            return query
        tokens = self._ascii_keywords(query)
        tokens.extend(self._domain_keywords(domain_id))
        normalized_tokens = list(dict.fromkeys(token for token in tokens if token))
        return " ".join(normalized_tokens) or query

    def _domain_keywords(self, domain_id: str) -> list[str]:
        if domain_id == "military":
            return ["defense", "military", "drone", "conflict"]
        if domain_id == "corporate":
            return ["AI", "startup", "company", "market"]
        return ["AI", "technology", "news"]

    def _ascii_keywords(self, value: str) -> list[str]:
        return re.findall(r"[A-Za-z0-9][A-Za-z0-9.+_-]*", value)[:8]

    def _contains_cjk(self, value: str) -> bool:
        return any("\u4e00" <= char <= "\u9fff" for char in value)

    def _timestamp_to_iso(self, value: Any) -> str | None:
        if value in (None, ""):
            return None
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
        except (TypeError, ValueError, OSError):
            return None

    def _clean_text(self, value: str) -> str:
        text = html.unescape(value or "")
        text = _HTML_TAG_RE.sub(" ", text)
        return _WHITESPACE_RE.sub(" ", text).strip()

    def _step(self, stage: str, message: str, detail: str | None = None) -> AnalysisStepRead:
        return AnalysisStepRead(stage=stage, message=message, detail=detail)

    def _event(self, event: str, payload: AnalysisStepRead | AnalysisSourceRead | AnalysisResponse) -> AnalysisEvent:
        return AnalysisEvent(event=event, payload=payload.model_dump(mode="json"))
