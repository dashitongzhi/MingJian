"""Google News RSS data source provider."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from urllib.parse import quote_plus

import httpx

from planagent.domain.api import AnalysisSourceRead
from planagent.services.sources.base import DataSourceProvider


class GoogleNewsProvider(DataSourceProvider):
    key = "google_news"
    label = "Google News"
    default_enabled = True
    default_limit = 5
    agent_name = "新闻探员"
    agent_icon = "📰"
    task_desc = "正在搜索 Google News 获取最新新闻报道"

    @property
    def fallback_keys(self) -> list[str]:
        return ["rss", "hacker_news"]

    # ── MCP metadata ─────────────────────────────────────────────────
    mcp_name = "google_news_search"
    mcp_description = (
        "Search Google News RSS for the latest news articles on any topic. "
        "Returns titles, URLs, summaries, and publication dates. "
        "Automatically detects CJK queries and adjusts locale (zh-CN vs en-US)."
    )
    mcp_input_schema: dict = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search keywords for news articles",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of results to return",
                "default": 5,
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
        locale = self._locale(query)
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
            title = self.clean_text(item.findtext("title", default=""))
            link = self.clean_text(item.findtext("link", default=""))
            description = self.clean_text(item.findtext("description", default=""))
            pub_date = self.clean_text(item.findtext("pubDate", default="")) or None
            if not title or not link:
                continue
            results.append(
                AnalysisSourceRead(
                    source_type="google_news_rss",
                    title=title,
                    url=link,
                    summary=description or title,
                    published_at=pub_date,
                    metadata={
                        "platform": "google_news",
                        "provider": "google_news_rss",
                        "raw_published_at": pub_date,
                        "query_used": query,
                    },
                )
            )
        return results

    def _locale(self, query: str) -> dict[str, str]:
        if self.contains_cjk(query):
            return {"hl": "zh-CN", "gl": "CN", "ceid": "CN:zh-Hans"}
        return {"hl": "en-US", "gl": "US", "ceid": "US:en"}
