"""Source provider registry — auto-discovers providers and builds adapters.

Enhanced with:
- Fallback/degradation logic (primary source fails → try fallbacks)
- Custom source provider support (user-defined sources)
- MCP-style provider listing and configuration
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import pkgutil
from typing import Any

from planagent.config import Settings
from planagent.domain.api import AnalysisRequest, AnalysisSourceRead, AnalysisStepRead
from planagent.services.openai_client import OpenAIService
from planagent.services.sources.base import DataSourceProvider

logger = logging.getLogger(__name__)

# Ordered list of provider module paths.
# The order determines default fetch priority.
_PROVIDER_MODULES: list[str] = [
    "planagent.services.sources.google_news",
    "planagent.services.sources.reddit",
    "planagent.services.sources.hacker_news",
    "planagent.services.sources.github",
    "planagent.services.sources.rss",
    "planagent.services.sources.gdelt",
    "planagent.services.sources.weather",
    "planagent.services.sources.aviation",
    "planagent.services.sources.x_provider",
    "planagent.services.sources.linux_do",
    "planagent.services.sources.xiaohongshu",
    "planagent.services.sources.douyin",
]


class SourceRegistry:
    """Manages all registered DataSourceProvider instances.

    Features:
    - Auto-discovers providers from module list
    - Supports dynamic registration (custom sources)
    - Implements fallback/degradation: if a provider fails, tries fallback keys
    - MCP-style listing of all available providers

    Usage::

        registry = SourceRegistry(settings, openai_service=openai_svc)
        adapters = registry.build_adapters(payload, query, domain_id)

        # Or with fallback
        results = await registry.fetch_with_fallback("hacker_news", query, 5, domain_id)
    """

    def __init__(
        self,
        settings: Settings,
        openai_service: OpenAIService | None = None,
    ) -> None:
        self.settings = settings
        self.openai_service = openai_service
        self._providers: dict[str, DataSourceProvider] = {}
        self._load_providers()
        self._load_custom_providers()

    # ── public API ─────────────────────────────────────────────────────

    def get(self, key: str) -> DataSourceProvider | None:
        """Look up a provider by key."""
        return self._providers.get(key)

    def all_providers(self) -> list[DataSourceProvider]:
        """Return all registered providers in priority order."""
        return list(self._providers.values())

    def list_provider_keys(self) -> list[str]:
        """Return all registered provider keys."""
        return list(self._providers.keys())

    def register(self, provider: DataSourceProvider) -> None:
        """Dynamically register a provider at runtime.

        Used for custom user-defined sources.
        """
        self._providers[provider.key] = provider
        logger.info("Dynamically registered source provider: %s", provider.key)

    def unregister(self, key: str) -> bool:
        """Remove a dynamically registered provider.

        Returns True if the provider was found and removed.
        """
        if key in self._providers:
            del self._providers[key]
            logger.info("Unregistered source provider: %s", key)
            return True
        return False

    def describe_all(self) -> list[dict[str, Any]]:
        """MCP-style tool descriptions for all registered providers."""
        return [p.describe() for p in self._providers.values()]

    def config_all(self) -> list[dict[str, Any]]:
        """Return configuration info for all registered providers."""
        return [p.get_config() for p in self._providers.values()]

    async def fetch_with_fallback(
        self,
        provider_key: str,
        query: str,
        limit: int,
        domain_id: str,
    ) -> tuple[list[AnalysisSourceRead], list[str]]:
        """Fetch from a provider, falling back to alternatives on failure.

        Returns (results, attempted_keys).
        If the primary and all fallbacks fail, returns ([], attempted_keys)
        and the last exception is logged but not raised.
        """
        provider = self.get(provider_key)
        if provider is None:
            logger.warning("Provider %s not found, no fallback possible", provider_key)
            return [], [provider_key]

        attempted: list[str] = []
        candidates = [provider_key] + provider.fallback_keys

        for key in candidates:
            p = self.get(key)
            if p is None:
                continue
            if p.is_available() is not None:
                logger.debug("Skipping unavailable provider %s: %s", key, p.is_available())
                attempted.append(key)
                continue
            try:
                results = await p.fetch(query, limit, domain_id)
                attempted.append(key)
                if results:
                    return results, attempted
                # Empty results are not an error, but try next
                logger.debug("Provider %s returned empty results, trying next", key)
            except Exception as exc:
                attempted.append(key)
                logger.warning(
                    "Provider %s failed (%s), trying fallback",
                    key,
                    f"{type(exc).__name__}: {str(exc)[:120]}",
                )
                continue

        return [], attempted

    def build_adapters(
        self,
        payload: AnalysisRequest,
        query: str,
        domain_id: str,
    ) -> list[_SourceAdapter]:
        """Build SourceAdapter wrappers for all providers."""
        adapters: list[_SourceAdapter] = []
        for provider in self._providers.values():
            adapters.append(
                _SourceAdapter(
                    provider=provider,
                    payload=payload,
                    query=query,
                    domain_id=domain_id,
                )
            )
        return adapters

    # ── internal ───────────────────────────────────────────────────────

    def _load_providers(self) -> None:
        """Import all provider modules and instantiate each concrete subclass."""
        for module_path in _PROVIDER_MODULES:
            try:
                mod = importlib.import_module(module_path)
            except Exception as exc:
                logger.warning("Failed to import provider module %s: %s", module_path, exc)
                continue
            for attr_name in dir(mod):
                attr = getattr(mod, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, DataSourceProvider)
                    and attr is not DataSourceProvider
                    and not getattr(attr, "__abstractmethods__", None)
                ):
                    try:
                        instance = attr(
                            self.settings,
                            openai_service=self.openai_service,
                        )
                        self._providers[instance.key] = instance
                        logger.debug("Registered source provider: %s", instance.key)
                    except Exception as exc:
                        logger.warning("Failed to instantiate provider %s: %s", attr_name, exc)

    def _load_custom_providers(self) -> None:
        """Load user-defined custom source providers from config files."""
        try:
            from planagent.services.sources.custom_provider import create_custom_providers

            for provider in create_custom_providers(self.settings, openai_service=self.openai_service):
                self._providers[provider.key] = provider
                logger.debug("Registered custom source provider: %s", provider.key)
        except ImportError:
            logger.debug("Custom provider support not available (missing dependencies)")
        except Exception as exc:
            logger.warning("Failed to load custom providers: %s", exc)


class _SourceAdapter:
    """Wraps a DataSourceProvider for use by AutomatedAnalysisService.

    This is the bridge between the new provider system and the existing
    _fetch_related_sources loop that expects (key, label, fetcher) tuples.
    """

    __slots__ = ("provider", "payload", "query", "domain_id")

    def __init__(
        self,
        provider: DataSourceProvider,
        payload: AnalysisRequest,
        query: str,
        domain_id: str,
    ) -> None:
        self.provider = provider
        self.payload = payload
        self.query = query
        self.domain_id = domain_id

    # ── properties expected by the analysis service ────────────────────

    @property
    def key(self) -> str:
        return self.provider.key

    @property
    def label(self) -> str:
        return self.provider.label

    @property
    def agent_name(self) -> str:
        return self.provider.agent_name

    @property
    def agent_icon(self) -> str:
        return self.provider.agent_icon

    @property
    def task_desc(self) -> str:
        return self.provider.task_desc

    @property
    def enabled(self) -> bool:
        return self.provider.request_enabled(self.payload)

    @property
    def limit(self) -> int:
        return self.provider.request_limit(self.payload)

    @property
    def unavailable_reason(self) -> str | None:
        return self.provider.is_available()

    async def fetch(self, limit: int | None = None) -> list[AnalysisSourceRead]:
        """Delegate to the provider's fetch method."""
        effective_limit = limit if limit is not None else self.limit
        return await self.provider.fetch(self.query, effective_limit, self.domain_id)
