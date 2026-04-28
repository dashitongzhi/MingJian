from __future__ import annotations

import asyncio

from planagent.config import Settings
from planagent.domain.api import AnalysisRequest, AnalysisSourceRead
from planagent.services.analysis import AutomatedAnalysisService
from planagent.services.openai_client import XSearchPostPayload, XSearchResultPayload


class StubOpenAIService:
    last_error: str | None = None

    def is_configured(self, target: str) -> bool:
        return target == "x_search"

    async def search_x_posts(self, query: str, limit: int) -> XSearchResultPayload:
        return XSearchResultPayload(
            posts=[
                XSearchPostPayload(
                    title=f"X result for {query}",
                    url="https://x.com/example/status/1",
                    summary="Example summary from model-backed X search.",
                    published_at="2026-03-20T10:00:00Z",
                )
            ][:limit]
        )


def test_analysis_uses_model_backed_x_search_when_available() -> None:
    service = AutomatedAnalysisService(
        Settings(_env_file=None, x_bearer_token=None),
        StubOpenAIService(),
    )
    results = asyncio.run(service._fetch_x_sources("OpenAI Grok", 3, "corporate"))
    assert len(results) == 1
    assert results[0].source_type == "x_model_search"
    assert results[0].url == "https://x.com/example/status/1"


class FailingStubOpenAIService:
    last_error = "x_search_failed: PermissionDeniedError('Your request was blocked.')"

    def is_configured(self, target: str) -> bool:
        return target == "x_search"

    async def search_x_posts(self, query: str, limit: int) -> XSearchResultPayload | None:
        return None


def test_analysis_surfaces_x_model_error_when_no_direct_x_fallback() -> None:
    service = AutomatedAnalysisService(
        Settings(_env_file=None, x_bearer_token=None),
        FailingStubOpenAIService(),
    )

    try:
        asyncio.run(service._fetch_x_sources("OpenAI Grok", 3, "corporate"))
    except RuntimeError as exc:
        assert "request was blocked" in str(exc)
    else:
        raise AssertionError("Expected the x_search failure to be surfaced.")


def test_source_types_request_unconfigured_provider_without_failure() -> None:
    service = AutomatedAnalysisService(Settings(_env_file=None))
    payload = AnalysisRequest(
        content="enterprise AI agent adoption",
        domain_id="corporate",
        source_types=["xiaohongshu"],
        max_source_items={"xiaohongshu": 2},
    )

    bundle = asyncio.run(service._fetch_related_sources(payload, "enterprise AI agent adoption", "corporate"))

    assert bundle.sources == []
    assert any(step.stage == "source_skip" and "Xiaohongshu" in step.message for step in bundle.steps)


def test_source_types_override_legacy_include_flags() -> None:
    service = AutomatedAnalysisService(Settings(_env_file=None))

    async def fake_linux_do(query: str, limit: int, domain_id: str):
        return [
            AnalysisSourceRead(
                source_type="linux_do_discourse",
                title=f"Linux.do result for {query}",
                url="https://linux.do/t/example/1",
                summary="Developers are discussing agent deployment reliability.",
                metadata={"platform": "linux_do", "provider": "test"},
            )
        ][:limit]

    service._fetch_linux_do = fake_linux_do  # type: ignore[method-assign]
    payload = AnalysisRequest(
        content="agent deployment reliability",
        domain_id="corporate",
        include_google_news=True,
        source_types=["linux_do"],
        max_source_items={"linux_do": 1},
    )

    bundle = asyncio.run(service._fetch_related_sources(payload, "agent deployment reliability", "corporate"))

    assert len(bundle.sources) == 1
    assert bundle.sources[0].source_type == "linux_do_discourse"
    assert all("Google News" not in step.message for step in bundle.steps if step.stage == "source_complete")
