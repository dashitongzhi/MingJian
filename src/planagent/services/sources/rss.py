"""Configured RSS feeds data source provider."""

from __future__ import annotations

import xml.etree.ElementTree as ET

import httpx

from planagent.domain.api import AnalysisSourceRead
from planagent.services.sources.base import DataSourceProvider


class RSSProvider(DataSourceProvider):
    key = "rss"
    label = "Configured RSS Feeds"
    default_enabled = True
    default_limit = 3
    agent_name = "订阅探员"
    agent_icon = "📡"
    task_desc = "正在扫描 RSS 订阅源"

    # ── MCP metadata ─────────────────────────────────────────────────
    mcp_name = "rss_feed_search"
    mcp_description = (
        "Search configured RSS feeds for relevant articles. "
        "Supports both RSS 2.0 and Atom feed formats. Returns titles, URLs, "
        "summaries, and publication dates. Performs keyword matching against "
        "titles and summaries to filter results."
    )
    mcp_input_schema: dict = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Keywords to match against RSS feed entries",
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
                "description": "Domain context to select relevant feed sets",
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
        feed_urls = self._feed_urls(domain_id)
        if limit <= 0 or not feed_urls:
            return []

        results: list[AnalysisSourceRead] = []
        query_tokens = set(self.ascii_keywords(query.lower()))
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
                    title = self.clean_text(
                        item.findtext("title", default="")
                        or item.findtext("{http://www.w3.org/2005/Atom}title", default="")
                    )
                    link = self._rss_link(item)
                    summary = self.clean_text(
                        item.findtext("description", default="")
                        or item.findtext("summary", default="")
                        or item.findtext("{http://www.w3.org/2005/Atom}summary", default="")
                    )
                    published_at = self.clean_text(
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
                            metadata={
                                "platform": "rss",
                                "provider": feed_url,
                                "raw_published_at": published_at,
                                "query_used": query,
                            },
                        )
                    )
        return results

    def _feed_urls(self, domain_id: str) -> list[str]:
        configured = [
            item.strip()
            for item in self.settings.additional_rss_feeds.split(",")
            if item.strip()
        ]
        defaults: dict[str, list[str]] = {
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

    @staticmethod
    def _rss_link(item: ET.Element) -> str:
        import xml.etree.ElementTree as _ET

        link = DataSourceProvider.clean_text(item.findtext("link", default=""))
        if link:
            return link
        atom_link = item.find("{http://www.w3.org/2005/Atom}link")
        if atom_link is not None:
            return DataSourceProvider.clean_text(atom_link.attrib.get("href", ""))
        return ""
