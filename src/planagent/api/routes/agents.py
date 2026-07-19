"""智能体管理 API 路由"""

from __future__ import annotations

from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from planagent.api.routes.auth import require_role
from planagent.services.auth import UserRole
from planagent.services.agent_registry import get_agent_registry, reset_agent_registry

router = APIRouter(prefix="/agents", tags=["agents"])


# ── 请求模型 ──────────────────────────────────────────────


class ApiKeyInput(BaseModel):
    api_key: str = Field(min_length=1, max_length=8192)
    provider_type: Literal["openai", "anthropic"] = "openai"
    base_url: str = Field(default="", max_length=2048)
    model: str = Field(default="", max_length=200)

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        if not value:
            return value
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or parsed.hostname is None:
            raise ValueError("base_url must be an explicit http(s) URL")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("base_url must not contain credentials")
        if parsed.query or parsed.fragment:
            raise ValueError("base_url must not contain a query or fragment")
        try:
            _ = parsed.port
        except ValueError as exc:
            raise ValueError("base_url must have a valid port") from exc
        return value.rstrip("/")


class ConfigureRequest(BaseModel):
    keys: list[ApiKeyInput] = Field(min_length=1, max_length=32)


class ModelOverrideRequest(BaseModel):
    role: str = Field(min_length=1, max_length=64)
    model: str = Field(default="", max_length=200)  # 空字符串 = 恢复系统推荐


# ── 端点 ──────────────────────────────────────────────────


@router.get("")
async def list_agents():
    """列出所有 9 个智能体及其状态"""
    return get_agent_registry().get_status()


@router.get("/status")
async def agent_status():
    """获取智能体注册中心状态"""
    return get_agent_registry().get_status()


@router.post("/configure", dependencies=[Depends(require_role(UserRole.ADMIN))])
async def configure_agents(req: ConfigureRequest):
    """一键配置 — 自动分配 API Key 到 9 个智能体"""
    registry = get_agent_registry()
    registry.distribute_keys([k.model_dump() for k in req.keys])
    return registry.get_status()


@router.post("/model", dependencies=[Depends(require_role(UserRole.ADMIN))])
async def set_model_override(req: ModelOverrideRequest):
    """设置单个智能体的模型选择"""
    registry = get_agent_registry()
    try:
        registry.set_model_override(req.role, req.model)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="Unknown agent role") from exc
    return registry.get_status()


@router.post("/reset", dependencies=[Depends(require_role(UserRole.ADMIN))])
async def reset_agents():
    """重置所有智能体配置"""
    return reset_agent_registry().get_status()
