"""Hacker News (Algolia) data source provider."""

from __future__ import annotations

from urllib.parse import quote_plus

import httpx

from planagent.domain.api import AnalysisSourceRead
from planagent.services.sources.base import DataSourceProvider


class HackerNewsProvider(DataSourceProvider):
    key = "hacker_news"
    label = "Hacker News"
    default_enabled = True
    default_limit = 3
    agent_name = "技术探员"
    agent_icon = "🔧"
    task_desc = "正在搜索 Hacker News 技术动态"

    @property
    def fallback_keys(self) -> list[str]:
        return ["reddit", "google_news"]

    # ── MCP metadata ─────────────────────────────────────────────────
    mcp_name = "hacker_news_search"
    mcp_description = (
        "Search Hacker News (via Algolia API) for technology news and discussions. "
        "Returns story titles, URLs, highlighted summaries, and creation timestamps. "
        "Supports domain-specific keyword expansion for military/corporate contexts."
    )
    mcp_input_schema: dict = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search keywords for Hacker News stories",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of results to return",
                "default": 3,
                "minimum": 1,
                "maximum": 25,
            },
            "domain_id": {
                "type": "string",
                "description": "Domain context (e.g. 'general', 'military', 'corporate')",
                "default": "general",
                "enum": ["general", "military", "corporate"],
            },
        },
        "required": ["query"],
    }

    def to_mcp_tool(self) -> dict:
        """Return a standardized MCP tool description."""
        return {
            "name": self.mcp_name,
            "description": self.mcp_description,
            "inputSchema": self.mcp_input_schema,
        }

    async def mcp_execute(self, params: dict) -> list[dict]:
        """Execute via standardized MCP parameter dictionary."""
        query = params["query"]
        limit = params.get("limit", self.default_limit)
        domain_id = params.get("domain_id", "general")
        results = await self.fetch(query, limit, domain_id)
        return [r.model_dump() for r in results]

    async def fetch(
        self, query: str, limit: int, domain_id: str,
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
            title = self.clean_text(hit.get("title") or "")
            url_value = self.clean_text(hit.get("url") or hit.get("story_url") or "")
            summary = self.clean_text(
                hit.get("_highlightResult", {}).get("title", {}).get("value", "")
            ) or title
            published_at = self.clean_text(hit.get("created_at") or "") or None
            if not title or not url_value:
                continue
            results.append(
                AnalysisSourceRead(
                    source_type="hacker_news",
                    title=title,
                    url=url_value,
                    summary=summary,
                    published_at=published_at,
                    metadata={
                        "platform": "hacker_news",
                        "provider": "hn_algolia",
                        "raw_published_at": published_at,
                        "query_used": search_query,
                    },
                )
            )
        return results

    def _platform_query(self, query: str, domain_id: str) -> str:
        if not self.contains_cjk(query):
            return query
        tokens = self.ascii_keywords(query)
        tokens.extend(self._domain_keywords(domain_id))
        normalized_tokens = list(dict.fromkeys(token for token in tokens if token))
        return " ".join(normalized_tokens) or query

    @staticmethod
    def _domain_keywords(domain_id: str) -> list[str]:
        if domain_id == "military":
            return ["defense", "military", "drone", "conflict"]
        if domain_id == "corporate":
            return ["AI", "startup", "company", "market"]
        return ["AI", "technology", "news"]
