"""Provider configuration API — manage model providers, API keys, and connection testing."""
from __future__ import annotations

import time
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/admin/providers", tags=["Providers"])


# ── Preset Providers ─────────────────────────────────────────────────────────


PROVIDER_PRESETS: list[dict[str, Any]] = [
    {
        "id": "openai",
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "api_format": "openai",
        "models": ["gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano", "gpt-4o", "gpt-4o-mini", "o3", "o4-mini"],
        "placeholder": "sk-...",
        "website": "https://platform.openai.com/api-keys",
        "color": "#10a37f",
    },
    {
        "id": "anthropic",
        "name": "Anthropic (Claude)",
        "base_url": "https://api.anthropic.com/v1/openai",
        "api_format": "openai",
        "models": ["claude-opus-4", "claude-sonnet-4", "claude-sonnet-3.5", "claude-haiku-3.5"],
        "placeholder": "sk-ant-...",
        "website": "https://console.anthropic.com/settings/keys",
        "color": "#d4a574",
    },
    {
        "id": "gemini",
        "name": "Google Gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "api_format": "openai",
        "models": ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-pro"],
        "placeholder": "AIza...",
        "website": "https://aistudio.google.com/apikey",
        "color": "#4285f4",
    },
    {
        "id": "grok",
        "name": "xAI Grok",
        "base_url": "https://api.x.ai/v1",
        "api_format": "openai",
        "models": ["grok-3", "grok-3-mini", "grok-2"],
        "placeholder": "xai-...",
        "website": "https://console.x.ai/",
        "color": "#1d1d1f",
    },
    {
        "id": "deepseek",
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "api_format": "openai",
        "models": ["deepseek-chat", "deepseek-reasoner"],
        "placeholder": "sk-...",
        "website": "https://platform.deepseek.com/api_keys",
        "color": "#4d6bfe",
    },
    {
        "id": "mimo",
        "name": "Xiaomi MiMo",
        "base_url": "https://token-plan-cn.xiaomimimo.com/v1",
        "api_format": "openai",
        "models": ["mimo-v2.5-pro", "mimo-v2-omni"],
        "placeholder": "your-api-key",
        "website": "https://mimo.xiaomi.com",
        "color": "#ff6900",
    },
    {
        "id": "glm",
        "name": "Zhipu GLM (智谱)",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "api_format": "openai",
        "models": ["glm-4-plus", "glm-4-flash", "glm-4-long", "glm-4-air", "glm-4-airx"],
        "placeholder": "...",
        "website": "https://open.bigmodel.cn/usercenter/apikeys",
        "color": "#3366ff",
    },
    {
        "id": "minimax",
        "name": "MiniMax",
        "base_url": "https://api.minimax.chat/v1",
        "api_format": "openai",
        "models": ["MiniMax-Text-01", "abab6.5s-chat", "abab6.5-chat"],
        "placeholder": "your-api-key",
        "website": "https://platform.minimaxi.com/user-center/basic-information/interface-key",
        "color": "#6c5ce7",
    },
    {
        "id": "doubao",
        "name": "Doubao (豆包/火山引擎)",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "api_format": "openai",
        "models": ["doubao-1.5-pro-256k", "doubao-1.5-lite-32k", "doubao-pro-256k"],
        "placeholder": "your-api-key",
        "website": "https://console.volcengine.com/ark/region:ark+cn-beijing/apiKey",
        "color": "#00b4d8",
    },
]


# ── In-memory store (persisted to .env by frontend) ─────────────────────────

_configured_providers: dict[str, dict[str, Any]] = {}


class ProviderConfig(BaseModel):
    provider_id: str
    name: str | None = None
    api_key: str = ""
    base_url: str | None = None
    model: str | None = None
    api_format: str = "openai"  # "openai" or "anthropic"
    enabled: bool = True


class ProviderTestRequest(BaseModel):
    base_url: str
    api_key: str
    api_format: str = "openai"
    model: str | None = None


class ProviderTestResponse(BaseModel):
    ok: bool
    latency_ms: int = 0
    models_available: list[str] = []
    error: str | None = None


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/presets")
async def list_presets() -> list[dict[str, Any]]:
    """Return all available provider presets."""
    return PROVIDER_PRESETS


