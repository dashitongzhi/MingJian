"""Custom data source CRUD API.

Endpoints for managing user-defined data sources that extend the built-in
provider set. Custom sources are persisted in YAML config and loaded into
the SourceRegistry at runtime.
"""

from __future__ import annotations

import copy
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from planagent.config import get_settings
from planagent.services.sources.custom_provider import (
    CustomSourceProvider,
    load_custom_source_configs,
    save_custom_source_configs,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Custom Sources"])


# ── Pydantic models ───────────────────────────────────────────────────


class CustomSourceCreate(BaseModel):
    """Create a new custom data source."""

    key: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(..., min_length=1, max_length=200)
    type: str = Field(default="api", pattern=r"^(api|rss|json_feed)$")
    url: str = Field(..., min_length=1)
    headers: dict[str, str] = Field(default_factory=dict)
    auth_token: str | None = None
    item_path: str = ""
    field_map: dict[str, str] = Field(default_factory=dict)
    query_param: str = "q"
    limit_param: str = "limit"
    domain_param: str | None = None
    content_type: str = "text/html"
    enabled: bool = True
    default_limit: int = Field(default=5, ge=0, le=25)
    agent_name: str = "自定义源探员"
    agent_icon: str = "🔌"
    task_desc: str = ""
    fallback_keys: list[str] = Field(default_factory=list)

    @field_validator("key")
    @classmethod
    def key_must_not_be_builtin(cls, v: str) -> str:
        builtin = {
            "google_news", "reddit", "hacker_news", "github", "rss",
            "gdelt", "weather", "aviation", "x", "linux_do", "xiaohongshu", "douyin",
        }
        if v in builtin:
            raise ValueError(f"Key '{v}' conflicts with a built-in source provider")
        return v


class CustomSourceUpdate(BaseModel):
    """Update an existing custom data source. All fields optional."""

    label: str | None = None
    type: str | None = None
    url: str | None = None
    headers: dict[str, str] | None = None
    auth_token: str | None = None
    item_path: str | None = None
    field_map: dict[str, str] | None = None
    query_param: str | None = None
    limit_param: str | None = None
    domain_param: str | None = None
    content_type: str | None = None
    enabled: bool | None = None
    default_limit: int | None = None
    agent_name: str | None = None
    agent_icon: str | None = None
    task_desc: str | None = None
    fallback_keys: list[str] | None = None


class CustomSourceRead(BaseModel):
    """Read model for a custom data source."""

    key: str
    label: str
    type: str
    url: str
    enabled: bool
    default_limit: int
    agent_name: str
    agent_icon: str
    has_auth: bool
    item_path: str
    field_map: dict[str, str]


class CustomSourceTestResult(BaseModel):
    """Result of testing a custom source."""

    ok: bool
    items_found: int = 0
    sample_titles: list[str] = Field(default_factory=list)
    latency_ms: int = 0
    error: str | None = None


# ── Helpers ────────────────────────────────────────────────────────────


def _load_configs() -> list[dict[str, Any]]:
    return load_custom_source_configs(get_settings())


def _save_configs(configs: list[dict[str, Any]]) -> None:
    save_custom_source_configs(get_settings(), configs)


def _find_config(configs: list[dict[str, Any]], key: str) -> dict[str, Any] | None:
    for cfg in configs:
        if cfg.get("key") == key:
            return cfg
    return None


def _to_read(cfg: dict[str, Any]) -> CustomSourceRead:
    return CustomSourceRead(
        key=cfg.get("key", ""),
        label=cfg.get("label", ""),
        type=cfg.get("type", "api"),
        url=cfg.get("url", ""),
        enabled=cfg.get("enabled", True),
        default_limit=cfg.get("default_limit", 5),
        agent_name=cfg.get("agent_name", "自定义源探员"),
        agent_icon=cfg.get("agent_icon", "🔌"),
        has_auth=bool(cfg.get("auth_token")),
        item_path=cfg.get("item_path", ""),
        field_map=cfg.get("field_map", {}),
    )


# ── Endpoints ─────────────────────────────────────────────────────────


@router.get("/sources/custom", response_model=list[CustomSourceRead])
async def list_custom_sources() -> list[CustomSourceRead]:
    """List all user-defined custom data sources."""
    configs = _load_configs()
    return [_to_read(cfg) for cfg in configs]


@router.post("/sources/custom", response_model=CustomSourceRead, status_code=201)
async def create_custom_source(body: CustomSourceCreate) -> CustomSourceRead:
    """Create a new custom data source."""
    configs = _load_configs()
    if _find_config(configs, body.key):
        raise HTTPException(status_code=409, detail=f"Custom source '{body.key}' already exists")

    new_cfg = body.model_dump()
    configs.append(new_cfg)
    _save_configs(configs)

    logger.info("Created custom source: %s", body.key)
    return _to_read(new_cfg)


@router.get("/sources/custom/{source_key}", response_model=CustomSourceRead)
async def get_custom_source(source_key: str) -> CustomSourceRead:
    """Get a single custom source by key."""
    configs = _load_configs()
    cfg = _find_config(configs, source_key)
    if cfg is None:
        raise HTTPException(status_code=404, detail=f"Custom source '{source_key}' not found")
    return _to_read(cfg)


@router.put("/sources/custom/{source_key}", response_model=CustomSourceRead)
async def update_custom_source(source_key: str, body: CustomSourceUpdate) -> CustomSourceRead:
    """Update an existing custom source."""
    configs = _load_configs()
    cfg = _find_config(configs, source_key)
    if cfg is None:
        raise HTTPException(status_code=404, detail=f"Custom source '{source_key}' not found")

    updates = body.model_dump(exclude_unset=True)
    cfg.update(updates)
    _save_configs(configs)

    logger.info("Updated custom source: %s", source_key)
    return _to_read(cfg)


@router.delete("/sources/custom/{source_key}", status_code=204)
async def delete_custom_source(source_key: str) -> None:
    """Delete a custom data source."""
    configs = _load_configs()
    new_configs = [cfg for cfg in configs if cfg.get("key") != source_key]
    if len(new_configs) == len(configs):
        raise HTTPException(status_code=404, detail=f"Custom source '{source_key}' not found")

    _save_configs(new_configs)
    logger.info("Deleted custom source: %s", source_key)


@router.post("/sources/custom/{source_key}/test", response_model=CustomSourceTestResult)
async def test_custom_source(source_key: str) -> CustomSourceTestResult:
    """Test a custom source by fetching sample data."""
    import time

    configs = _load_configs()
    cfg = _find_config(configs, source_key)
    if cfg is None:
        raise HTTPException(status_code=404, detail=f"Custom source '{source_key}' not found")

    try:
        provider = CustomSourceProvider(cfg, get_settings())
        if provider.is_available():
            return CustomSourceTestResult(ok=False, error=provider.is_available())

        start = time.monotonic()
        import asyncio
        results = await asyncio.wait_for(
            provider.fetch("test", 3, "general"),
            timeout=30,
        )
        latency = int((time.monotonic() - start) * 1000)

        return CustomSourceTestResult(
            ok=True,
            items_found=len(results),
            sample_titles=[r.title for r in results[:3]],
            latency_ms=latency,
        )
    except Exception as exc:
        return CustomSourceTestResult(ok=False, error=str(exc)[:300])


# ── Provider listing (MCP-ified) ─────────────────────────────────────


@router.get("/sources/providers")
async def list_all_source_providers() -> list[dict[str, Any]]:
    """List all source providers (built-in + custom) with MCP-style metadata.

    Returns tool descriptions, config schemas, and availability status.
    """
    from planagent.services.openai_client import OpenAIService
    from planagent.services.sources.registry import SourceRegistry

    settings = get_settings()
    openai_service = OpenAIService(settings) if settings.openai_enabled else None
    registry = SourceRegistry(settings, openai_service)

    providers = []
    for provider in registry.all_providers():
        info = provider.get_config()
        info["description_tool"] = provider.describe()
        info["is_custom"] = isinstance(provider, CustomSourceProvider)
        providers.append(info)

    return providers
