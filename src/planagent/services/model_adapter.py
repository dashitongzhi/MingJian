"""模型自适应策略模块 — 根据模型能力动态调整辩论参数

功能:
- 评估模型能力（token限制、推理能力、专注领域）
- 动态调整辩论轮次（简单模型3轮，强模型5轮）
- 根据模型token限制调整最长输出
- 根据模型专注领域调整Agent分配策略
- 允许用户手动覆盖自动检测
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from planagent.services.agent_registry import AgentRole

logger = logging.getLogger(__name__)


# ── 模型能力等级 ────────────────────────────────────────────────


class ModelTier(str, Enum):
    """模型能力等级"""
    BASIC = "basic"           # 基础模型 (如 gpt-3.5-turbo, deepseek-chat)
    STANDARD = "standard"     # 标准模型 (如 gpt-4o-mini, claude-haiku)
    ADVANCED = "advanced"     # 高级模型 (如 gpt-4o, claude-sonnet-4, gemini-2.5-pro)


class DomainStrength(str, Enum):
    """模型专注领域"""
    GENERAL = "general"
    REASONING = "reasoning"
    CREATIVE = "creative"
    CODE = "code"
    MULTILINGUAL = "multilingual"


@dataclass(frozen=True)
class ModelCapabilities:
    """模型能力评估结果"""
    model_id: str
    tier: ModelTier
    context_window: int          # 上下文窗口大小
    max_output_tokens: int       # 最大输出token数
    reasoning_score: float       # 推理能力评分 0-1
    domain_strength: DomainStrength
    supports_json: bool          # 是否原生支持JSON模式
    supports_function_calling: bool
    estimated_latency_ms: int    # 预估延迟
    detail: str = ""             # 评估说明


@dataclass(frozen=True)
class DebateAdaptation:
    """辩论参数自适应结果"""
    max_output_tokens: int       # 每轮最大输出token
    total_rounds: int            # 辩论总轮次
    max_arguments: int           # 每轮最大论证数
    agent_filter: list[str] | None = None  # 建议启用的Agent角色
    skip_agents: list[str] | None = None   # 建议跳过的Agent角色
    detail: str = ""


@dataclass
class ModelSettings:
    """用户自定义模型设置（覆盖自动检测）"""
    tier: ModelTier | None = None
    max_output_tokens: int | None = None
    total_rounds: int | None = None
    max_arguments: int | None = None
    enabled_agent_roles: list[str] | None = None
    disabled_agent_roles: list[str] | None = None


# ── 模型数据库 ─────────────────────────────────────────────────


# 已知模型的能力数据
_MODEL_DB: dict[str, dict[str, Any]] = {
    # ── OpenAI 系列 ──────────────
    "gpt-4o": {
        "tier": ModelTier.ADVANCED,
        "context_window": 128000,
        "max_output_tokens": 16384,
        "reasoning_score": 0.92,
        "domain_strength": DomainStrength.GENERAL,
        "supports_json": True,
        "supports_function_calling": True,
        "estimated_latency_ms": 2000,
    },
    "gpt-4o-mini": {
        "tier": ModelTier.STANDARD,
        "context_window": 128000,
        "max_output_tokens": 16384,
        "reasoning_score": 0.78,
        "domain_strength": DomainStrength.GENERAL,
        "supports_json": True,
        "supports_function_calling": True,
        "estimated_latency_ms": 1200,
    },
    "gpt-4-turbo": {
        "tier": ModelTier.ADVANCED,
        "context_window": 128000,
        "max_output_tokens": 4096,
        "reasoning_score": 0.88,
        "domain_strength": DomainStrength.GENERAL,
        "supports_json": True,
        "supports_function_calling": True,
        "estimated_latency_ms": 3000,
    },
    "gpt-3.5-turbo": {
        "tier": ModelTier.BASIC,
        "context_window": 16385,
        "max_output_tokens": 4096,
        "reasoning_score": 0.55,
        "domain_strength": DomainStrength.GENERAL,
        "supports_json": True,
        "supports_function_calling": True,
        "estimated_latency_ms": 800,
    },
    "o1": {
        "tier": ModelTier.ADVANCED,
        "context_window": 200000,
        "max_output_tokens": 100000,
        "reasoning_score": 0.97,
        "domain_strength": DomainStrength.REASONING,
        "supports_json": True,
        "supports_function_calling": True,
        "estimated_latency_ms": 8000,
    },
    "o3": {
        "tier": ModelTier.ADVANCED,
        "context_window": 200000,
        "max_output_tokens": 100000,
        "reasoning_score": 0.98,
        "domain_strength": DomainStrength.REASONING,
        "supports_json": True,
        "supports_function_calling": True,
        "estimated_latency_ms": 10000,
    },
    "o3-mini": {
        "tier": ModelTier.STANDARD,
        "context_window": 200000,
        "max_output_tokens": 100000,
        "reasoning_score": 0.85,
        "domain_strength": DomainStrength.REASONING,
        "supports_json": True,
        "supports_function_calling": True,
        "estimated_latency_ms": 5000,
    },
    # ── Anthropic 系列 ──────────────
    "claude-sonnet-4": {
        "tier": ModelTier.ADVANCED,
        "context_window": 200000,
        "max_output_tokens": 8192,
        "reasoning_score": 0.94,
        "domain_strength": DomainStrength.REASONING,
        "supports_json": True,
        "supports_function_calling": True,
        "estimated_latency_ms": 3000,
    },
    "claude-haiku-3.5": {
        "tier": ModelTier.STANDARD,
        "context_window": 200000,
        "max_output_tokens": 8192,
        "reasoning_score": 0.80,
        "domain_strength": DomainStrength.GENERAL,
        "supports_json": True,
        "supports_function_calling": True,
        "estimated_latency_ms": 1000,
    },
    "claude-opus-4": {
        "tier": ModelTier.ADVANCED,
        "context_window": 200000,
        "max_output_tokens": 32000,
        "reasoning_score": 0.96,
        "domain_strength": DomainStrength.REASONING,
        "supports_json": True,
        "supports_function_calling": True,
        "estimated_latency_ms": 5000,
    },
    # ── Google 系列 ──────────────
    "gemini-2.5-pro": {
        "tier": ModelTier.ADVANCED,
        "context_window": 1000000,
        "max_output_tokens": 65536,
        "reasoning_score": 0.93,
        "domain_strength": DomainStrength.GENERAL,
        "supports_json": True,
        "supports_function_calling": True,
        "estimated_latency_ms": 2500,
    },
    "gemini-2.5-flash": {
        "tier": ModelTier.STANDARD,
        "context_window": 1000000,
        "max_output_tokens": 65536,
        "reasoning_score": 0.82,
        "domain_strength": DomainStrength.GENERAL,
        "supports_json": True,
        "supports_function_calling": True,
        "estimated_latency_ms": 1000,
    },
    # ── DeepSeek 系列 ──────────────
    "deepseek-chat": {
        "tier": ModelTier.STANDARD,
        "context_window": 64000,
        "max_output_tokens": 8192,
        "reasoning_score": 0.75,
        "domain_strength": DomainStrength.GENERAL,
        "supports_json": True,
        "supports_function_calling": True,
        "estimated_latency_ms": 2000,
    },
    "deepseek-reasoner": {
        "tier": ModelTier.ADVANCED,
        "context_window": 64000,
        "max_output_tokens": 8192,
        "reasoning_score": 0.90,
        "domain_strength": DomainStrength.REASONING,
        "supports_json": True,
        "supports_function_calling": False,
        "estimated_latency_ms": 8000,
    },
    # ── Qwen 系列 ──────────────
    "qwen-max": {
        "tier": ModelTier.ADVANCED,
        "context_window": 32000,
        "max_output_tokens": 8192,
        "reasoning_score": 0.85,
        "domain_strength": DomainStrength.MULTILINGUAL,
        "supports_json": True,
        "supports_function_calling": True,
        "estimated_latency_ms": 2000,
    },
    "qwen-plus": {
        "tier": ModelTier.STANDARD,
        "context_window": 131072,
        "max_output_tokens": 8192,
        "reasoning_score": 0.78,
        "domain_strength": DomainStrength.MULTILINGUAL,
        "supports_json": True,
        "supports_function_calling": True,
        "estimated_latency_ms": 1500,
    },
    # ── MiMo 系列 ──────────────
    "mimo-v2.5-pro": {
        "tier": ModelTier.STANDARD,
        "context_window": 128000,
        "max_output_tokens": 16384,
        "reasoning_score": 0.82,
        "domain_strength": DomainStrength.REASONING,
        "supports_json": True,
        "supports_function_calling": True,
        "estimated_latency_ms": 2000,
    },
}

# 默认未知模型的能力（按标准模型估计）
_DEFAULT_CAPABILITIES: dict[str, Any] = {
    "tier": ModelTier.STANDARD,
    "context_window": 32000,
    "max_output_tokens": 4096,
    "reasoning_score": 0.70,
    "domain_strength": DomainStrength.GENERAL,
    "supports_json": True,
    "supports_function_calling": False,
    "estimated_latency_ms": 3000,
}

# 模型名称模式匹配（用于未直接注册的模型变体）
_MODEL_PATTERNS: list[tuple[str, dict[str, Any]]] = [
    # gpt-4o-2024-xx-xx 等变体
    (r"gpt-4o", {"tier": ModelTier.ADVANCED, "reasoning_score": 0.92, "context_window": 128000, "max_output_tokens": 16384}),
    (r"gpt-4-turbo", {"tier": ModelTier.ADVANCED, "reasoning_score": 0.88, "context_window": 128000, "max_output_tokens": 4096}),
    (r"gpt-4[^o]", {"tier": ModelTier.ADVANCED, "reasoning_score": 0.85, "context_window": 8192, "max_output_tokens": 4096}),
    (r"gpt-3\.5", {"tier": ModelTier.BASIC, "reasoning_score": 0.55, "context_window": 16385, "max_output_tokens": 4096}),
    (r"o1[-_]", {"tier": ModelTier.ADVANCED, "reasoning_score": 0.97, "context_window": 200000, "max_output_tokens": 100000}),
    (r"o3[-_]", {"tier": ModelTier.ADVANCED, "reasoning_score": 0.97, "context_window": 200000, "max_output_tokens": 100000}),
    (r"claude.*opus", {"tier": ModelTier.ADVANCED, "reasoning_score": 0.96, "context_window": 200000, "max_output_tokens": 32000}),
    (r"claude.*sonnet", {"tier": ModelTier.ADVANCED, "reasoning_score": 0.94, "context_window": 200000, "max_output_tokens": 8192}),
    (r"claude.*haiku", {"tier": ModelTier.STANDARD, "reasoning_score": 0.80, "context_window": 200000, "max_output_tokens": 8192}),
    (r"gemini.*pro", {"tier": ModelTier.ADVANCED, "reasoning_score": 0.93, "context_window": 1000000, "max_output_tokens": 65536}),
    (r"gemini.*flash", {"tier": ModelTier.STANDARD, "reasoning_score": 0.82, "context_window": 1000000, "max_output_tokens": 65536}),
    (r"deepseek.*reason", {"tier": ModelTier.ADVANCED, "reasoning_score": 0.90, "context_window": 64000, "max_output_tokens": 8192}),
    (r"deepseek", {"tier": ModelTier.STANDARD, "reasoning_score": 0.75, "context_window": 64000, "max_output_tokens": 8192}),
    (r"qwen.*max", {"tier": ModelTier.ADVANCED, "reasoning_score": 0.85, "context_window": 32000, "max_output_tokens": 8192}),
    (r"qwen", {"tier": ModelTier.STANDARD, "reasoning_score": 0.78, "context_window": 131072, "max_output_tokens": 8192}),
    (r"mimo", {"tier": ModelTier.STANDARD, "reasoning_score": 0.82, "context_window": 128000, "max_output_tokens": 16384}),
    (r"llama", {"tier": ModelTier.BASIC, "reasoning_score": 0.60, "context_window": 8192, "max_output_tokens": 4096}),
    (r"mistral", {"tier": ModelTier.STANDARD, "reasoning_score": 0.72, "context_window": 32000, "max_output_tokens": 8192}),
]


# ── 核心服务 ────────────────────────────────────────────────────


class ModelAdapterService:
    """模型自适应服务 — 评估模型能力并动态调整辩论参数"""

    def __init__(self) -> None:
        # 用户覆盖设置（内存级，重启后恢复自动检测）
        self._user_settings: ModelSettings = ModelSettings()
        # 模型能力缓存
        self._capabilities_cache: dict[str, ModelCapabilities] = {}

    # ── 能力评估 ──────────────────────────────────────────

    def assess_model(self, model_id: str) -> ModelCapabilities:
        """评估指定模型的能力

        Args:
            model_id: 模型标识（如 "gpt-4o", "claude-sonnet-4-20250514"）

        Returns:
            ModelCapabilities 评估结果
        """
        # 清理模型名称用于查找
        normalized = self._normalize_model_id(model_id)

        # 先查精确匹配缓存
        if normalized in self._capabilities_cache:
            return self._capabilities_cache[normalized]

        # 查精确匹配数据库
        if normalized in _MODEL_DB:
            caps = self._build_capabilities(normalized, _MODEL_DB[normalized])
            self._capabilities_cache[normalized] = caps
            return caps

        # 尝试去版本号后匹配
        base_name = re.sub(r"[-_]\d{8}$", "", normalized)  # 去掉 20250514 这类日期后缀
        base_name = re.sub(r"[-_]v\d+(\.\d+)*$", "", base_name)  # 去掉 v2.5 等版本后缀
        if base_name in _MODEL_DB:
            caps = self._build_capabilities(normalized, _MODEL_DB[base_name])
            self._capabilities_cache[normalized] = caps
            return caps

        # 使用模式匹配
        for pattern, overrides in _MODEL_PATTERNS:
            if re.search(pattern, normalized, re.IGNORECASE):
                data = {**_DEFAULT_CAPABILITIES, **overrides}
                caps = self._build_capabilities(normalized, data)
                self._capabilities_cache[normalized] = caps
                return caps

        # 使用默认值
        caps = self._build_capabilities(normalized, {**_DEFAULT_CAPABILITIES})
        caps = ModelCapabilities(
            model_id=caps.model_id,
            tier=caps.tier,
            context_window=caps.context_window,
            max_output_tokens=caps.max_output_tokens,
            reasoning_score=caps.reasoning_score,
            domain_strength=caps.domain_strength,
            supports_json=caps.supports_json,
            supports_function_calling=caps.supports_function_calling,
            estimated_latency_ms=caps.estimated_latency_ms,
            detail=f"模型 '{model_id}' 未在数据库中，使用默认标准模型参数评估",
        )
        self._capabilities_cache[normalized] = caps
        return caps

    def assess_debate_models(
        self,
        advocate_model: str | None = None,
        challenger_model: str | None = None,
        arbitrator_model: str | None = None,
    ) -> dict[str, ModelCapabilities]:
        """评估辩论中使用的各模型的能力"""
        result: dict[str, ModelCapabilities] = {}
        if advocate_model:
            result["advocate"] = self.assess_model(advocate_model)
        if challenger_model:
            result["challenger"] = self.assess_model(challenger_model)
        if arbitrator_model:
            result["arbitrator"] = self.assess_model(arbitrator_model)
        return result

    # ── 辩论参数自适应 ────────────────────────────────────

    def compute_debate_adaptation(
        self,
        advocate_model: str | None = None,
        challenger_model: str | None = None,
        arbitrator_model: str | None = None,
    ) -> DebateAdaptation:
        """根据各模型能力计算辩论参数的自适应调整

        策略:
        - token限制 → 调整最长输出
        - 推理能力 → 调整辩论轮次（简单模型3轮，强模型5轮）
        - 模型专注领域 → 调整Agent分配策略

        Returns:
            DebateAdaptation 调整后的辩论参数
        """
        # 应用用户覆盖
        user = self._user_settings

        # 评估各模型
        caps = self.assess_debate_models(advocate_model, challenger_model, arbitrator_model)

        if not caps:
            # 没有检测到任何模型，使用保守默认值
            return DebateAdaptation(
                max_output_tokens=user.max_output_tokens or 1000,
                total_rounds=user.total_rounds or 4,
                max_arguments=user.max_arguments or 3,
                detail="未检测到辩论模型，使用默认参数",
            )

        # 取最低能力的模型作为瓶颈
        min_max_tokens = min(c.max_output_tokens for c in caps.values())
        min_reasoning = min(c.reasoning_score for c in caps.values())

        # ── 调整最大输出token ──────────────────────────────
        if user.max_output_tokens:
            max_tokens = user.max_output_tokens
        else:
            # 根据最小max_output_tokens调整，但不超过2000
            # 最低不少于500
            max_tokens = max(500, min(min_max_tokens // 4, 2000))

        # ── 调整辩论轮次 ──────────────────────────────────
        if user.total_rounds:
            total_rounds = user.total_rounds
        else:
            if min_reasoning >= 0.90:
                # 强推理模型：5轮（增加深度质询和总结）
                total_rounds = 5
            elif min_reasoning >= 0.75:
                # 标准模型：4轮（当前默认）
                total_rounds = 4
            else:
                # 简单模型：3轮（跳过修订，直接仲裁）
                total_rounds = 3

        # ── 调整每轮论证数 ────────────────────────────────
        if user.max_arguments:
            max_arguments = user.max_arguments
        else:
            if min_max_tokens >= 8000:
                max_arguments = 3
            elif min_max_tokens >= 4000:
                max_arguments = 2
            else:
                max_arguments = 1

        # ── Agent分配策略 ─────────────────────────────────
        agent_filter = user.enabled_agent_roles
        skip_agents = user.disabled_agent_roles
        if not agent_filter and not skip_agents:
            if total_rounds <= 3:
                # 简化模式：只保留核心角色
                skip_agents = [
                    "intel_analyst", "geo_expert", "econ_analyst",
                    "military_strategist", "tech_foresight", "social_impact",
                ]

        # 构建说明
        model_names = [c.model_id for c in caps.values()]
        tier_names = list({c.tier.value for c in caps.values()})
        detail_parts = [
            f"评估模型: {', '.join(model_names)}",
            f"能力等级: {', '.join(tier_names)}",
            f"最低推理分: {min_reasoning:.2f}",
            f"最低输出限制: {min_max_tokens} tokens",
            f"→ 输出上限: {max_tokens} tokens",
            f"→ 辩论轮次: {total_rounds}",
            f"→ 每轮论证: {max_arguments}",
        ]
        if skip_agents:
            detail_parts.append(f"→ 跳过角色: {', '.join(skip_agents)}")

        return DebateAdaptation(
            max_output_tokens=max_tokens,
            total_rounds=total_rounds,
            max_arguments=max_arguments,
            agent_filter=agent_filter,
            skip_agents=skip_agents,
            detail=" | ".join(detail_parts),
        )

    # ── 用户设置 ──────────────────────────────────────────

    def get_user_settings(self) -> dict[str, Any]:
        """获取当前用户覆盖设置"""
        s = self._user_settings
        return {
            "tier_override": s.tier.value if s.tier else None,
            "max_output_tokens_override": s.max_output_tokens,
            "total_rounds_override": s.total_rounds,
            "max_arguments_override": s.max_arguments,
            "enabled_agent_roles": s.enabled_agent_roles,
            "disabled_agent_roles": s.disabled_agent_roles,
        }

    def update_user_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        """更新用户覆盖设置

        Args:
            settings: 需要覆盖的设置字典，None值表示使用自动检测

        Returns:
            更新后的设置字典
        """
        current = self._user_settings

        if "tier_override" in settings:
            tier_val = settings["tier_override"]
            if tier_val is None:
                current = ModelSettings(
                    tier=None,
                    max_output_tokens=current.max_output_tokens,
                    total_rounds=current.total_rounds,
                    max_arguments=current.max_arguments,
                    enabled_agent_roles=current.enabled_agent_roles,
                    disabled_agent_roles=current.disabled_agent_roles,
                )
            else:
                try:
                    tier = ModelTier(tier_val)
                    current = ModelSettings(
                        tier=tier,
                        max_output_tokens=current.max_output_tokens,
                        total_rounds=current.total_rounds,
                        max_arguments=current.max_arguments,
                        enabled_agent_roles=current.enabled_agent_roles,
                        disabled_agent_roles=current.disabled_agent_roles,
                    )
                except ValueError:
                    pass  # 无效的tier值，忽略

        if "max_output_tokens_override" in settings:
            val = settings["max_output_tokens_override"]
            current = ModelSettings(
                tier=current.tier,
                max_output_tokens=max(100, min(int(val), 32000)) if val is not None else None,
                total_rounds=current.total_rounds,
                max_arguments=current.max_arguments,
                enabled_agent_roles=current.enabled_agent_roles,
                disabled_agent_roles=current.disabled_agent_roles,
            )

        if "total_rounds_override" in settings:
            val = settings["total_rounds_override"]
            current = ModelSettings(
                tier=current.tier,
                max_output_tokens=current.max_output_tokens,
                total_rounds=max(2, min(int(val), 7)) if val is not None else None,
                max_arguments=current.max_arguments,
                enabled_agent_roles=current.enabled_agent_roles,
                disabled_agent_roles=current.disabled_agent_roles,
            )

        if "max_arguments_override" in settings:
            val = settings["max_arguments_override"]
            current = ModelSettings(
                tier=current.tier,
                max_output_tokens=current.max_output_tokens,
                total_rounds=current.total_rounds,
                max_arguments=max(1, min(int(val), 5)) if val is not None else None,
                enabled_agent_roles=current.enabled_agent_roles,
                disabled_agent_roles=current.disabled_agent_roles,
            )

        if "enabled_agent_roles" in settings:
            val = settings["enabled_agent_roles"]
            current = ModelSettings(
                tier=current.tier,
                max_output_tokens=current.max_output_tokens,
                total_rounds=current.total_rounds,
                max_arguments=current.max_arguments,
                enabled_agent_roles=val if isinstance(val, list) else None,
                disabled_agent_roles=current.disabled_agent_roles,
            )

        if "disabled_agent_roles" in settings:
            val = settings["disabled_agent_roles"]
            current = ModelSettings(
                tier=current.tier,
                max_output_tokens=current.max_output_tokens,
                total_rounds=current.total_rounds,
                max_arguments=current.max_arguments,
                enabled_agent_roles=current.enabled_agent_roles,
                disabled_agent_roles=val if isinstance(val, list) else None,
            )

        self._user_settings = current
        self._capabilities_cache.clear()  # 设置变更后清除缓存
        logger.info("模型自适应设置已更新: %s", self.get_user_settings())
        return self.get_user_settings()

    def reset_user_settings(self) -> dict[str, Any]:
        """重置所有用户覆盖设置为自动检测"""
        self._user_settings = ModelSettings()
        self._capabilities_cache.clear()
        logger.info("模型自适应设置已重置为自动检测")
        return self.get_user_settings()

    # ── 内部方法 ──────────────────────────────────────────

    @staticmethod
    def _normalize_model_id(model_id: str) -> str:
        """标准化模型名称，去除前缀和后缀"""
        name = model_id.strip().lower()
        # 去除 provider/ 前缀（如 openai/gpt-4o → gpt-4o）
        if "/" in name:
            name = name.split("/")[-1]
        return name

    @staticmethod
    def _build_capabilities(model_id: str, data: dict[str, Any]) -> ModelCapabilities:
        """从字典构建 ModelCapabilities"""
        return ModelCapabilities(
            model_id=model_id,
            tier=data.get("tier", ModelTier.STANDARD),
            context_window=data.get("context_window", 32000),
            max_output_tokens=data.get("max_output_tokens", 4096),
            reasoning_score=data.get("reasoning_score", 0.70),
            domain_strength=data.get("domain_strength", DomainStrength.GENERAL),
            supports_json=data.get("supports_json", True),
            supports_function_calling=data.get("supports_function_calling", False),
            estimated_latency_ms=data.get("estimated_latency_ms", 3000),
        )

    def get_all_known_models(self) -> list[dict[str, Any]]:
        """返回所有已知模型的概要信息"""
        result = []
        for model_id, data in sorted(_MODEL_DB.items()):
            result.append({
                "model_id": model_id,
                "tier": data["tier"].value,
                "context_window": data["context_window"],
                "max_output_tokens": data["max_output_tokens"],
                "reasoning_score": data["reasoning_score"],
                "domain_strength": data["domain_strength"].value,
            })
        return result


# ── 全局单例 ──────────────────────────────────────────────

_model_adapter: ModelAdapterService | None = None


def get_model_adapter() -> ModelAdapterService:
    global _model_adapter
    if _model_adapter is None:
        _model_adapter = ModelAdapterService()
    return _model_adapter


def reset_model_adapter() -> ModelAdapterService:
    global _model_adapter
    _model_adapter = ModelAdapterService()
    return _model_adapter
