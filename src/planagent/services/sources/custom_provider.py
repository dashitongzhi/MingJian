"""Custom user-defined data source provider.

Loads custom source configurations from YAML/JSON and wraps them as
DataSourceProvider instances. Each custom source defines:
- An HTTP endpoint or RSS feed URL
- Response parsing hints (JSON path, XML path)
- Optional headers/auth

Configuration is stored in ``custom_sources.yaml`` (or .json) in the
project data directory.
"""

from __future__ import annotations

import json
import logging
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import httpx
import yaml

from planagent.domain.api import AnalysisSourceRead
from planagent.services.sources.base import DataSourceProvider

logger = logging.getLogger(__name__)

# ── Configuration storage ──────────────────────────────────────────────

_DEFAULT_CONFIG_DIR = Path("config")
_CUSTOM_SOURCES_FILE = "custom_sources.yaml"


def _config_path(settings: Any) -> Path:
    """Resolve the custom sources config file path."""
    base = getattr(settings, "custom_sources_dir", None)
    if base:
        return Path(base) / _CUSTOM_SOURCES_FILE
    return _DEFAULT_CONFIG_DIR / _CUSTOM_SOURCES_FILE


def load_custom_source_configs(settings: Any) -> list[dict[str, Any]]:
    """Load custom source configs from YAML/JSON file.

    Returns a list of source config dicts. Each must have at least:
    - ``key``: unique identifier
    - ``label``: display name
    - ``type``: "api" | "rss" | "json_feed"
    - ``url``: endpoint URL
    """
    path = _config_path(settings)
    if not path.exists():
        return []

    try:
        text = path.read_text(encoding="utf-8")
        if path.suffix in (".yaml", ".yml"):
            data = yaml.safe_load(text) or {}
        else:
            data = json.loads(text)

        sources = data.get("sources", []) if isinstance(data, dict) else []
        if not isinstance(sources, list):
            logger.warning("Custom sources config is not a list: %s", path)
            return []
        return sources
    except Exception as exc:
        logger.warning("Failed to load custom sources config %s: %s", path, exc)
        return []


def save_custom_source_configs(settings: Any, configs: list[dict[str, Any]]) -> None:
    """Save custom source configs to YAML file."""
    path = _config_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"sources": configs}
    path.write_text(yaml.dump(data, default_flow_style=False, allow_unicode=True), encoding="utf-8")


# ── Custom Provider ────────────────────────────────────────────────────


