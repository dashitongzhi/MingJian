"""Tests for built-in source provider registry behavior."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock


def _make_settings(**overrides: Any) -> Any:
    settings = MagicMock()
    settings.additional_rss_feeds = ""
    settings.source_failure_degraded_threshold = 5
    settings.openai_enabled = False
    for key, value in overrides.items():
        setattr(settings, key, value)
    return settings


def test_registry_loads_builtin_providers() -> None:
    from planagent.services.sources.registry import SourceRegistry

    registry = SourceRegistry(_make_settings())
    keys = registry.list_provider_keys()

    assert "google_news" in keys
    assert "reddit" in keys
    assert "hacker_news" in keys
    assert "github" in keys
    assert "rss" in keys


def test_registry_get_returns_provider() -> None:
    from planagent.services.sources.registry import SourceRegistry

    registry = SourceRegistry(_make_settings())
    provider = registry.get("hacker_news")

    assert provider is not None
    assert provider.key == "hacker_news"
    assert provider.label == "Hacker News"


def test_registry_get_returns_none_for_unknown() -> None:
    from planagent.services.sources.registry import SourceRegistry

    registry = SourceRegistry(_make_settings())

    assert registry.get("nonexistent_source") is None


def test_registry_describes_builtin_providers() -> None:
    from planagent.services.sources.registry import SourceRegistry

    registry = SourceRegistry(_make_settings())
    descriptions = registry.describe_all()

    assert descriptions
    assert all("name" in item for item in descriptions)

