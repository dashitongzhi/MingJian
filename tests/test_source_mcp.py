"""Tests for data source MCP-ification and custom source plugin system.

Covers:
- SourceRegistry fallback/degradation logic
- CustomSourceProvider (API, RSS, JSON Feed)
- Custom source CRUD API endpoints
- MCP-style provider listing
- Fallback chains
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Helpers ────────────────────────────────────────────────────────────


def _make_settings(**overrides: Any) -> Any:
    """Create a minimal settings mock."""
    settings = MagicMock()
    settings.additional_rss_feeds = ""
    settings.custom_sources_dir = None
    settings.source_failure_degraded_threshold = 5
    settings.openai_enabled = False
    for k, v in overrides.items():
        setattr(settings, k, v)
    return settings


# ── SourceRegistry tests ───────────────────────────────────────────────


class TestSourceRegistry:
    """Test the SourceRegistry class."""

    def test_registry_loads_builtin_providers(self):
        """Registry should auto-discover all built-in providers."""
        from planagent.services.sources.registry import SourceRegistry

        registry = SourceRegistry(_make_settings())
        keys = registry.list_provider_keys()

        assert "google_news" in keys
        assert "reddit" in keys
        assert "hacker_news" in keys
        assert "github" in keys
        assert "rss" in keys

    def test_registry_get_returns_provider(self):
        """get() should return the correct provider instance."""
        from planagent.services.sources.registry import SourceRegistry

        registry = SourceRegistry(_make_settings())
        hn = registry.get("hacker_news")

        assert hn is not None
        assert hn.key == "hacker_news"
        assert hn.label == "Hacker News"

    def test_registry_get_returns_none_for_unknown(self):
        """get() should return None for unregistered keys."""
        from planagent.services.sources.registry import SourceRegistry

        registry = SourceRegistry(_make_settings())
        assert registry.get("nonexistent_source") is None

    def test_registry_register_dynamic(self):
        """register() should add a provider at runtime."""
        from planagent.services.sources.base import DataSourceProvider
        from planagent.services.sources.registry import SourceRegistry

        registry = SourceRegistry(_make_settings())

        # Create a mock provider
        mock_provider = MagicMock(spec=DataSourceProvider)
        mock_provider.key = "dynamic_test"
        mock_provider.label = "Dynamic Test"

        registry.register(mock_provider)
        assert registry.get("dynamic_test") is mock_provider

    def test_registry_unregister(self):
        """unregister() should remove a dynamically registered provider."""
        from planagent.services.sources.base import DataSourceProvider
        from planagent.services.sources.registry import SourceRegistry

        registry = SourceRegistry(_make_settings())

        mock_provider = MagicMock(spec=DataSourceProvider)
        mock_provider.key = "to_remove"
        mock_provider.label = "To Remove"

        registry.register(mock_provider)
        assert registry.get("to_remove") is not None

        result = registry.unregister("to_remove")
        assert result is True
        assert registry.get("to_remove") is None

    def test_registry_unregister_nonexistent(self):
        """unregister() returns False for unknown keys."""
        from planagent.services.sources.registry import SourceRegistry

        registry = SourceRegistry(_make_settings())
        assert registry.unregister("nonexistent") is False

    def test_registry_describe_all(self):
        """describe_all() should return MCP-style tool descriptions."""
        from planagent.services.sources.registry import SourceRegistry

        registry = SourceRegistry(_make_settings())
        descriptions = registry.describe_all()

        assert len(descriptions) > 0
        for desc in descriptions:
            assert "name" in desc
            assert "description" in desc
            assert "parameters" in desc

    def test_registry_config_all(self):
        """config_all() should return config info for all providers."""
        from planagent.services.sources.registry import SourceRegistry

        registry = SourceRegistry(_make_settings())
        configs = registry.config_all()

        assert len(configs) > 0
        for cfg in configs:
            assert "key" in cfg
            assert "label" in cfg
            assert "default_enabled" in cfg

    @pytest.mark.asyncio
    async def test_fetch_with_fallback_primary_success(self):
        """fetch_with_fallback should use primary if it succeeds."""
        from planagent.domain.api import AnalysisSourceRead
        from planagent.services.sources.registry import SourceRegistry

        registry = SourceRegistry(_make_settings())

        # Mock the hacker_news provider to succeed
        mock_results = [
            AnalysisSourceRead(
                source_type="hacker_news",
                title="Test",
                url="https://example.com",
                summary="Test summary",
            )
        ]
        registry.get("hacker_news").fetch = AsyncMock(return_value=mock_results)

        results, attempted = await registry.fetch_with_fallback(
            "hacker_news", "test query", 5, "general"
        )

        assert len(results) == 1
        assert "hacker_news" in attempted

    @pytest.mark.asyncio
    async def test_fetch_with_fallback_primary_fails(self):
        """fetch_with_fallback should try fallbacks when primary fails."""
        from planagent.domain.api import AnalysisSourceRead
        from planagent.services.sources.registry import SourceRegistry

        registry = SourceRegistry(_make_settings())

        # Mock hacker_news to fail
        registry.get("hacker_news").fetch = AsyncMock(side_effect=Exception("API Error"))

        # Mock reddit (fallback) to succeed
        mock_results = [
            AnalysisSourceRead(
                source_type="reddit_search",
                title="Fallback Result",
                url="https://reddit.com/test",
                summary="Fallback summary",
            )
        ]
        registry.get("reddit").fetch = AsyncMock(return_value=mock_results)

        results, attempted = await registry.fetch_with_fallback(
            "hacker_news", "test query", 5, "general"
        )

        assert len(results) == 1
        assert results[0].title == "Fallback Result"
        assert "hacker_news" in attempted
        assert "reddit" in attempted

    @pytest.mark.asyncio
    async def test_fetch_with_fallback_all_fail(self):
        """fetch_with_fallback returns empty if all sources fail."""
        from planagent.services.sources.registry import SourceRegistry

        registry = SourceRegistry(_make_settings())

        # Make all fail
        registry.get("hacker_news").fetch = AsyncMock(side_effect=Exception("Error"))
        registry.get("reddit").fetch = AsyncMock(side_effect=Exception("Error"))
        registry.get("google_news").fetch = AsyncMock(side_effect=Exception("Error"))

        results, attempted = await registry.fetch_with_fallback(
            "hacker_news", "test", 5, "general"
        )

        assert results == []
        assert len(attempted) >= 1

    @pytest.mark.asyncio
    async def test_fetch_with_fallback_unknown_key(self):
        """fetch_with_fallback returns empty for unknown provider."""
        from planagent.services.sources.registry import SourceRegistry

        registry = SourceRegistry(_make_settings())
        results, attempted = await registry.fetch_with_fallback(
            "unknown_source", "test", 5, "general"
        )

        assert results == []
        assert attempted == ["unknown_source"]

    def test_build_adapters(self):
        """build_adapters should create adapters for all providers."""
        from planagent.domain.api import AnalysisRequest
        from planagent.services.sources.registry import SourceRegistry

        registry = SourceRegistry(_make_settings())
        payload = AnalysisRequest(content="test query")
        adapters = registry.build_adapters(payload, "test query", "general")

        assert len(adapters) > 0
        keys = [a.key for a in adapters]
        assert "hacker_news" in keys
        assert "google_news" in keys


# ── DataSourceProvider MCP interface tests ─────────────────────────────


class TestDataSourceProviderMCPInterface:
    """Test the MCP-ified interface on the base class."""

    def test_describe_returns_mcp_tool(self):
        """describe() should return MCP-style tool description."""
        from planagent.services.sources.registry import SourceRegistry

        registry = SourceRegistry(_make_settings())
        hn = registry.get("hacker_news")
        desc = hn.describe()

        assert desc["name"] == "hacker_news"
        assert desc["description"] == "Hacker News"
        assert "parameters" in desc
        assert "query" in desc["parameters"]["properties"]

    def test_get_config_returns_config_info(self):
        """get_config() should return provider configuration."""
        from planagent.services.sources.registry import SourceRegistry

        registry = SourceRegistry(_make_settings())
        hn = registry.get("hacker_news")
        config = hn.get_config()

        assert config["key"] == "hacker_news"
        assert config["label"] == "Hacker News"
        assert config["default_limit"] == 3

    def test_fallback_keys_default_empty(self):
        """Default fallback_keys should be empty list."""
        from planagent.services.sources.base import DataSourceProvider

        class MinimalProvider(DataSourceProvider):
            key = "minimal"
            label = "Minimal"

            async def fetch(self, query, limit, domain_id):
                return []

        provider = MinimalProvider(_make_settings())
        assert provider.fallback_keys == []

    def test_fallback_keys_on_google_news(self):
        """Google News should have fallback keys defined."""
        from planagent.services.sources.registry import SourceRegistry

        registry = SourceRegistry(_make_settings())
        gn = registry.get("google_news")
        assert "rss" in gn.fallback_keys
        assert "hacker_news" in gn.fallback_keys

    def test_fallback_keys_on_reddit(self):
        """Reddit should have fallback keys defined."""
        from planagent.services.sources.registry import SourceRegistry

        registry = SourceRegistry(_make_settings())
        reddit = registry.get("reddit")
        assert "hacker_news" in reddit.fallback_keys

    @pytest.mark.asyncio
    async def test_search_delegates_to_fetch(self):
        """search() should delegate to fetch() by default."""
        from planagent.domain.api import AnalysisSourceRead
        from planagent.services.sources.registry import SourceRegistry

        registry = SourceRegistry(_make_settings())
        hn = registry.get("hacker_news")

        mock_results = [
            AnalysisSourceRead(
                source_type="hacker_news",
                title="Test",
                url="https://example.com",
                summary="Test",
            )
        ]
        hn.fetch = AsyncMock(return_value=mock_results)

        results = await hn.search("test", limit=5, domain_id="general")
        hn.fetch.assert_called_once_with("test", 5, "general")
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_list_sources_returns_self(self):
        """list_sources() should return the provider itself by default."""
        from planagent.services.sources.registry import SourceRegistry

        registry = SourceRegistry(_make_settings())
        hn = registry.get("hacker_news")
        sources = await hn.list_sources()

        assert len(sources) == 1
        assert sources[0]["key"] == "hacker_news"
        assert sources[0]["label"] == "Hacker News"


# ── CustomSourceProvider tests ─────────────────────────────────────────


class TestCustomSourceProvider:
    """Test the CustomSourceProvider class."""

    def test_custom_provider_from_config(self):
        """CustomSourceProvider should be created from config dict."""
        from planagent.services.sources.custom_provider import CustomSourceProvider

        config = {
            "key": "my_custom",
            "label": "My Custom Source",
            "type": "api",
            "url": "https://api.example.com/search",
        }
        provider = CustomSourceProvider(config, _make_settings())

        assert provider.key == "my_custom"
        assert provider.label == "My Custom Source"
        assert provider.default_enabled is True

    def test_custom_provider_is_available(self):
        """CustomSourceProvider should report availability based on URL."""
        from planagent.services.sources.custom_provider import CustomSourceProvider

        config = {"key": "test", "label": "Test", "url": "https://example.com"}
        provider = CustomSourceProvider(config, _make_settings())
        assert provider.is_available() is None

        config_no_url = {"key": "test", "label": "Test", "url": ""}
        provider_no_url = CustomSourceProvider(config_no_url, _make_settings())
        assert provider_no_url.is_available() == "No URL configured"

    def test_custom_provider_describe(self):
        """CustomSourceProvider should return MCP tool description."""
        from planagent.services.sources.custom_provider import CustomSourceProvider

        config = {"key": "my_src", "label": "My Source", "url": "https://example.com"}
        provider = CustomSourceProvider(config, _make_settings())
        desc = provider.describe()

        assert desc["name"] == "my_src"
        assert "custom" in desc["description"].lower()

    def test_custom_provider_get_config(self):
        """CustomSourceProvider should expose config details."""
        from planagent.services.sources.custom_provider import CustomSourceProvider

        config = {
            "key": "my_src",
            "label": "My Source",
            "type": "rss",
            "url": "https://example.com/feed.xml",
        }
        provider = CustomSourceProvider(config, _make_settings())
        cfg = provider.get_config()

        assert cfg["key"] == "my_src"
        assert cfg["source_type"] == "rss"
        assert cfg["url"] == "https://example.com/feed.xml"

    @pytest.mark.asyncio
    async def test_custom_provider_fetch_api(self):
        """CustomSourceProvider should fetch from a JSON API."""
        import httpx

        from planagent.services.sources.custom_provider import CustomSourceProvider

        config = {
            "key": "test_api",
            "label": "Test API",
            "type": "api",
            "url": "https://api.example.com/search",
            "item_path": "results",
            "field_map": {"title": "name", "url": "link"},
        }
        provider = CustomSourceProvider(config, _make_settings())

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "results": [
                {"name": "Article 1", "link": "https://example.com/1", "description": "Summary 1"},
                {"name": "Article 2", "link": "https://example.com/2", "description": "Summary 2"},
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            results = await provider.fetch("test", 5, "general")

        assert len(results) == 2
        assert results[0].title == "Article 1"
        assert results[0].url == "https://example.com/1"

    @pytest.mark.asyncio
    async def test_custom_provider_fetch_json_feed(self):
        """CustomSourceProvider should fetch from a JSON Feed."""
        from planagent.services.sources.custom_provider import CustomSourceProvider

        config = {
            "key": "jf_test",
            "label": "JSON Feed Test",
            "type": "json_feed",
            "url": "https://example.com/feed.json",
        }
        provider = CustomSourceProvider(config, _make_settings())

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "items": [
                {
                    "title": "Feed Item 1",
                    "url": "https://example.com/item1",
                    "content_text": "Content 1",
                    "date_published": "2024-01-01T00:00:00Z",
                },
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            results = await provider.fetch("test", 5, "general")

        assert len(results) == 1
        assert results[0].title == "Feed Item 1"
        assert results[0].source_type == "jf_test"


# ── Custom source config persistence tests ─────────────────────────────


class TestCustomSourceConfig:
    """Test custom source config file operations."""

    def test_load_configs_from_yaml(self, tmp_path):
        """Should load custom source configs from YAML file."""
        from planagent.services.sources.custom_provider import load_custom_source_configs

        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = config_dir / "custom_sources.yaml"
        config_file.write_text(
            """
