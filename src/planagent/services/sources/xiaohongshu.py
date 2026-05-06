"""Xiaohongshu data source provider."""

from __future__ import annotations

from planagent.services.sources.base import DataSourceProvider
from planagent.services.sources._provider_endpoint import ProviderEndpointMixin


class XiaohongshuProvider(ProviderEndpointMixin, DataSourceProvider):
    key = "xiaohongshu"
    label = "Xiaohongshu"
    default_enabled = False
    default_limit = 3
    agent_name = "小红书探员"
    agent_icon = "📕"
    task_desc = "正在搜索小红书内容"

    def is_available(self) -> str | None:
        if not (self.settings.xhs_provider_base_url and self.settings.xhs_provider_api_key):
            return "PLANAGENT_XHS_PROVIDER_BASE_URL and PLANAGENT_XHS_PROVIDER_API_KEY are not configured."
        return None

    async def fetch(self, query: str, limit: int, domain_id: str):
        return await self.fetch_from_endpoint(
            provider="xiaohongshu",
            base_url=self.settings.xhs_provider_base_url,
            api_key=self.settings.xhs_provider_api_key,
            query=query,
            limit=limit,
            domain_id=domain_id,
        )