@router.get("")
async def list_configured() -> list[dict[str, Any]]:
    """Return all configured providers with their settings."""
    result = []
    for preset in PROVIDER_PRESETS:
        pid = preset["id"]
        config = _configured_providers.get(pid, {})
        result.append({
            **preset,
            "configured": bool(config.get("api_key")),
            "api_key_set": bool(config.get("api_key")),
            "active_model": config.get("model") or (preset["models"][0] if preset["models"] else ""),
            "enabled": config.get("enabled", True),
        })
    # Add custom providers
    for pid, config in _configured_providers.items():
        if pid not in {p["id"] for p in PROVIDER_PRESETS}:
            result.append({
                "id": pid,
                "name": config.get("name", pid),
                "base_url": config.get("base_url", ""),
                "api_format": config.get("api_format", "openai"),
                "models": [],
                "configured": bool(config.get("api_key")),
                "api_key_set": bool(config.get("api_key")),
                "active_model": config.get("model", ""),
                "enabled": config.get("enabled", True),
                "color": "#888",
                "custom": True,
            })
    return result


@router.post("")
async def save_provider(config: ProviderConfig) -> dict[str, str]:
    """Save or update a provider configuration."""
    _configured_providers[config.provider_id] = config.model_dump()
    return {"status": "ok", "provider_id": config.provider_id}


@router.delete("/{provider_id}")
async def delete_provider(provider_id: str) -> dict[str, str]:
    """Remove a provider configuration."""
    _configured_providers.pop(provider_id, None)
    return {"status": "ok"}


@router.post("/test", response_model=ProviderTestResponse)
async def test_provider(req: ProviderTestRequest) -> ProviderTestResponse:
    """Test a provider connection by fetching available models."""
    base_url = req.base_url.rstrip("/")
    headers: dict[str, str] = {"Authorization": f"Bearer {req.api_key}"}

    # For native Anthropic format
    if req.api_format == "anthropic":
        headers = {
            "x-api-key": req.api_key,
            "anthropic-version": "2023-06-01",
        }
        models_url = f"{base_url}/models"
    else:
        models_url = f"{base_url}/models"

    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(models_url, headers=headers)
            latency = int((time.monotonic() - start) * 1000)

            if resp.status_code == 200:
                data = resp.json()
                models = []
                if isinstance(data, dict) and "data" in data:
                    models = [m.get("id", "") for m in data["data"] if isinstance(m, dict)]
                elif isinstance(data, list):
                    models = [m.get("id", "") if isinstance(m, dict) else str(m) for m in data]

                return ProviderTestResponse(
                    ok=True,
                    latency_ms=latency,
                    models_available=sorted(models)[:50],
                )
            else:
                # Try a minimal chat completion as fallback
                if req.model:
                    return await _test_chat_completion(req, base_url, headers)
                return ProviderTestResponse(
                    ok=False,
                    latency_ms=latency,
                    error=f"HTTP {resp.status_code}: {resp.text[:200]}",
                )
    except httpx.ConnectError:
        return ProviderTestResponse(ok=False, error="Connection failed — check base URL")
    except httpx.TimeoutException:
        return ProviderTestResponse(ok=False, error="Timeout — server did not respond in 15s")
    except Exception as e:
        return ProviderTestResponse(ok=False, error=str(e)[:200])


async def _test_chat_completion(
    req: ProviderTestRequest,
    base_url: str,
    headers: dict[str, str],
) -> ProviderTestResponse:
    """Fallback: send a minimal chat completion to verify the key works."""
    url = f"{base_url}/chat/completions"
    body = {
        "model": req.model,
        "messages": [{"role": "user", "content": "Say 'ok'"}],
        "max_tokens": 5,
    }
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, headers=headers, json=body)
            latency = int((time.monotonic() - start) * 1000)
            if resp.status_code == 200:
                return ProviderTestResponse(ok=True, latency_ms=latency)
            return ProviderTestResponse(
                ok=False,
                latency_ms=latency,
                error=f"HTTP {resp.status_code}: {resp.text[:200]}",
            )
    except Exception as e:
        return ProviderTestResponse(ok=False, error=str(e)[:200])
