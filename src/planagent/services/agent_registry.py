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


@dataclass
class AgentConfig:
    """单个智能体配置"""

    role: AgentRole
    name: str
    name_en: str
    icon: str
    description: str
    provider_type: str = ""
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    priority: int = 1  # 1=核心辩论角色, 2=视角分析角色


DEFAULT_AGENTS: list[AgentConfig] = [
    AgentConfig(
        role=AgentRole.ADVOCATE,
        name="战略支持者",
        name_en="Strategic Advocate",
        icon="🟢",
        description="正面论证，寻找支持证据",
        priority=1,
    ),
    AgentConfig(
        role=AgentRole.CHALLENGER,
        name="风险挑战者",
        name_en="Risk Challenger",
        icon="🔴",
        description="反面论证，寻找风险漏洞",
        priority=1,
    ),
    AgentConfig(
        role=AgentRole.ARBITRATOR,
        name="首席仲裁官",
        name_en="Chief Arbitrator",
        icon="⚖️",
        description="综合评判，出最终裁决",
        priority=1,
    ),
    AgentConfig(
        role=AgentRole.EVIDENCE_ASSESSOR,
        name="情报分析师",
        name_en="Intelligence Analyst",
        icon="🔍",
        description="分析搜集到的证据质量",
        priority=2,
    ),
    AgentConfig(
        role=AgentRole.GEOPOLITICAL,
        name="地缘政治专家",
        name_en="Geopolitical Expert",
        icon="🌍",
        description="地缘政治视角分析",
        priority=2,
    ),
    AgentConfig(
        role=AgentRole.ECONOMIC,
        name="经济分析师",
        name_en="Economic Analyst",
        icon="💰",
        description="经济/市场视角分析",
        priority=2,
    ),
    AgentConfig(
        role=AgentRole.MILITARY,
        name="军事战略家",
        name_en="Military Strategist",
        icon="⚔️",
        description="军事/安全视角分析",
        priority=2,
    ),
    AgentConfig(
        role=AgentRole.TECH,
        name="技术前瞻者",
        name_en="Tech Forecaster",
        icon="🔮",
        description="技术趋势视角分析",
        priority=2,
    ),
    AgentConfig(
        role=AgentRole.SOCIAL,
        name="社会影响评估师",
        name_en="Social Impact Assessor",
        icon="👥",
        description="社会/舆论视角分析",
        priority=2,
    ),
]


class AgentRegistry:
    """智能体注册中心 — 管理9个智能体"""

    def __init__(self) -> None:
        self._agents: dict[AgentRole, AgentConfig] = {
            a.role: AgentConfig(**{**a.__dict__}) for a in DEFAULT_AGENTS
        }

    # ── 查询 ──────────────────────────────────────────────

    def get_agent(self, role: AgentRole) -> AgentConfig:
        return self._agents[role]

    def get_all_agents(self) -> list[AgentConfig]:
        return list(self._agents.values())

    def get_provider_config(self, role: AgentRole) -> dict[str, str]:
        """获取指定角色的 provider 配置，用于 LLM 调用"""
        a = self._agents[role]
        return {
            "provider_type": a.provider_type,
            "api_key": a.api_key,
            "base_url": a.base_url,
            "model": a.model,
        }

    # ── 更新 ──────────────────────────────────────────────

    def update_agent(self, role: AgentRole, **kwargs: object) -> None:
        agent = self._agents[role]
        for k, v in kwargs.items():
            if hasattr(agent, k):
                setattr(agent, k, v)

    # ── API Key 分配 ──────────────────────────────────────

    def distribute_keys(self, keys: list[dict[str, str]]) -> None:
        """自动分配 API Key 到 9 个智能体

        keys 格式::

            [{"api_key": "sk-xxx", "provider_type": "openai",
              "base_url": "...", "model": "..."}]

        分配策略:
        * 1 个 key → 9 个 agent 全部使用该 key
        * 2 个 key → 核心 3 角色用 key1，视角 6 角色用 key2
        * 3+ key  → 轮询分配
        """
        if not keys:
            return

        agents = self.get_all_agents()

        if len(keys) == 1:
            k = keys[0]
            for agent in agents:
                self._apply_key(agent, k)
        elif len(keys) == 2:
            k1, k2 = keys[0], keys[1]
            for agent in agents:
                self._apply_key(agent, k1 if agent.priority == 1 else k2)
        else:
            for i, agent in enumerate(agents):
                self._apply_key(agent, keys[i % len(keys)])

    @staticmethod
    def _apply_key(agent: AgentConfig, key: dict[str, str]) -> None:
        agent.provider_type = key.get("provider_type", "openai")
        agent.api_key = key["api_key"]
        agent.base_url = key.get("base_url", "")
        agent.model = key.get("model", "")

    # ── 状态 ──────────────────────────────────────────────

    def is_ready(self, role: AgentRole) -> bool:
        return bool(self._agents[role].api_key)

    def all_ready(self) -> bool:
        return all(self.is_ready(r) for r in AgentRole)

    def get_status(self) -> dict:
        return {
            "total": 9,
            "ready": sum(1 for r in AgentRole if self.is_ready(r)),
            "agents": [
                {
                    "role": a.role.value,
                    "name": a.name,
                    "name_en": a.name_en,
                    "icon": a.icon,
                    "description": a.description,
                    "provider_type": a.provider_type,
                    "model": a.model,
                    "has_key": bool(a.api_key),
                    "priority": a.priority,
                }
                for a in self.get_all_agents()
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
