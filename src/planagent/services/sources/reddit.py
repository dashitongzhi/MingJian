"""Reddit data source provider."""

from __future__ import annotations

from urllib.parse import quote_plus

import httpx

from planagent.domain.api import AnalysisSourceRead
from planagent.services.sources.base import DataSourceProvider


class RedditProvider(DataSourceProvider):
    key = "reddit"
    label = "Reddit"
    default_enabled = True
    default_limit = 3
    agent_name = "社区探员"
    agent_icon = "💬"
    task_desc = "正在搜索 Reddit 社区讨论"

    @property
    def fallback_keys(self) -> list[str]:
        return ["hacker_news"]

    # ── MCP metadata ─────────────────────────────────────────────────
    mcp_name = "reddit_search"
    mcp_description = (
        "Search Reddit for community discussions and posts. "
        "Returns titles, URLs, subreddit info, engagement scores (upvotes/comments), "
        "and publication timestamps. Supports domain-specific query expansion."
    )
    mcp_input_schema: dict = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search keywords for Reddit posts",
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

        search_query = self._reddit_query(query, domain_id)
        url = (
            "https://www.reddit.com/search.json"
            f"?q={quote_plus(search_query)}&sort=relevance&t=week&type=link&raw_json=1&limit={limit}"
        )
        async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
            response = await client.get(url, headers={"User-Agent": "PlanAgent/0.1"})
            response.raise_for_status()

        payload = response.json()
        results: list[AnalysisSourceRead] = []
        for child in payload.get("data", {}).get("children", [])[:limit]:
            post = child.get("data", {})
            title = self.clean_text(post.get("title") or "")
            permalink = self.clean_text(post.get("permalink") or "")
            subreddit = self.clean_text(post.get("subreddit_name_prefixed") or "")
            selftext = self.clean_text(post.get("selftext") or "")
            external_url = self.clean_text(post.get("url") or "")
            summary_parts = [part for part in [subreddit, selftext or external_url] if part]
            url_value = f"https://www.reddit.com{permalink}" if permalink else external_url
            if not title or not url_value:
                continue
            results.append(
                AnalysisSourceRead(
                    source_type="reddit_search",
                    title=title,
                    url=url_value,
                    summary=" | ".join(summary_parts) or title,
                    published_at=self.timestamp_to_iso(post.get("created_utc")),
                    metadata={
                        "platform": "reddit",
                        "provider": "reddit_search",
                        "author": self.clean_text(post.get("author") or ""),
                        "engagement": {
                            "score": post.get("score"),
                            "comments": post.get("num_comments"),
                        },
                        "raw_published_at": post.get("created_utc"),
                        "query_used": search_query,
                    },
                )
            )
        return results

    def _reddit_query(self, query: str, domain_id: str) -> str:
        base_query = self._platform_query(query, domain_id)
        if domain_id == "military":
            return f"{base_query} conflict defense military"
        if domain_id == "corporate":
            return f"{base_query} startup company market AI"
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
