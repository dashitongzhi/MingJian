"""Tests for built-in source provider registry behavior."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest


_ENTITY_XML = """<?xml version="1.0"?>
<!DOCTYPE rss [<!ENTITY expanded "untrusted entity content">]>
<rss><channel><item><title>&expanded;</title><link>https://example.com/item</link></item></channel></rss>
"""


class _FakeXMLResponse:
    text = _ENTITY_XML

    def raise_for_status(self) -> None:
        return None


class _FakeAsyncClient:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        _ = (args, kwargs)

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        _ = args

    async def get(self, *args: Any, **kwargs: Any) -> _FakeXMLResponse:
        _ = (args, kwargs)
        return _FakeXMLResponse()

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


@pytest.mark.parametrize("provider_name", ["google_news", "rss"])
async def test_xml_source_providers_reject_entity_declarations(
    monkeypatch: pytest.MonkeyPatch,
    provider_name: str,
) -> None:
    from planagent.services.sources.google_news import GoogleNewsProvider
    from planagent.services.sources.rss import RSSProvider

    monkeypatch.setattr("httpx.AsyncClient", _FakeAsyncClient)
    settings = _make_settings(additional_rss_feeds="https://feeds.example.test/rss")
    provider = (
        GoogleNewsProvider(settings) if provider_name == "google_news" else RSSProvider(settings)
    )

    with pytest.raises(Exception) as exc_info:
        await provider.fetch("expanded", limit=1, domain_id="general")

    assert exc_info.value.__class__.__name__ == "EntitiesForbidden"