sources:
  - key: my_feed
    label: My Feed
    type: rss
    url: https://example.com/feed.xml
  - key: my_api
    label: My API
    type: api
    url: https://api.example.com
""",
            encoding="utf-8",
        )

        settings = MagicMock()
        settings.custom_sources_dir = str(config_dir)

        configs = load_custom_source_configs(settings)
        assert len(configs) == 2
        assert configs[0]["key"] == "my_feed"
        assert configs[1]["key"] == "my_api"

    def test_save_configs_to_yaml(self, tmp_path):
        """Should save custom source configs to YAML file."""
        from planagent.services.sources.custom_provider import save_custom_source_configs

        config_dir = tmp_path / "config"
        config_dir.mkdir()

        settings = MagicMock()
        settings.custom_sources_dir = str(config_dir)

        configs = [
            {"key": "saved_feed", "label": "Saved Feed", "type": "rss", "url": "https://example.com"},
        ]
        save_custom_source_configs(settings, configs)

        config_file = config_dir / "custom_sources.yaml"
        assert config_file.exists()

        content = config_file.read_text(encoding="utf-8")
        assert "saved_feed" in content

    def test_load_configs_missing_file(self, tmp_path):
        """Should return empty list when config file doesn't exist."""
        from planagent.services.sources.custom_provider import load_custom_source_configs

        settings = MagicMock()
        settings.custom_sources_dir = str(tmp_path / "nonexistent")

        configs = load_custom_source_configs(settings)
        assert configs == []

    def test_create_custom_providers(self, tmp_path):
        """create_custom_providers should create provider instances."""
        from planagent.services.sources.custom_provider import create_custom_providers

        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = config_dir / "custom_sources.yaml"
        config_file.write_text(
            """
sources:
  - key: test_custom
    label: Test Custom
    type: api
    url: https://api.test.com
""",
            encoding="utf-8",
        )

        settings = MagicMock()
        settings.custom_sources_dir = str(config_dir)

        providers = create_custom_providers(settings)
        assert len(providers) == 1
        assert providers[0].key == "test_custom"


