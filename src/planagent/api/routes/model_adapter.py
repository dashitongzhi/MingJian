"""模型自适应策略 API — 查看模型能力评估和调整辩论参数

端点:
- GET  /model/capabilities  查看当前模型评估
- PUT  /model/settings      允许用户覆盖自动检测
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from planagent.services.model_adapter import get_model_adapter

router = APIRouter(prefix="/model", tags=["Model Adapter"])


# ── 请求/响应模型 ──────────────────────────────────────────────


class ModelAssessRequest(BaseModel):
    """模型能力评估请求"""
    model_id: str = Field(..., description="模型标识（如 gpt-4o, claude-sonnet-4-20250514）")


class ModelCapabilitiesResponse(BaseModel):
    """模型能力评估响应"""
    model_id: str
    tier: str
    context_window: int
    max_output_tokens: int
    reasoning_score: float
    domain_strength: str
    supports_json: bool
    supports_function_calling: bool
    estimated_latency_ms: int
    detail: str = ""


class DebateAdaptationRequest(BaseModel):
    """辩论自适应参数请求"""
    advocate_model: str | None = Field(None, description="支持方模型")
    challenger_model: str | None = Field(None, description="挑战方模型")
    arbitrator_model: str | None = Field(None, description="仲裁方模型")


class DebateAdaptationResponse(BaseModel):
    """辩论自适应参数响应"""
    max_output_tokens: int
    total_rounds: int
    max_arguments: int
    agent_filter: list[str] | None = None
    skip_agents: list[str] | None = None
    detail: str


class ModelSettingsUpdate(BaseModel):
    """用户覆盖设置"""
    tier_override: str | None = Field(
        None,
        description="覆盖模型等级: basic/standard/advanced，null恢复自动检测",
    )
    max_output_tokens_override: int | None = Field(
        None, ge=100, le=32000,
        description="覆盖最大输出token，null恢复自动检测",
    )
    total_rounds_override: int | None = Field(
        None, ge=2, le=7,
        description="覆盖辩论轮次，null恢复自动检测",
    )
    max_arguments_override: int | None = Field(
        None, ge=1, le=5,
        description="覆盖每轮论证数，null恢复自动检测",
    )
    enabled_agent_roles: list[str] | None = Field(
        None,
        description="启用的Agent角色列表，null使用自适应策略",
    )
    disabled_agent_roles: list[str] | None = Field(
        None,
        description="禁用的Agent角色列表，null使用自适应策略",
    )


class ModelSettingsResponse(BaseModel):
    """设置响应"""
    tier_override: str | None = None
    max_output_tokens_override: int | None = None
    total_rounds_override: int | None = None
    max_arguments_override: int | None = None
    enabled_agent_roles: list[str] | None = None
    disabled_agent_roles: list[str] | None = None


class CapabilitiesOverviewResponse(BaseModel):
    """能力总览响应"""
    known_models: list[dict[str, Any]]
    current_settings: dict[str, Any]
    model_count: int


# ── 端点 ───────────────────────────────────────────────────────


@router.get("/capabilities", response_model=CapabilitiesOverviewResponse)
async def get_capabilities() -> CapabilitiesOverviewResponse:
    """查看当前模型能力评估总览

    返回所有已知模型的能力数据和当前用户设置。
    """
    adapter = get_model_adapter()
    return CapabilitiesOverviewResponse(
        known_models=adapter.get_all_known_models(),
        current_settings=adapter.get_user_settings(),
        model_count=len(adapter.get_all_known_models()),
    )


@router.post("/capabilities/assess", response_model=ModelCapabilitiesResponse)
async def assess_model(req: ModelAssessRequest) -> ModelCapabilitiesResponse:
    """评估指定模型的能力

    传入模型ID，返回该模型的详细能力评估。
    """
    adapter = get_model_adapter()
    caps = adapter.assess_model(req.model_id)
    return ModelCapabilitiesResponse(
        model_id=caps.model_id,
        tier=caps.tier.value,
        context_window=caps.context_window,
        max_output_tokens=caps.max_output_tokens,
        reasoning_score=caps.reasoning_score,
        domain_strength=caps.domain_strength.value,
        supports_json=caps.supports_json,
        supports_function_calling=caps.supports_function_calling,
        estimated_latency_ms=caps.estimated_latency_ms,
        detail=caps.detail,
    )


@router.post("/capabilities/adapt", response_model=DebateAdaptationResponse)
async def compute_adaptation(req: DebateAdaptationRequest) -> DebateAdaptationResponse:
    """计算辩论参数的自适应调整

    根据各方模型能力，返回优化后的辩论参数。
    """
    adapter = get_model_adapter()
    adaptation = adapter.compute_debate_adaptation(
        advocate_model=req.advocate_model,
        challenger_model=req.challenger_model,
        arbitrator_model=req.arbitrator_model,
    )
    return DebateAdaptationResponse(
        max_output_tokens=adaptation.max_output_tokens,
        total_rounds=adaptation.total_rounds,
        max_arguments=adaptation.max_arguments,
        agent_filter=adaptation.agent_filter,
        skip_agents=adaptation.skip_agents,
        detail=adaptation.detail,
    )


@router.get("/settings", response_model=ModelSettingsResponse)
async def get_settings() -> ModelSettingsResponse:
    """获取当前用户覆盖设置"""
    adapter = get_model_adapter()
    s = adapter.get_user_settings()
    return ModelSettingsResponse(**s)


@router.put("/settings", response_model=ModelSettingsResponse)
async def update_settings(req: ModelSettingsUpdate) -> ModelSettingsResponse:
    """更新用户覆盖设置

    传入需要覆盖的参数，null值表示使用自动检测。
    """
    adapter = get_model_adapter()
    try:
        settings_dict = req.model_dump(exclude_none=False)
        updated = adapter.update_user_settings(settings_dict)
        return ModelSettingsResponse(**updated)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/settings", response_model=ModelSettingsResponse)
async def reset_settings() -> ModelSettingsResponse:
    """重置所有用户覆盖设置为自动检测"""
    adapter = get_model_adapter()
    s = adapter.reset_user_settings()
    return ModelSettingsResponse(**s)
