"""X (Twitter) data source provider.

Supports two backends: model-backed X search (via OpenAI) and direct X API.
"""

from __future__ import annotations

from typing import Any

import httpx

from planagent.domain.api import AnalysisSourceRead
from planagent.services.openai_client import OpenAIService
from planagent.services.sources.base import DataSourceProvider


class XProvider(DataSourceProvider):
    key = "x"
    label = "X"
    default_enabled = False
    default_limit = 3
    agent_name = "社媒探员"
    agent_icon = "🐦"
    task_desc = "正在搜索 X/Twitter 社交媒体"

    def __init__(self, settings, **deps):
        super().__init__(settings, **deps)
        self.openai_service: OpenAIService | None = deps.get("openai_service")

    def is_available(self) -> str | None:
        if not self.settings.x_enabled:
            return "Neither PLANAGENT_X_BEARER_TOKEN nor PLANAGENT_OPENAI_X_SEARCH_API_KEY is configured."
        return None

    async def fetch(
        self, query: str, limit: int, domain_id: str,
    ) -> list[AnalysisSourceRead]:
        # Try model-backed search first
        if self.openai_service is not None and self.openai_service.is_configured("x_search"):
            model_results = await self.openai_service.search_x_posts(
                self._platform_query(query, domain_id), limit,
            )
            if model_results is not None and model_results.posts:
                results: list[AnalysisSourceRead] = []
                for post in model_results.posts[:limit]:
                    title = self.clean_text(post.title)
                    url = self.clean_text(post.url)
                    summary = self.clean_text(post.summary)
                    if not title or not url or not summary:
                        continue
                    results.append(
                        AnalysisSourceRead(
                            source_type="x_model_search",
                            title=title,
                            url=url,
                            summary=summary,
                            published_at=self.clean_text(post.published_at or "") or None,
                            metadata={
                                "platform": "x",
                                "provider": "model_backed_x_search",
                                "raw_published_at": self.clean_text(post.published_at or "") or None,
                                "query_used": self._platform_query(query, domain_id),
                            },
                        )
                    )
                if results:
                    return results
            if not self.settings.resolved_x_bearer_token:
                last_error = getattr(self.openai_service, "last_error", None)
                if last_error:
                    raise RuntimeError(last_error)
        return await self._fetch_x_posts(query, limit, domain_id)

    async def _fetch_x_posts(
        self, query: str, limit: int, domain_id: str,
    ) -> list[AnalysisSourceRead]:
        if limit <= 0:
            return []

        bearer_token = self.settings.resolved_x_bearer_token
        if not bearer_token:
            return []

        max_results = min(max(limit, 10), 100)
        url = f"{self.settings.x_base_url.rstrip('/')}/tweets/search/recent"
        params = {
            "query": self._x_query(query, domain_id),
            "max_results": str(max_results),
            "tweet.fields": "created_at,author_id",
            "expansions": "author_id",
            "user.fields": "username,name",
        }
        headers = {
            "Authorization": f"Bearer {bearer_token}",
            "User-Agent": "PlanAgent/0.1",
        }
        async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()

        payload = response.json()
        includes = payload.get("includes", {})
        users = {
            item.get("id"): item
            for item in includes.get("users", [])
            if isinstance(item, dict) and item.get("id")
        }
        results: list[AnalysisSourceRead] = []
        for post in payload.get("data", [])[:limit]:
            post_id = self.clean_text(post.get("id") or "")
            text = self.clean_text(post.get("text") or "")
            author = users.get(post.get("author_id"), {})
            username = self.clean_text(author.get("username") or "")
            title = f"X post by @{username}" if username else "X post"
            url_value = (
                f"https://x.com/{username}/status/{post_id}"
                if username and post_id
                else f"https://x.com/i/web/status/{post_id}"
            )
            if not post_id or not text:
                continue
            results.append(
                AnalysisSourceRead(
                    source_type="x_recent_search",
                    title=title,
                    url=url_value,
                    summary=text,
                    published_at=self.clean_text(post.get("created_at") or "") or None,
                    metadata={
                        "platform": "x",
                        "provider": "x_recent_search",
                        "author": username,
                        "raw_published_at": self.clean_text(post.get("created_at") or "") or None,
                        "query_used": self._x_query(query, domain_id),
                    },
                )
            )
        return results

    def _x_query(self, query: str, domain_id: str) -> str:
        return f"({self._platform_query(query, domain_id)}) -is:retweet"

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
