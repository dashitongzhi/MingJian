"""Pluggable data source providers for MingJian analysis.

This package implements an MCP-like pluggable architecture for data sources.
Each source (Google News, Reddit, Hacker News, etc.) is implemented as a
DataSourceProvider subclass with a standardized interface.

Usage:
    from planagent.services.sources import SourceRegistry

    registry = SourceRegistry(settings, openai_service)
    adapters = registry.build_adapters(payload, query, domain_id)

    # Fallback fetching
    results, attempted = await registry.fetch_with_fallback("hacker_news", query, 5, domain_id)
"""

from planagent.services.sources.base import DataSourceProvider
from planagent.services.sources.custom_provider import (
    CustomSourceProvider,
    create_custom_providers,
    load_custom_source_configs,
    save_custom_source_configs,
)
from planagent.services.sources.registry import SourceRegistry

__all__ = [
    "DataSourceProvider",
    "SourceRegistry",
    "CustomSourceProvider",
    "create_custom_providers",
    "load_custom_source_configs",
    "save_custom_source_configs",
]
