"""Base class for pluggable data source providers.

Each data source (Google News, Reddit, Hacker News, etc.) implements a
DataSourceProvider subclass. The provider interface mirrors MCP server
concepts: a named tool with a standardized fetch protocol.

MCP-ified interface:
  - ``fetch`` — primary data retrieval
  - ``search`` — search with structured filters
  - ``list_sources`` — enumerate available sub-sources
  - ``get_config`` — return provider config schema
  - ``describe`` — MCP-style tool description
"""

from __future__ import annotations

import html
import re
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from planagent.config import Settings
from planagent.domain.api import AnalysisRequest, AnalysisSourceRead

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


class SourceProviderConfig(ABC):
    """Describes the configuration schema for a source provider."""

    @property
    @abstractmethod
    def schema(self) -> dict[str, Any]:
        """JSON Schema describing provider config fields."""
        ...

    @property
    def defaults(self) -> dict[str, Any]:
        """Default configuration values."""
        return {}


class DataSourceProvider(ABC):
    """Abstract base for all pluggable data source providers.

    Subclasses must define the class-level metadata properties and implement
    ``fetch``.  The base class provides common text-cleaning helpers.

    MCP-ified methods (``search``, ``list_sources``, ``get_config``, ``describe``)
    have default implementations that delegate to ``fetch``; override for richer
    behavior.
    """

    # ── metadata (override in subclasses) ──────────────────────────────

    @property
    @abstractmethod
    def key(self) -> str:
        """Canonical short key, e.g. ``"google_news"``, ``"reddit"``."""
        ...

    @property
    @abstractmethod
    def label(self) -> str:
        """Human-readable display name, e.g. ``"Google News"``."""
        ...

    @property
    def default_enabled(self) -> bool:
        """Whether this source is enabled by default in requests."""
        return True

    @property
    def default_limit(self) -> int:
        """Default number of items to fetch when not overridden."""
        return 3

    @property
    def agent_name(self) -> str:
        """Display name for the fetching agent (shown in UI)."""
        return ""

    @property
    def agent_icon(self) -> str:
        """Emoji icon for the fetching agent."""
        return ""

    @property
    def task_desc(self) -> str:
        """Description of what the agent is doing (Chinese OK)."""
        return ""

    @property
    def fallback_keys(self) -> list[str]:
        """Ordered list of fallback provider keys if this one fails.

        Override to declare alternative sources. The registry uses this
        to implement automatic degradation.
        """
        return []

    # ── lifecycle ──────────────────────────────────────────────────────

    def __init__(self, settings: Settings, **deps: Any) -> None:
        self.settings = settings
        self.deps = deps

    def is_available(self) -> str | None:
        """Return ``None`` if the source can be used, or a reason string if not."""
        return None

    @abstractmethod
    async def fetch(
        self,
        query: str,
        limit: int,
        domain_id: str,
    ) -> list[AnalysisSourceRead]:
        """Fetch up to *limit* source items matching *query*.

        Returns a (possibly empty) list of ``AnalysisSourceRead`` objects.
        Must raise on transient errors so the caller can record them.
        """
        ...

    # ── MCP-ified interface ────────────────────────────────────────────

    async def search(
        self,
        query: str,
        limit: int = 10,
        domain_id: str = "general",
        filters: dict[str, Any] | None = None,
    ) -> list[AnalysisSourceRead]:
        """Search with optional structured filters.

        Default implementation delegates to ``fetch``.  Override for
        providers that support richer query semantics (date ranges,
        language filters, etc.).
        """
        return await self.fetch(query, limit, domain_id)

    async def list_sources(self) -> list[dict[str, Any]]:
        """Enumerate available sub-sources or categories.

        Returns a list of dicts with at least ``key`` and ``label``.
        Default returns the provider itself as a single source.
        """
        return [{"key": self.key, "label": self.label}]

    def get_config(self) -> dict[str, Any]:
        """Return provider configuration schema and current values.

        Useful for UI rendering of source configuration forms.
        """
        return {
            "key": self.key,
            "label": self.label,
            "default_enabled": self.default_enabled,
            "default_limit": self.default_limit,
            "available": self.is_available() is None,
            "unavailable_reason": self.is_available(),
        }

    def describe(self) -> dict[str, Any]:
        """MCP-style tool description for agent consumption."""
        return {
            "name": self.key,
            "description": self.label,
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "limit": {"type": "integer", "description": "Max results", "default": self.default_limit},
                    "domain_id": {"type": "string", "description": "Domain context", "default": "general"},
                },
                "required": ["query"],
            },
        }

    # ── request-level overrides ────────────────────────────────────────

    def request_enabled(self, payload: AnalysisRequest) -> bool:
        """Check the payload for source_types or include_* flags."""
        requested = {_canonical_source_type(item) for item in payload.source_types}
        if requested:
            return self.key in requested
        return self.default_enabled

    def request_limit(self, payload: AnalysisRequest) -> int:
        """Resolve the effective item limit from the payload."""
        limits = {
            _canonical_source_type(key): int(value)
            for key, value in payload.max_source_items.items()
            if isinstance(value, int) or str(value).isdigit()
        }
        if self.key in limits:
            return max(0, min(limits[self.key], 25))
        return self.default_limit

    # ── shared helpers ─────────────────────────────────────────────────

    @staticmethod
    def clean_text(value: str) -> str:
        """Strip HTML tags, collapse whitespace."""
        text = html.unescape(value or "")
        text = _HTML_TAG_RE.sub(" ", text)
        return _WHITESPACE_RE.sub(" ", text).strip()

    @staticmethod
    def timestamp_to_iso(value: Any) -> str | None:
        if value in (None, ""):
            return None
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
        except (TypeError, ValueError, OSError):
            return None

    @staticmethod
    def contains_cjk(value: str) -> bool:
        return any("\u4e00" <= char <= "\u9fff" for char in value)

    @staticmethod
    def ascii_keywords(value: str) -> list[str]:
        return re.findall(r"[A-Za-z0-9][A-Za-z0-9.+_-]*", value)[:8]


# ── module-level canonical mapping ─────────────────────────────────────

_SOURCE_TYPE_ALIASES: dict[str, str] = {
    "news": "google_news",
    "google": "google_news",
    "google_news_rss": "google_news",
    "hn": "hacker_news",
    "hackernews": "hacker_news",
    "rss_feeds": "rss",
    "rss_feed": "rss",
    "twitter": "x",
    "x_com": "x",
    "linuxdo": "linux_do",
    "linux_do_discourse": "linux_do",
    "xhs": "xiaohongshu",
    "red": "xiaohongshu",
}


def _canonical_source_type(value: str) -> str:
    normalized = DataSourceProvider.clean_text(value).lower().replace("-", "_").replace(".", "_")
    return _SOURCE_TYPE_ALIASES.get(normalized, normalized)
