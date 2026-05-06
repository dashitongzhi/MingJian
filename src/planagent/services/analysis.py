from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timezone
import html
import inspect
import logging
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from planagent.config import Settings
from planagent.domain.api import AnalysisRequest, AnalysisResponse, AnalysisSourceRead, AnalysisStepRead
from planagent.domain.models import SourceHealth, utc_now
from planagent.services.openai_client import OpenAIService
from planagent.services.sources.registry import SourceRegistry

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")
logger = logging.getLogger(__name__)


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
        self.source_registry = SourceRegistry(settings, openai_service)

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

            fetch_bundle: SourceFetchBundle | None = None
            try:
                async for fetch_item in self._fetch_related_sources_with_events(payload, query, domain_id):
                    if isinstance(fetch_item, AnalysisEvent):
                        yield fetch_item
                    else:
                        fetch_bundle = fetch_item
            except Exception as exc:
                logger.warning("Source fetching with events failed: %s", exc)
                fetch_bundle = SourceFetchBundle(sources=[], steps=[
                    self._step("fetch_error", "Source fetching failed.", str(exc)[:240])
                ])
            if fetch_bundle is None:
                fetch_bundle = SourceFetchBundle(sources=[], steps=[
                    self._step("fetch_error", "Source fetching returned no result.", None)
                ])
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

    async def _fetch_related_sources_with_events(
        self,
        payload: AnalysisRequest,
        query: str,
        domain_id: str,
    ) -> AsyncIterator[AnalysisEvent | SourceFetchBundle]:
        event_queue: asyncio.Queue[AnalysisEvent] = asyncio.Queue()
        parameters = inspect.signature(self._fetch_related_sources).parameters
        kwargs: dict[str, Any] = {}
        if "event_queue" in parameters:
            kwargs["event_queue"] = event_queue

        fetch_task = asyncio.create_task(
            self._fetch_related_sources(payload=payload, query=query, domain_id=domain_id, **kwargs)
        )

        while True:
            event_task = asyncio.create_task(event_queue.get())
            done, pending = await asyncio.wait(
                {fetch_task, event_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            # Only cancel event_task, NEVER cancel fetch_task
            for task in pending:
                if task is not fetch_task:
                    task.cancel()

            if event_task in done:
                try:
                    yield event_task.result()
                except Exception:
                    pass  # event queue item failed; skip

            if fetch_task in done:
                while not event_queue.empty():
                    try:
                        yield event_queue.get_nowait()
                    except Exception:
                        pass
                try:
                    yield fetch_task.result()
                except Exception as exc:
                    logger.warning("Source fetch task failed: %s", exc)
                    yield SourceFetchBundle(sources=[], steps=[
                        self._step("fetch_error", "Source fetching failed.", str(exc)[:240])
                    ])
                return

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
                "metadata": source.metadata,
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
        event_queue: asyncio.Queue[AnalysisEvent] | None = None,
    ) -> SourceFetchBundle:
        results: list[AnalysisSourceRead] = []
        steps_by_adapter: list[AnalysisStepRead | None] = []
        seen: set[tuple[str, str]] = set()
        adapters = self.source_registry.build_adapters(payload, query, domain_id)
        fetch_requests: list[tuple[int, Any, int]] = []
        tasks: list[Any] = []

        async def fetch_with_timeout(adapter, limit: int) -> list[AnalysisSourceRead]:
            async with asyncio.timeout(30):
                return await adapter.fetch(limit)

        async def emit(event: str, payload_data: dict[str, Any]) -> None:
            if event_queue is not None:
                await event_queue.put(self._event(event, payload_data))

        for index, adapter in enumerate(adapters):
            provider_key = adapter.key
            provider_label = adapter.label
            if not adapter.enabled:
                steps_by_adapter.append(
                    self._step(
                        "source_skip",
                        f"Skipped {provider_label}.",
                        "Disabled in the request payload.",
                    )
                )
                continue
            if adapter.limit <= 0:
                steps_by_adapter.append(
                    self._step(
                        "source_skip",
                        f"Skipped {provider_label}.",
                        "Requested limit is 0.",
                    )
                )
                continue
            unavailable_reason = adapter.unavailable_reason
            if unavailable_reason is not None:
                steps_by_adapter.append(
                    self._step(
                        "source_skip",
                        f"Skipped {provider_label}.",
                        unavailable_reason,
                    )
                )
                continue

            steps_by_adapter.append(None)
            fetch_requests.append((index, adapter, adapter.limit))
            await emit(
                "source_start",
                {
                    "provider": provider_key,
                    "label": provider_label,
                    "agent_name": adapter.agent_name,
                    "agent_icon": adapter.agent_icon,
                    "task_desc": adapter.task_desc,
                },
            )
            tasks.append(fetch_with_timeout(adapter, adapter.limit))

        fetch_results = await asyncio.gather(*tasks, return_exceptions=True)

        for (index, adapter, limit), provider_results in zip(fetch_requests, fetch_results, strict=True):
            provider_label = adapter.label
            if isinstance(provider_results, Exception):
                error_detail = (
                    self._clean_text(str(provider_results))[:240]
                    or provider_results.__class__.__name__
                )
                logger.warning(
                    "%s fetch failed: %s",
                    provider_label,
                    error_detail,
                )
                steps_by_adapter[index] = self._step(
                    "source_error",
                    f"{provider_label} fetch failed.",
                    error_detail,
                )
                await emit(
                    "source_error",
                    {
                        "provider": adapter.key,
                        "label": provider_label,
                        "error": error_detail,
                    },
                )
                continue

            added = 0
            items_preview: list[str] = []
            for source in provider_results:
                dedupe_key = (source.title.lower(), source.url)
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                results.append(source)
                added += 1
                if len(items_preview) < 3:
                    items_preview.append(source.title)

            steps_by_adapter[index] = (
                self._step(
                    "source_complete",
                    f"Collected {added} item(s) from {provider_label}.",
                    f"Requested {limit}; deduped total is now {len(results)}.",
                )
            )
            await emit(
                "source_complete",
                {
                    "provider": adapter.key,
                    "label": provider_label,
                    "count": added,
                    "items_preview": items_preview,
                },
            )

        return SourceFetchBundle(
            sources=results,
            steps=[step for step in steps_by_adapter if step is not None],
        )

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

    def _clean_text(self, value: str) -> str:
        text = html.unescape(value or "")
        text = _HTML_TAG_RE.sub(" ", text)
        return _WHITESPACE_RE.sub(" ", text).strip()

    def _step(self, stage: str, message: str, detail: str | None = None) -> AnalysisStepRead:
        return AnalysisStepRead(stage=stage, message=message, detail=detail)

    def _event(self, event: str, payload: AnalysisStepRead | AnalysisSourceRead | AnalysisResponse | dict[str, Any]) -> AnalysisEvent:
        if isinstance(payload, dict):
            return AnalysisEvent(event=event, payload=payload)
        return AnalysisEvent(event=event, payload=payload.model_dump(mode="json"))
