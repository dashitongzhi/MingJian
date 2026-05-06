"""GitHub repositories and issues data source provider."""

from __future__ import annotations

from typing import Any

import httpx

from planagent.domain.api import AnalysisSourceRead
from planagent.services.sources.base import DataSourceProvider


class GitHubProvider(DataSourceProvider):
    key = "github"
    label = "GitHub"
    default_enabled = True
    default_limit = 3
    agent_name = "代码探员"
    agent_icon = "🐙"
    task_desc = "正在搜索 GitHub 开源项目"

    # ── MCP metadata ─────────────────────────────────────────────────
    mcp_name = "github_search"
    mcp_description = (
        "Search GitHub for repositories, issues, and pull requests. "
        "Returns repository names, URLs, descriptions, languages, star counts, "
        "and issue/PR states. Supports domain-specific query expansion for "
        "military (OSINT/defense) and corporate (AI/startup) contexts."
    )
    mcp_input_schema: dict = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search keywords for GitHub repositories and issues",
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

        search_query = self._github_query(query, domain_id)
        repo_limit = max(1, min(limit, max(1, limit // 2)))
        update_limit = max(0, limit - repo_limit)
        url = "https://api.github.com/search/repositories"
        params = {
            "q": search_query,
            "sort": "updated",
            "order": "desc",
            "per_page": str(min(max(repo_limit, 1), 10)),
        }
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "PlanAgent/0.1",
        }
        async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
            issue_payload: dict[str, Any] = {}
            if update_limit > 0:
                issue_response = await client.get(
                    "https://api.github.com/search/issues",
                    params={
                        "q": f"{search_query} is:issue OR is:pr",
                        "sort": "updated",
                        "order": "desc",
                        "per_page": str(min(update_limit, 10)),
                    },
                    headers=headers,
                )
                issue_response.raise_for_status()
                issue_payload = issue_response.json()

        payload = response.json()
        results: list[AnalysisSourceRead] = []
        for repo in payload.get("items", [])[:repo_limit]:
            full_name = self.clean_text(repo.get("full_name") or "")
            html_url = self.clean_text(repo.get("html_url") or "")
            description = self.clean_text(repo.get("description") or "")
            language = self.clean_text(repo.get("language") or "")
            stars = repo.get("stargazers_count")
            updated_at = self.clean_text(repo.get("updated_at") or "") or None
            summary_parts = []
            if description:
                summary_parts.append(description)
            if language:
                summary_parts.append(f"language={language}")
            if isinstance(stars, int):
                summary_parts.append(f"stars={stars}")
            if not full_name or not html_url:
                continue
            results.append(
                AnalysisSourceRead(
                    source_type="github_repository",
                    title=full_name,
                    url=html_url,
                    summary=" | ".join(summary_parts) or full_name,
                    published_at=updated_at,
                    metadata={
                        "platform": "github",
                        "provider": "github_search",
                        "engagement": {"stars": stars} if isinstance(stars, int) else {},
                        "raw_published_at": updated_at,
                        "query_used": search_query,
                    },
                )
            )
        for issue in issue_payload.get("items", [])[:update_limit]:
            title = self.clean_text(issue.get("title") or "")
            html_url = self.clean_text(issue.get("html_url") or "")
            state = self.clean_text(issue.get("state") or "")
            updated_at = self.clean_text(issue.get("updated_at") or "") or None
            item_type = "github_pull_request" if issue.get("pull_request") else "github_issue"
            if not title or not html_url:
                continue
            results.append(
                AnalysisSourceRead(
                    source_type=item_type,
                    title=title,
                    url=html_url,
                    summary=f"{item_type} | state={state}" if state else item_type,
                    published_at=updated_at,
                    metadata={
                        "platform": "github",
                        "provider": "github_search",
                        "raw_published_at": updated_at,
                        "query_used": search_query,
                    },
                )
            )
        return results

    def _github_query(self, query: str, domain_id: str) -> str:
        base_query = self._platform_query(query, domain_id)
        if domain_id == "corporate":
            return f"{base_query} AI startup OR agents"
        if domain_id == "military":
            return f"{base_query} OSINT OR defense"
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
