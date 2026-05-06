"""GDELT global events database data source provider."""

from __future__ import annotations

import httpx

from planagent.domain.api import AnalysisSourceRead
from planagent.services.sources.base import DataSourceProvider


class GDELTProvider(DataSourceProvider):
    key = "gdelt"
    label = "GDELT"
    default_enabled = True
    default_limit = 3
    agent_name = "全球探员"
    agent_icon = "🌍"
    task_desc = "正在搜索 GDELT 全球事件数据库"

    # ── MCP metadata ─────────────────────────────────────────────────
    mcp_name = "gdelt_search"
    mcp_description = (
        "Search the GDELT Global Event Database for worldwide news and events. "
        "Returns article titles, URLs, source domains, countries, and timestamps. "
        "Supports domain-specific query expansion for military and corporate contexts."
    )
    mcp_input_schema: dict = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search keywords for GDELT events",
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
            title = self.clean_text(article.get("title") or "")
            url_value = self.clean_text(article.get("url") or "")
            source_country = self.clean_text(article.get("sourceCountry") or "")
            domain = self.clean_text(article.get("domain") or "")
            seendate = self.clean_text(article.get("seendate") or "") or None
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
                    metadata={
                        "platform": "gdelt",
                        "provider": domain,
                        "raw_published_at": seendate,
                        "query_used": gdelt_query,
                    },
                )
            )
        return results

    def _gdelt_query(self, query: str, domain_id: str) -> str:
        base_query = self._platform_query(query, domain_id)
        if domain_id == "military":
            return f"({base_query}) (military OR defense OR maritime OR aviation OR weather OR OSINT)"
        if domain_id == "corporate":
            return f"({base_query}) (company OR startup OR market OR product OR funding)"
        return base_query

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
