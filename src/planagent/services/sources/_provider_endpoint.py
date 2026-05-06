"""Shared mixin for providers that call external search endpoints (Xiaohongshu, Douyin)."""

from __future__ import annotations

from typing import Any

import httpx

from planagent.domain.api import AnalysisSourceRead
from planagent.services.sources.base import DataSourceProvider


class ProviderEndpointMixin:
    """Mixin that fetches from a generic provider search endpoint.

    Used by Xiaohongshu and Douyin providers which share the same API pattern.
    """

    async def fetch_from_endpoint(
        self: DataSourceProvider,
        provider: str,
        base_url: str | None,
        api_key: str | None,
        query: str,
        limit: int,
        domain_id: str,
    ) -> list[AnalysisSourceRead]:
        if limit <= 0:
            return []
        if not base_url or not api_key:
            return []
        search_query = self._pe_platform_query(query, domain_id)
        async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
            response = await client.get(
                f"{base_url.rstrip('/')}/search",
                params={"q": search_query, "limit": str(limit), "domain_id": domain_id},
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "User-Agent": "PlanAgent/0.1",
                },
            )
            response.raise_for_status()
        payload = response.json()
        candidates = (
            payload.get("items")
            or payload.get("results")
            or payload.get("posts")
            or payload.get("data")
            or []
        )
        if isinstance(candidates, dict):
            candidates = candidates.get("items") or candidates.get("list") or []
        results: list[AnalysisSourceRead] = []
        for item in candidates[:limit]:
            if not isinstance(item, dict):
                continue
            title = self.clean_text(item.get("title") or item.get("caption") or item.get("text") or "")
            url_value = self.clean_text(item.get("url") or item.get("link") or item.get("share_url") or "")
            summary = self.clean_text(
                item.get("summary") or item.get("description") or item.get("content") or item.get("text") or title
            )
            published_at = self.clean_text(item.get("published_at") or item.get("created_at") or "") or None
            if not title or not url_value:
                continue
            results.append(
                AnalysisSourceRead(
                    source_type=provider,
                    title=title,
                    url=url_value,
                    summary=summary or title,
                    published_at=published_at,
                    metadata={
                        "platform": provider,
                        "provider": base_url,
                        "author": self.clean_text(item.get("author") or item.get("username") or ""),
                        "engagement": item.get("engagement") or item.get("metrics") or {},
                        "raw_published_at": published_at,
                        "query_used": search_query,
                    },
                )
            )
        return results

    def _pe_platform_query(self: DataSourceProvider, query: str, domain_id: str) -> str:
        if not self.contains_cjk(query):
            return query
        tokens = self.ascii_keywords(query)
        tokens.extend(self._pe_domain_keywords(domain_id))
        normalized_tokens = list(dict.fromkeys(token for token in tokens if token))
        return " ".join(normalized_tokens) or query

    @staticmethod
    def _pe_domain_keywords(domain_id: str) -> list[str]:
        if domain_id == "military":
            return ["defense", "military", "drone", "conflict"]
        if domain_id == "corporate":
            return ["AI", "startup", "company", "market"]
        return ["AI", "technology", "news"]
