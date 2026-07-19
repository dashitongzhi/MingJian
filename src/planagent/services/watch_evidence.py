from __future__ import annotations

import json
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from planagent.domain.api import AnalysisRequest, AnalysisSourceRead
from planagent.domain.models import WatchRule

_MAX_PROVIDER_METADATA_CHARS = 16_384
_RESERVED_SOURCE_METADATA_KEYS = frozenset({"importance_score", "origin", "rule_id"})


class SourceHealthRecorder(Protocol):
    async def record_source_success(self, session: AsyncSession, source_type: str) -> object: ...

    async def record_source_failure(
        self,
        session: AsyncSession,
        source_type: str,
        error: str,
    ) -> object: ...


def build_watch_analysis_request(rule: WatchRule) -> AnalysisRequest:
    return AnalysisRequest(
        content=rule.query,
        domain_id=rule.domain_id,
        auto_fetch_news=True,
        include_google_news="google_news" in rule.source_types,
        include_reddit="reddit" in rule.source_types,
        include_hacker_news="hacker_news" in rule.source_types,
        include_github="github" in rule.source_types,
        include_rss_feeds="rss" in rule.source_types,
        include_gdelt="gdelt" in rule.source_types,
        include_weather="weather" in rule.source_types,
        include_aviation="aviation" in rule.source_types,
        include_x="x" in rule.source_types,
        source_types=rule.source_types,
    )


async def record_watch_source_health(
    session: AsyncSession,
    recorder: SourceHealthRecorder,
    reasoning_steps: list[Any],
) -> None:
    for step in reasoning_steps:
        if step.stage == "source_complete":
            await recorder.record_source_success(session, source_type_from_step(step.message))
        elif step.stage == "source_error":
            await recorder.record_source_failure(
                session,
                source_type_from_step(step.message),
                step.detail or step.message,
            )


def build_watch_ingest_items(
    rule: WatchRule,
    sources: list[AnalysisSourceRead],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = [
        {
            "source_type": "analyst_note",
            "source_url": f"https://local.planagent/watch/{rule.id}",
            "title": rule.name,
            "content_text": rule.query,
            "source_metadata": {"origin": "watch_rule", "rule_id": rule.id},
        }
    ]
    for source in sources:
        provider_metadata = _provider_metadata(source.metadata)
        provider_metadata.update(
            {
                "origin": "watch_rule_source",
                "importance_score": watch_source_score(rule, source),
                "rule_id": rule.id,
            }
        )
        items.append(
            {
                "source_type": source.source_type,
                "source_url": source.url,
                "title": source.title,
                "content_text": source.summary,
                "source_metadata": provider_metadata,
            }
        )
    return items


def qualified_watch_sources(
    rule: WatchRule,
    sources: list[AnalysisSourceRead],
) -> list[AnalysisSourceRead]:
    return [
        source
        for source in sources
        if watch_source_score(rule, source) >= float(rule.importance_threshold or 0.0)
    ]


def watch_threshold_met(rule: WatchRule, sources: list[AnalysisSourceRead]) -> bool:
    if len(sources) < int(rule.min_new_evidence_count or 0):
        return False
    if not sources:
        return float(rule.trigger_threshold or 0.0) <= 0.0
    return max(watch_source_score(rule, source) for source in sources) >= float(
        rule.trigger_threshold or 0.0
    )


def watch_source_score(rule: WatchRule, source: AnalysisSourceRead) -> float:
    haystack = f"{source.title} {source.summary}".lower()
    if any(term.lower() in haystack for term in (rule.exclude_keywords or []) if term):
        return 0.0
    keywords = [term.lower() for term in (rule.keywords or []) if term]
    entity_tags = [term.lower() for term in (rule.entity_tags or []) if term]
    terms = keywords or entity_tags or [token.lower() for token in rule.query.split()[:6] if token]
    matched = sum(1 for term in terms if term and term in haystack)
    score = 0.35 + min(matched * 0.18, 0.45)
    engagement = source.metadata.get("engagement", {}) if isinstance(source.metadata, dict) else {}
    if isinstance(engagement, dict) and any(
        value for value in engagement.values() if isinstance(value, int | float)
    ):
        score += 0.1
    if source.published_at:
        score += 0.1
    return round(max(0.0, min(score, 1.0)), 4)


def source_type_from_step(message: str) -> str:
    lowered = message.lower()
    mappings = (
        ("google", "google_news"),
        ("reddit", "reddit"),
        ("hacker", "hacker_news"),
        ("github", "github"),
        ("gdelt", "gdelt"),
        ("weather", "weather"),
        ("rss", "rss"),
        ("linux.do", "linux_do"),
        ("linux", "linux_do"),
        ("xiaohongshu", "xiaohongshu"),
        ("douyin", "douyin"),
    )
    if "aviation" in lowered or "opensky" in lowered:
        return "aviation"
    for marker, source_type in mappings:
        if marker in lowered:
            return source_type
    if lowered.strip() == "x" or " x." in lowered or " x " in lowered:
        return "x"
    return "unknown"


def watch_recommendation_summary(
    recommendations: list[str],
    summary: str,
    debate_id: str | None,
    simulation_run_id: str | None,
) -> str:
    cleaned = [" ".join(item.split()) for item in recommendations if item]
    base = "；".join(cleaned[:3]) if cleaned else " ".join(str(summary or "").split())
    actions = []
    if simulation_run_id is not None:
        actions.append("已生成新推演")
    if debate_id is not None:
        actions.append("已完成重新辩论")
    suffix = f"（{', '.join(actions)}）" if actions else ""
    return f"{base[:500]}{suffix}" or "监控刷新完成，暂无明确建议变化。"


def _provider_metadata(metadata: object) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        return {}
    cleaned = {
        str(key): value
        for key, value in metadata.items()
        if str(key) not in _RESERVED_SOURCE_METADATA_KEYS
    }
    try:
        encoded = json.dumps(cleaned, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return {"provider_metadata_rejected": True}
    if len(encoded) > _MAX_PROVIDER_METADATA_CHARS:
        return {"provider_metadata_truncated": True}
    return cleaned