# ── Custom source API endpoint tests ──────────────────────────────────


class TestCustomSourceAPI:
    """Test the custom sources API endpoints."""

    def _make_app(self, tmp_path):
        """Create a FastAPI test app with custom sources routes."""
        import os

        from fastapi import FastAPI

        from planagent.api.routes.custom_sources import router

        # Set up config directory
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "custom_sources.yaml").write_text("sources: []\n", encoding="utf-8")

        os.environ["PLANAGENT_CUSTOM_SOURCES_DIR"] = str(config_dir)

        app = FastAPI()
        app.include_router(router)
        return app

    def test_list_custom_sources_empty(self, tmp_path):
        """GET /sources/custom should return empty list initially."""
        from fastapi.testclient import TestClient

        app = self._make_app(tmp_path)
        client = TestClient(app)

        resp = client.get("/sources/custom")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_custom_source(self, tmp_path):
        """POST /sources/custom should create a new source."""
        from fastapi.testclient import TestClient

        app = self._make_app(tmp_path)
        client = TestClient(app)

        payload = {
            "key": "my_source",
            "label": "My Source",
            "type": "api",
            "url": "https://api.example.com/search",
        }
        resp = client.post("/sources/custom", json=payload)
        assert resp.status_code == 201

        data = resp.json()
        assert data["key"] == "my_source"
        assert data["label"] == "My Source"
        assert data["type"] == "api"

    def test_create_duplicate_custom_source(self, tmp_path):
        """POST /sources/custom should return 409 for duplicate key."""
        from fastapi.testclient import TestClient

        app = self._make_app(tmp_path)
        client = TestClient(app)

        payload = {
            "key": "dup_source",
            "label": "Dup Source",
            "url": "https://api.example.com",
        }
        client.post("/sources/custom", json=payload)
        resp = client.post("/sources/custom", json=payload)
        assert resp.status_code == 409

    def test_get_custom_source(self, tmp_path):
        """GET /sources/custom/{key} should return a source."""
        from fastapi.testclient import TestClient

        app = self._make_app(tmp_path)
        client = TestClient(app)

        payload = {
            "key": "get_test",
            "label": "Get Test",
            "url": "https://api.example.com",
        }
        client.post("/sources/custom", json=payload)

        resp = client.get("/sources/custom/get_test")
        assert resp.status_code == 200
        assert resp.json()["key"] == "get_test"

    def test_get_custom_source_not_found(self, tmp_path):
        """GET /sources/custom/{key} should return 404 for unknown key."""
        from fastapi.testclient import TestClient

        app = self._make_app(tmp_path)
        client = TestClient(app)

        resp = client.get("/sources/custom/nonexistent")
        assert resp.status_code == 404

    def test_update_custom_source(self, tmp_path):
        """PUT /sources/custom/{key} should update a source."""
        from fastapi.testclient import TestClient

        app = self._make_app(tmp_path)
        client = TestClient(app)

        payload = {
            "key": "update_test",
            "label": "Original",
            "url": "https://api.example.com",
        }
        client.post("/sources/custom", json=payload)

        resp = client.put(
            "/sources/custom/update_test",
            json={"label": "Updated Label"},
        )
        assert resp.status_code == 200
        assert resp.json()["label"] == "Updated Label"

    def test_update_custom_source_not_found(self, tmp_path):
        """PUT /sources/custom/{key} should return 404 for unknown key."""
        from fastapi.testclient import TestClient

        app = self._make_app(tmp_path)
        client = TestClient(app)

        resp = client.put("/sources/custom/nonexistent", json={"label": "X"})
        assert resp.status_code == 404

    def test_delete_custom_source(self, tmp_path):
        """DELETE /sources/custom/{key} should delete a source."""
        from fastapi.testclient import TestClient

        app = self._make_app(tmp_path)
        client = TestClient(app)

        payload = {
            "key": "delete_test",
            "label": "Delete Test",
            "url": "https://api.example.com",
        }
        client.post("/sources/custom", json=payload)

        resp = client.delete("/sources/custom/delete_test")
        assert resp.status_code == 204

        # Verify deleted
        resp = client.get("/sources/custom/delete_test")
        assert resp.status_code == 404

    def test_delete_custom_source_not_found(self, tmp_path):
        """DELETE /sources/custom/{key} should return 404 for unknown key."""
        from fastapi.testclient import TestClient

        app = self._make_app(tmp_path)
        client = TestClient(app)

        resp = client.delete("/sources/custom/nonexistent")
        assert resp.status_code == 404

    def test_create_custom_source_rejects_builtin_key(self, tmp_path):
        """POST /sources/custom should reject keys that conflict with built-in sources."""
        from fastapi.testclient import TestClient

        app = self._make_app(tmp_path)
        client = TestClient(app)

        payload = {
            "key": "hacker_news",
            "label": "Hacker News Clone",
            "url": "https://api.example.com",
        }
        resp = client.post("/sources/custom", json=payload)
        assert resp.status_code == 422  # Validation error

    def test_full_crud_flow(self, tmp_path):
        """Test complete Create → Read → Update → Delete flow."""
        from fastapi.testclient import TestClient

        app = self._make_app(tmp_path)
        client = TestClient(app)

        # Create
        resp = client.post("/sources/custom", json={
            "key": "flow_test",
            "label": "Flow Test",
            "type": "rss",
            "url": "https://example.com/feed.xml",
        })
        assert resp.status_code == 201

        # Read
        resp = client.get("/sources/custom/flow_test")
        assert resp.status_code == 200
        assert resp.json()["type"] == "rss"

        # Update
        resp = client.put("/sources/custom/flow_test", json={
            "label": "Updated Flow Test",
            "type": "json_feed",
        })
        assert resp.status_code == 200
        assert resp.json()["label"] == "Updated Flow Test"
        assert resp.json()["type"] == "json_feed"

        # List (should contain our source)
        resp = client.get("/sources/custom")
        assert resp.status_code == 200
        keys = [s["key"] for s in resp.json()]
        assert "flow_test" in keys

        # Delete
        resp = client.delete("/sources/custom/flow_test")
        assert resp.status_code == 204

        # Verify gone
        resp = client.get("/sources/custom")
        keys = [s["key"] for s in resp.json()]
        assert "flow_test" not in keys


