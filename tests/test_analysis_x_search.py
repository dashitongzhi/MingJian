from __future__ import annotations

import asyncio

from planagent.config import Settings
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