class CustomSourceProvider(DataSourceProvider):
    """A data source provider that wraps a user-defined HTTP endpoint.

    Supports three source types:
    - ``api``: Generic JSON API with configurable response parsing
    - ``rss``: RSS/Atom feed
    - ``json_feed``: JSON Feed format (https://jsonfeed.org)
    """

    def __init__(
        self,
        config: dict[str, Any],
        settings: Any,
        **deps: Any,
    ) -> None:
        self._config = config
        self._source_type = config.get("type", "api")
        self._url = config.get("url", "")
        self._headers = config.get("headers", {})
        self._auth_token = config.get("auth_token")
        self._item_path = config.get("item_path", "")
        self._field_map = config.get("field_map", {})
        self._content_type = config.get("content_type", "text/html")
        super().__init__(settings, **deps)

    @property
    def key(self) -> str:
        return self._config.get("key", "custom")

    @property
    def label(self) -> str:
        return self._config.get("label", self.key)

    @property
    def default_enabled(self) -> bool:
        return self._config.get("enabled", True)

    @property
    def default_limit(self) -> int:
        return self._config.get("default_limit", 5)

    @property
    def agent_name(self) -> str:
        return self._config.get("agent_name", "自定义源探员")

    @property
    def agent_icon(self) -> str:
        return self._config.get("agent_icon", "🔌")

    @property
    def task_desc(self) -> str:
        return self._config.get("task_desc", f"正在搜索 {self.label}")

    @property
    def fallback_keys(self) -> list[str]:
        return self._config.get("fallback_keys", [])

    def is_available(self) -> str | None:
        if not self._url:
            return "No URL configured"
        return None

    async def fetch(
        self,
        query: str,
        limit: int,
        domain_id: str,
    ) -> list[AnalysisSourceRead]:
        if not self._url:
            return []

        if self._source_type == "rss":
            return await self._fetch_rss(query, limit)
        elif self._source_type == "json_feed":
            return await self._fetch_json_feed(query, limit)
        else:
            return await self._fetch_api(query, limit, domain_id)

    def get_config(self) -> dict[str, Any]:
        base = super().get_config()
        base.update({
            "source_type": self._source_type,
            "url": self._url,
            "item_path": self._item_path,
            "field_map": self._field_map,
        })
        return base

    def describe(self) -> dict[str, Any]:
        desc = super().describe()
        desc["description"] = f"{self.label} (custom {self._source_type} source)"
        return desc

    # ── internal fetch strategies ──────────────────────────────────────

    async def _fetch_api(
        self,
        query: str,
        limit: int,
        domain_id: str,
    ) -> list[AnalysisSourceRead]:
        """Fetch from a generic JSON API endpoint."""
        headers = dict(self._headers)
        if self._auth_token:
            headers["Authorization"] = f"Bearer {self._auth_token}"

        params: dict[str, str] = {
            self._config.get("query_param", "q"): query,
            self._config.get("limit_param", "limit"): str(limit),
        }
        domain_param = self._config.get("domain_param")
        if domain_param:
            params[domain_param] = domain_id

        async with httpx.AsyncClient(follow_redirects=True, timeout=25) as client:
            response = await client.get(self._url, params=params, headers=headers)
            response.raise_for_status()

        payload = response.json()

        # Navigate to items using item_path (e.g., "data.results")
        items = payload
        if self._item_path:
            for segment in self._item_path.split("."):
                if isinstance(items, dict):
                    items = items.get(segment, [])
                else:
                    break

        if not isinstance(items, list):
            items = items.get("items", []) if isinstance(items, dict) else []

        # Map fields
        fmap = {
            "title": "title",
            "url": "url",
            "summary": "summary",
            "published_at": "published_at",
            **self._field_map,
        }

        results: list[AnalysisSourceRead] = []
        for item in items[:limit]:
            if not isinstance(item, dict):
                continue
            title = self.clean_text(_resolve_field(item, fmap["title"]))
            url_value = self.clean_text(_resolve_field(item, fmap["url"]))
            summary = self.clean_text(_resolve_field(item, fmap["summary"])) or title
            published_at = self.clean_text(_resolve_field(item, fmap["published_at"])) or None

            if not title or not url_value:
                continue

            results.append(
                AnalysisSourceRead(
                    source_type=self.key,
                    title=title,
                    url=url_value,
                    summary=summary,
                    published_at=published_at,
                    metadata={
                        "platform": self.key,
                        "provider": "custom",
                        "source_type": self._source_type,
                        "query_used": query,
                    },
                )
            )
        return results

    async def _fetch_rss(self, query: str, limit: int) -> list[AnalysisSourceRead]:
        """Fetch from an RSS/Atom feed."""
        headers = dict(self._headers)
        if self._auth_token:
            headers["Authorization"] = f"Bearer {self._auth_token}"

        async with httpx.AsyncClient(follow_redirects=True, timeout=25) as client:
            response = await client.get(self._url, headers=headers)
            response.raise_for_status()

        root = ET.fromstring(response.text)
        items = root.findall(".//item") + root.findall(".//{http://www.w3.org/2005/Atom}entry")

        query_tokens = set(self.ascii_keywords(query.lower()))
        results: list[AnalysisSourceRead] = []

        for item in items[:limit * 2]:  # fetch more to allow filtering
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

            if query_tokens:
                haystack = f"{title} {summary}".lower()
                if not any(token in haystack for token in query_tokens):
                    continue
            if not title or not link:
                continue
            results.append(
                AnalysisSourceRead(
                    source_type=self.key,
                    title=title,
                    url=link,
                    summary=summary or title,
                    published_at=published_at,
                    metadata={
                        "platform": self.key,
                        "provider": "custom_rss",
                        "query_used": query,
                    },
                )
            )
        return results

    async def _fetch_json_feed(self, query: str, limit: int) -> list[AnalysisSourceRead]:
        """Fetch from a JSON Feed (https://jsonfeed.org)."""
        headers = dict(self._headers)
        if self._auth_token:
            headers["Authorization"] = f"Bearer {self._auth_token}"

        async with httpx.AsyncClient(follow_redirects=True, timeout=25) as client:
            response = await client.get(self._url, headers=headers)
            response.raise_for_status()

        feed = response.json()
        items = feed.get("items", [])

        query_tokens = set(self.ascii_keywords(query.lower()))
        results: list[AnalysisSourceRead] = []

        for item in items[:limit * 2]:
            if len(results) >= limit:
                break
            title = self.clean_text(item.get("title") or "")
            url_value = self.clean_text(item.get("url") or item.get("external_url") or "")
            summary = self.clean_text(
                item.get("content_text") or item.get("content_html") or ""
            )
            published_at = self.clean_text(item.get("date_published") or "") or None

            if query_tokens:
                haystack = f"{title} {summary}".lower()
                if not any(token in haystack for token in query_tokens):
                    continue
            if not title or not url_value:
                continue
            results.append(
                AnalysisSourceRead(
                    source_type=self.key,
                    title=title,
                    url=url_value,
                    summary=summary or title,
                    published_at=published_at,
                    metadata={
                        "platform": self.key,
                        "provider": "custom_json_feed",
                        "query_used": query,
                    },
                )
            )
        return results

    @staticmethod
    def _rss_link(item: ET.Element) -> str:
        link = DataSourceProvider.clean_text(item.findtext("link", default=""))
        if link:
            return link
        atom_link = item.find("{http://www.w3.org/2005/Atom}link")
        if atom_link is not None:
            return DataSourceProvider.clean_text(atom_link.attrib.get("href", ""))
        return ""


# ── helpers ────────────────────────────────────────────────────────────


def _resolve_field(item: dict[str, Any], path: str) -> str:
    """Resolve a dot-separated field path from a dict.

    E.g., ``"data.title"`` → ``item["data"]["title"]``.
    """
    if not path:
        return ""
    current: Any = item
    for segment in path.split("."):
        if isinstance(current, dict):
            current = current.get(segment)
        else:
            return ""
        if current is None:
            return ""
    return str(current) if current is not None else ""


def create_custom_providers(settings: Any, **deps: Any) -> list[CustomSourceProvider]:
    """Load all custom source configs and create provider instances."""
    configs = load_custom_source_configs(settings)
    providers: list[CustomSourceProvider] = []
    for config in configs:
        if not config.get("key") or not config.get("url"):
            logger.warning("Skipping invalid custom source config: %s", config)
            continue
        try:
            providers.append(CustomSourceProvider(config, settings, **deps))
        except Exception as exc:
            logger.warning("Failed to create custom provider %s: %s", config.get("key"), exc)
    return providers
