"""Linux.do community data source provider."""

from __future__ import annotations

import httpx

from planagent.domain.api import AnalysisSourceRead
from planagent.services.sources.base import DataSourceProvider


class LinuxDoProvider(DataSourceProvider):
    key = "linux_do"
    label = "Linux.do"
    default_enabled = False
    default_limit = 3
    agent_name = "论坛探员"
    agent_icon = "🐧"
    task_desc = "正在搜索 Linux.do 社区"

    async def fetch(
        self, query: str, limit: int, domain_id: str,
    ) -> list[AnalysisSourceRead]:
        if limit <= 0:
            return []
        search_query = self._platform_query(query, domain_id)
        base_url = self.settings.linux_do_base_url.rstrip("/")
        async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
            response = await client.get(
                f"{base_url}/search.json",
                params={"q": search_query},
                headers={"User-Agent": "PlanAgent/0.1"},
            )
            response.raise_for_status()
        payload = response.json()
        topics = payload.get("topics") or []
        posts = payload.get("posts") or []
        posts_by_topic = {
            post.get("topic_id"): post
            for post in posts
            if isinstance(post, dict) and post.get("topic_id")
        }
        results: list[AnalysisSourceRead] = []
        for topic in topics[:limit]:
            if not isinstance(topic, dict):
                continue
            title = self.clean_text(topic.get("title") or "")
            topic_id = topic.get("id")
            slug = self.clean_text(topic.get("slug") or "")
            post = posts_by_topic.get(topic_id, {})
            excerpt = self.clean_text(post.get("blurb") or post.get("cooked") or "")
            url_value = f"{base_url}/t/{slug}/{topic_id}" if slug and topic_id else base_url
            if not title or not topic_id:
                continue
            published_at = self.clean_text(
                topic.get("created_at") or post.get("created_at") or topic.get("last_posted_at") or ""
            ) or None
            results.append(
                AnalysisSourceRead(
                    source_type="linux_do_discourse",
                    title=title,
                    url=url_value,
                    summary=excerpt or title,
                    published_at=published_at,
                    metadata={
                        "platform": "linux_do",
                        "provider": "discourse_search",
                        "author": self.clean_text(post.get("username") or ""),
                        "engagement": {
                            "posts_count": topic.get("posts_count"),
                            "views": topic.get("views"),
                            "like_count": topic.get("like_count"),
                        },
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