# ── SourceAdapter tests ────────────────────────────────────────────────


class TestSourceAdapter:
    """Test the _SourceAdapter wrapper."""

    def test_adapter_delegates_properties(self):
        """Adapter should delegate all properties to the provider."""
        from planagent.domain.api import AnalysisRequest
        from planagent.services.sources.registry import _SourceRegistry__SourceAdapter as _SourceAdapter
        from planagent.services.sources.registry import SourceRegistry

        registry = SourceRegistry(_make_settings())
        hn = registry.get("hacker_news")

        payload = AnalysisRequest(content="test", source_types=["hacker_news"])
        adapters = registry.build_adapters(payload, "test", "general")

        hn_adapter = next(a for a in adapters if a.key == "hacker_news")
        assert hn_adapter.label == "Hacker News"
        assert hn_adapter.enabled is True

    @pytest.mark.asyncio
    async def test_adapter_fetch_delegates(self):
        """Adapter fetch should delegate to provider."""
        from planagent.domain.api import AnalysisRequest, AnalysisSourceRead
        from planagent.services.sources.registry import SourceRegistry

        registry = SourceRegistry(_make_settings())
        hn = registry.get("hacker_news")

        mock_results = [
            AnalysisSourceRead(
                source_type="hacker_news",
                title="Adapter Test",
                url="https://example.com",
                summary="Test",
            )
        ]
        hn.fetch = AsyncMock(return_value=mock_results)

        payload = AnalysisRequest(content="test")
        adapters = registry.build_adapters(payload, "test", "general")
        hn_adapter = next(a for a in adapters if a.key == "hacker_news")

        results = await hn_adapter.fetch(5)
        assert len(results) == 1
        assert results[0].title == "Adapter Test"


