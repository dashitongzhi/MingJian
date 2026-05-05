"""智能体注册中心 — 管理9个智能体的生命周期和API Key分配"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AgentRole(str, Enum):
    """9个智能体角色"""

    ADVOCATE = "advocate"
    CHALLENGER = "challenger"
    ARBITRATOR = "arbitrator"
    EVIDENCE_ASSESSOR = "evidence_assessor"
    GEOPOLITICAL = "geopolitical"
    ECONOMIC = "economic"
    MILITARY = "military"
    TECH = "tech"
    SOCIAL = "social"


# 按重要性排序的角色列表
_ROLE_PRIORITY: list[AgentRole] = [
    AgentRole.ADVOCATE,
    AgentRole.CHALLENGER,
    AgentRole.ARBITRATOR,
    AgentRole.EVIDENCE_ASSESSOR,
    AgentRole.GEOPOLITICAL,
    AgentRole.ECONOMIC,
    AgentRole.MILITARY,
    AgentRole.TECH,
    AgentRole.SOCIAL,
]

# 每个角色的推荐模型
_RECOMMENDED_MODELS: dict[AgentRole, list[str]] = {
    AgentRole.ADVOCATE:           ["gpt-4o", "claude-sonnet-4", "deepseek-chat"],
    AgentRole.CHALLENGER:         ["claude-sonnet-4", "gpt-4o", "deepseek-chat"],
    AgentRole.ARBITRATOR:         ["gpt-4o", "claude-sonnet-4", "gemini-2.5-pro"],
    AgentRole.EVIDENCE_ASSESSOR:  ["gpt-4o-mini", "claude-haiku", "deepseek-chat"],
    AgentRole.GEOPOLITICAL:       ["gpt-4o", "claude-sonnet-4", "gemini-2.5-pro"],
    AgentRole.ECONOMIC:           ["gpt-4o", "deepseek-chat", "claude-sonnet-4"],
    AgentRole.MILITARY:           ["gpt-4o", "claude-sonnet-4", "deepseek-chat"],
    AgentRole.TECH:               ["gpt-4o", "claude-sonnet-4", "gemini-2.5-pro"],
    AgentRole.SOCIAL:             ["gpt-4o-mini", "claude-haiku", "deepseek-chat"],
}


@dataclass
class AgentConfig:
    """单个智能体配置"""

    role: AgentRole
    name: str
    name_en: str
    icon: str
    description: str
    recommended_models: list[str] = field(default_factory=list)
    model_override: str = ""  # 用户自选模型，空=使用系统推荐
    provider_type: str = ""
    api_key: str = ""
    base_url: str = ""
    model: str = ""  # 实际使用的模型（分配后填入）
    priority: int = 1  # 1=核心辩论角色, 2=视角分析角色


DEFAULT_AGENTS: list[AgentConfig] = [
    AgentConfig(
        role=AgentRole.ADVOCATE,
        name="战略支持者",
        name_en="Strategic Advocate",
        icon="🟢",
        description="正面论证，寻找支持证据",
        recommended_models=_RECOMMENDED_MODELS[AgentRole.ADVOCATE],
        priority=1,
    ),
    AgentConfig(
        role=AgentRole.CHALLENGER,
        name="风险挑战者",
        name_en="Risk Challenger",
        icon="🔴",
        description="反面论证，寻找风险漏洞",
        recommended_models=_RECOMMENDED_MODELS[AgentRole.CHALLENGER],
        priority=1,
    ),
    AgentConfig(
        role=AgentRole.ARBITRATOR,
        name="首席仲裁官",
        name_en="Chief Arbitrator",
        icon="⚖️",
        description="综合评判，出最终裁决",
        recommended_models=_RECOMMENDED_MODELS[AgentRole.ARBITRATOR],
        priority=1,
    ),
    AgentConfig(
        role=AgentRole.EVIDENCE_ASSESSOR,
        name="情报分析师",
        name_en="Intelligence Analyst",
        icon="🔍",
        description="分析搜集到的证据质量",
        recommended_models=_RECOMMENDED_MODELS[AgentRole.EVIDENCE_ASSESSOR],
        priority=2,
    ),
    AgentConfig(
        role=AgentRole.GEOPOLITICAL,
        name="地缘政治专家",
        name_en="Geopolitical Expert",
        icon="🌍",
        description="地缘政治视角分析",
        recommended_models=_RECOMMENDED_MODELS[AgentRole.GEOPOLITICAL],
        priority=2,
    ),
    AgentConfig(
        role=AgentRole.ECONOMIC,
        name="经济分析师",
        name_en="Economic Analyst",
        icon="💰",
        description="经济/市场视角分析",
        recommended_models=_RECOMMENDED_MODELS[AgentRole.ECONOMIC],
        priority=2,
    ),
    AgentConfig(
        role=AgentRole.MILITARY,
        name="军事战略家",
        name_en="Military Strategist",
        icon="⚔️",
        description="军事/安全视角分析",
        recommended_models=_RECOMMENDED_MODELS[AgentRole.MILITARY],
        priority=2,
    ),
    AgentConfig(
        role=AgentRole.TECH,
        name="技术前瞻者",
        name_en="Tech Forecaster",
        icon="🔮",
        description="技术趋势视角分析",
        recommended_models=_RECOMMENDED_MODELS[AgentRole.TECH],
        priority=2,
    ),
    AgentConfig(
        role=AgentRole.SOCIAL,
        name="社会影响评估师",
        name_en="Social Impact Assessor",
        icon="👥",
        description="社会/舆论视角分析",
        recommended_models=_RECOMMENDED_MODELS[AgentRole.SOCIAL],
        priority=2,
    ),
]


class AgentRegistry:
    """智能体注册中心 — 管理9个智能体"""

    def __init__(self) -> None:
        self._agents: dict[AgentRole, AgentConfig] = {
            a.role: AgentConfig(**{**a.__dict__}) for a in DEFAULT_AGENTS
        }
        # 备用 key 池（当 key 数量 > 9 时）
        self._spare_keys: list[dict[str, str]] = []

    # ── 查询 ──────────────────────────────────────────────

    def get_agent(self, role: AgentRole) -> AgentConfig:
        return self._agents[role]

    def get_all_agents(self) -> list[AgentConfig]:
        return [self._agents[r] for r in _ROLE_PRIORITY]

    def get_provider_config(self, role: AgentRole) -> dict[str, str]:
        """获取指定角色的 provider 配置，用于 LLM 调用"""
        a = self._agents[role]
        effective_model = a.model_override or a.model
        return {
            "provider_type": a.provider_type,
            "api_key": a.api_key,
            "base_url": a.base_url,
            "model": effective_model,
        }

    # ── 更新 ──────────────────────────────────────────────

    def update_agent(self, role: AgentRole, **kwargs: object) -> None:
        agent = self._agents[role]
        for k, v in kwargs.items():
            if hasattr(agent, k):
                setattr(agent, k, v)

    def set_model_override(self, role: AgentRole, model: str) -> None:
        """设置用户自选模型（空字符串=恢复系统推荐）"""
        self._agents[role].model_override = model

    # ── API Key 分配 ──────────────────────────────────────

    def distribute_keys(self, keys: list[dict[str, str]]) -> None:
        """自动分配 API Key — 按角色优先级

        keys 格式::

            [{"api_key": "sk-xxx", "provider_type": "openai",
              "base_url": "...", "model": "..."}]

        分配策略:
        * 1 key  → 全部 9 个 agent
        * 2 key  → key1 = 核心 3, key2 = 视角 6
        * 3 key  → key1 = 核心 3, key2 = 视角前 3, key3 = 视角后 3
        * 4-8 key → 核心 3 各独占 1 key, 剩余 key 分给视角 6
        * 9+ key → 每个 agent 独占 1 key, 多余存入 spare 池
        """
        if not keys:
            return

        self._spare_keys = []
        agents = self.get_all_agents()  # 按优先级排序
        core = [a for a in agents if a.priority == 1]       # 3 个
        perspective = [a for a in agents if a.priority == 2]  # 6 个

        n = len(keys)

        if n == 1:
            for agent in agents:
                self._apply_key(agent, keys[0])

        elif n == 2:
            for agent in core:
                self._apply_key(agent, keys[0])
            for agent in perspective:
                self._apply_key(agent, keys[1])

        elif n == 3:
            for agent in core:
                self._apply_key(agent, keys[0])
            for agent in perspective[:3]:
                self._apply_key(agent, keys[1])
            for agent in perspective[3:]:
                self._apply_key(agent, keys[2])

        elif n <= 8:
            # 核心 3 各独占 1 key
            for i, agent in enumerate(core):
                self._apply_key(agent, keys[i])
            # 剩余 key 分给视角 6
            remaining = keys[3:]
            for i, agent in enumerate(perspective):
                self._apply_key(agent, remaining[i % len(remaining)])

        else:
            # 9+ key: 每个 agent 独占 1 key
            for i, agent in enumerate(agents):
                self._apply_key(agent, keys[i])
            self._spare_keys = keys[9:]

    @staticmethod
    def _apply_key(agent: AgentConfig, key: dict[str, str]) -> None:
        agent.provider_type = key.get("provider_type", "openai")
        agent.api_key = key["api_key"]
        agent.base_url = key.get("base_url", "")
        # 如果用户没有设置 model_override，则使用 key 中的 model
        key_model = key.get("model", "")
        if key_model and not agent.model_override:
            agent.model = key_model

    # ── 状态 ──────────────────────────────────────────────

    def is_ready(self, role: AgentRole) -> bool:
        return bool(self._agents[role].api_key)

    def all_ready(self) -> bool:
        return all(self.is_ready(r) for r in AgentRole)

    def get_status(self) -> dict:
        agents = self.get_all_agents()
        return {
            "total": 9,
            "ready": sum(1 for a in agents if a.api_key),
            "spare_keys": len(self._spare_keys),
            "agents": [
                {
                    "role": a.role.value,
                    "name": a.name,
                    "name_en": a.name_en,
                    "icon": a.icon,
                    "description": a.description,
                    "recommended_models": a.recommended_models,
                    "model_override": a.model_override,
                    "effective_model": a.model_override or a.model or a.recommended_models[0] if a.recommended_models else "",
                    "has_key": bool(a.api_key),
                    "priority": a.priority,
                }
                for a in agents
            ],
        }


# ── 全局单例 ──────────────────────────────────────────────

_agent_registry: Optional[AgentRegistry] = None


def get_agent_registry() -> AgentRegistry:
    global _agent_registry
    if _agent_registry is None:
        _agent_registry = AgentRegistry()
    return _agent_registry


def reset_agent_registry() -> AgentRegistry:
    global _agent_registry
    _agent_registry = AgentRegistry()
    return _agent_registry
