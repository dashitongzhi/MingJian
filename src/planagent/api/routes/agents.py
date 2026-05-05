"""智能体管理 API 路由"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from planagent.services.agent_registry import get_agent_registry, reset_agent_registry

router = APIRouter(prefix="/agents", tags=["agents"])


# ── 请求模型 ──────────────────────────────────────────────


class ApiKeyInput(BaseModel):
    api_key: str
    provider_type: str = "openai"
    base_url: str = ""
    model: str = ""


class ConfigureRequest(BaseModel):
    keys: list[ApiKeyInput]


# ── 端点 ──────────────────────────────────────────────────


@router.get("")
async def list_agents():
    """列出所有 9 个智能体及其状态"""
    registry = get_agent_registry()
    return registry.get_status()


@router.get("/status")
async def agent_status():
    """获取智能体注册中心状态"""
    registry = get_agent_registry()
    return registry.get_status()


@router.post("/configure")
async def configure_agents(req: ConfigureRequest):
    """一键配置 — 自动分配 API Key 到 9 个智能体"""
    registry = get_agent_registry()
    registry.distribute_keys([k.model_dump() for k in req.keys])
    return registry.get_status()


@router.post("/reset")
async def reset_agents():
    """重置所有智能体配置"""
    registry = reset_agent_registry()
    return registry.get_status()