# ── Edge case tests ───────────────────────────────────────────────────


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_resolve_field_nested(self):
        """_resolve_field should handle nested dot paths."""
        from planagent.services.sources.custom_provider import _resolve_field

        item = {"data": {"results": {"title": "Nested Title"}}}
        assert _resolve_field(item, "data.results.title") == "Nested Title"

    def test_resolve_field_missing(self):
        """_resolve_field should return empty string for missing fields."""
        from planagent.services.sources.custom_provider import _resolve_field

        item = {"data": {"title": "Test"}}
        assert _resolve_field(item, "data.missing") == ""
        assert _resolve_field(item, "") == ""
        assert _resolve_field(item, "nonexistent.path") == ""

    def test_resolve_field_non_dict(self):
        """_resolve_field should handle non-dict intermediate values."""
        from planagent.services.sources.custom_provider import _resolve_field

        item = {"data": "not a dict"}
        assert _resolve_field(item, "data.title") == ""

    def test_canonical_source_type(self):
        """_canonical_source_type should normalize aliases."""
        from planagent.services.sources.base import _canonical_source_type

        assert _canonical_source_type("hn") == "hacker_news"
        assert _canonical_source_type("news") == "google_news"
        assert _canonical_source_type("twitter") == "x"
        assert _canonical_source_type("xhs") == "xiaohongshu"
        assert _canonical_source_type("unknown_source") == "unknown_source"

    def test_custom_source_config_empty(self, tmp_path):
        """Should handle empty config file gracefully."""
        from planagent.services.sources.custom_provider import load_custom_source_configs

        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "custom_sources.yaml").write_text("sources: []\n", encoding="utf-8")

        settings = MagicMock()
        settings.custom_sources_dir = str(config_dir)

        configs = load_custom_source_configs(settings)
        assert configs == []

    @pytest.mark.asyncio
    async def test_custom_provider_empty_url_returns_empty(self):
        """CustomSourceProvider with empty URL should return empty results."""
        from planagent.services.sources.custom_provider import CustomSourceProvider

        config = {"key": "empty", "label": "Empty", "url": ""}
        provider = CustomSourceProvider(config, _make_settings())

        results = await provider.fetch("test", 5, "general")
        assert results == []
