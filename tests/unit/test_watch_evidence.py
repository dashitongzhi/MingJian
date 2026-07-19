from __future__ import annotations

from planagent.domain.api import AnalysisSourceRead
from planagent.domain.models import WatchRule
from planagent.services.watch_evidence import (
    build_watch_analysis_request,
    build_watch_ingest_items,
    qualified_watch_sources,
    watch_threshold_met,
)


def _rule() -> WatchRule:
    return WatchRule(
        id="watch-1",
        name="AI demand",
        domain_id="corporate",
        query="AI demand",
        source_types=["google_news", "rss"],
        keywords=["demand"],
        exclude_keywords=["rumor"],
        trigger_threshold=0.5,
        importance_threshold=0.5,
        min_new_evidence_count=1,
    )


def test_watch_analysis_request_uses_rule_source_configuration() -> None:
    request = build_watch_analysis_request(_rule())

    assert request.include_google_news is True
    assert request.include_rss_feeds is True
    assert request.include_reddit is False
    assert request.source_types == ["google_news", "rss"]


def test_watch_ingest_metadata_cannot_override_system_provenance() -> None:
    rule = _rule()
    source = AnalysisSourceRead(
        source_type="rss",
        title="AI demand rises",
        url="https://example.com/report",
        summary="Demand increased in the latest quarter.",
        metadata={
            "origin": "forged-provider",
            "importance_score": 0.0,
            "rule_id": "other-rule",
            "provider": "example",
        },
    )

    item = build_watch_ingest_items(rule, [source])[1]

    assert item["source_metadata"]["origin"] == "watch_rule_source"
    assert item["source_metadata"]["importance_score"] >= 0.5
    assert item["source_metadata"]["rule_id"] == rule.id
    assert item["source_metadata"]["provider"] == "example"


def test_watch_qualification_and_threshold_share_scoring_policy() -> None:
    rule = _rule()
    qualified = AnalysisSourceRead(
        source_type="rss",
        title="Demand update",
        url="https://example.com/qualified",
        summary="AI demand remains strong.",
        metadata={},
    )
    excluded = AnalysisSourceRead(
        source_type="rss",
        title="Market rumor",
        url="https://example.com/excluded",
        summary="A rumor about AI demand.",
        metadata={},
    )

    sources = qualified_watch_sources(rule, [qualified, excluded])

    assert sources == [qualified]
    assert watch_threshold_met(rule, sources) is True
