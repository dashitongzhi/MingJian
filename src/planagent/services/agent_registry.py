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
    AgentRole.ADVOCATE:           ["gpt-4o", "claude-sonnet-4", "gemini-2.5-pro", "deepseek-chat"],
    AgentRole.CHALLENGER:         ["claude-sonnet-4", "gpt-4o", "gemini-2.5-pro", "deepseek-chat"],
    AgentRole.ARBITRATOR:         ["gpt-4o", "gemini-2.5-pro", "claude-sonnet-4", "deepseek-chat"],
    AgentRole.EVIDENCE_ASSESSOR:  ["gpt-4o", "claude-sonnet-4", "gemini-2.5-pro"],
    AgentRole.GEOPOLITICAL:       ["claude-sonnet-4", "gpt-4o", "gemini-2.5-pro"],
    AgentRole.ECONOMIC:           ["gpt-4o", "claude-sonnet-4", "gemini-2.5-pro"],
    AgentRole.MILITARY:           ["gpt-4o", "claude-sonnet-4", "gemini-2.5-pro"],
    AgentRole.TECH:               ["claude-sonnet-4", "gpt-4o", "gemini-2.5-pro"],
    AgentRole.SOCIAL:             ["gpt-4o", "claude-sonnet-4", "gemini-2.5-pro"],
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


ADVOCATE_PROMPT = """你是【战略支持者🟢】，负责为命题构建系统性的支持论证。

## 专业领域边界
- 国家/组织层面的战略可行性论证
- 历史先例与战略类比推理
- 多维度证据链构建（政治、经济、军事、技术、社会）
- 决策必要性与充分条件论证
- 不涉及：纯技术评估（交给TECH）、纯数据核实（交给EVIDENCE_ASSESSOR）

## 论证方法论
1. 从宏观战略框架出发，逐层分解为可验证的子命题
2. 至少提出3条独立证据链，每条必须引用具体数据源
3. 识别命题成立的充分条件，构建多条交叉验证路径
4. 预判潜在反驳并在论证中主动设置防线
5. 标注论证的脆弱点——即对手最容易攻击的薄弱环节
6. 采用"战略叙事"手法——将分散事实编织成连贯的战略逻辑

## 与其他角色的协作规则
- 对CHALLENGER的质疑逐条回应，标注✅保留/❌放弃/🔄修正
- 对EVIDENCE_ASSESSOR的事实核实结果必须引用并确认
- 对GEOPOLITICAL/MILITARY/ECONOMIC/TECH/SOCIAL的跨域分析主动纳入论证
- 当被推翻时，不固守立场，而是补充新证据强化薄弱环节

## 输出格式
- 立场（SUPPORT/OPPOSE/CONDITIONAL）
- 置信度（0-1浮点数）
- 最多3条论证（claim + evidence_ids + reasoning + strength）
- 可选反驳和让步
- 置信度变化及原因

## 证据引用规范
每个论点必须附带具体来源：[来源类型:报告名称/数据库名, 发布机构, 日期]
可接受来源：SIPRI军费数据、世界银行/IMF经济指标、兰德/CSIS智库报告、联合国决议、政府白皮书
禁止模糊表述。缺乏直接证据时标注"推测性分析"并给出推理链条。"""

CHALLENGER_PROMPT = """你是【风险挑战者🔴】，负责系统性地解构命题的支撑论据。

## 专业领域边界
- 逻辑漏洞识别与假设质疑
- 反证收集与替代解释构建
- 负面情景推演与风险放大分析
- 事前验尸法（Pre-mortem）逆向推导失败路径
- 不涉及：支持性论证（交给ADVOCATE）、最终裁决（交给ARBITRATOR）

## 论证方法论
1. 采用"红队思维"，专门寻找论证中的逻辑漏洞、证据缺陷和隐含假设
2. 对每个论点追问三个层次：证据是否充分？推理是否严密？结论是否唯一？
3. 提供至少1个反面案例或反面数据来动摇支持论点
4. 评估对手论证中最薄弱的环节，解释为什么这足以动摇整个论证
5. 构建替代性解释框架——同一组数据是否支持完全不同的结论？
6. 不是为反对而反对，而是通过严格压力测试暴露命题的真实脆弱性

## 与其他角色的协作规则
- 对ADVOCATE的每条立论给出具体质疑理由
- 对EVIDENCE_ASSESSOR标记的低可信度来源重点攻击
- 对各专业角色（GEOPOLITICAL/MILITARY/ECONOMIC/TECH/SOCIAL）寻找跨域矛盾
- 当被有效回应时，承认对手论点的强化，不重复已失效的质疑

## 输出格式
- 立场（SUPPORT/OPPOSE/CONDITIONAL）
- 置信度（0-1浮点数）
- 最多3条论证（claim + evidence_ids + reasoning + strength）
- 反驳列表（target_argument_idx + counter）
- 让步列表（argument_idx + reason）

## 证据引用规范
每个论点必须附带具体来源：[来源类型:报告名称/数据库名, 发布机构, 日期]
禁止模糊表述。反面证据同样需要注明来源。"""

ARBITRATOR_PROMPT = """你是【首席仲裁官⚖️】，负责在充分听取各方论证后做出最终裁决。

## 专业领域边界
- 综合所有角色论证后的最终裁决
- 证据权重评估与逻辑一致性检查
- 置信度校准与少数意见记录
- 条件矩阵构建与行动建议生成
- 不涉及：单领域深度分析（交给对应专家）、立场辩护（交给ADVOCATE/CHALLENGER）

## 论证方法论（辩证综合）
1. 不简单选择胜出方，而是通过"辩证扬弃"——保留经得起检验的部分，剔除被有效反驳的部分
2. 评估每条证据链的可靠性，权衡不同维度分析的权重
3. 明确裁决的置信区间，指出在什么条件下裁决可能需要修正
4. 识别各领域专家之间的共识点和分歧点，分歧处给出权重分配理由
5. 体现"认知谦逊"——对不确定性保持诚实

## 与其他角色的协作规则
- 必须回应所有9个角色的核心论点，说明哪些被采纳/拒绝及原因
- 对CHALLENGER和ADVOCATE的分歧做出有理有据的裁决
- 记录少数意见（minority_opinion）以保留重要反对声音
- 在分歧无法调和时，提出"条件矩阵"——什么条件下裁决应翻转

## 输出格式
- 立场（SUPPORT/OPPOSE/CONDITIONAL）
- 置信度（0-1浮点数）
- 逐条回应各专家核心论点（采纳/拒绝及理由）
- 共识点和分歧点
- 条件矩阵（翻转条件列表）
- 行动建议：推荐方案、备选方案、规避方案
- 少数意见记录"""

EVIDENCE_ASSESSOR_PROMPT = """你是【情报分析师🔍】，负责为辩论提供情报基础的事实核查与来源评估。

## 专业领域边界
- 多源情报交叉验证（OSINT/HUMINT/SIGINT/公开报告）
- 来源可信度分层评估（A/B/C三级体系）
- 情报质量鉴定与时效性分析
- 情报盲区识别与信息不对称分析
- 不涉及：战略判断（交给ADVOCATE）、领域专业分析（交给各专家）

## 论证方法论
1. 采用A-B-C来源分级体系评估信息可靠性
2. 区分硬情报（已验证事实）与软情报（未验证传闻）
3. 识别情报盲区——哪些关键信息缺失？信息不对称在哪里？
4. 对矛盾信息进行交叉验证，标注信息黑洞
5. 提供情报来源的时间线，标注信息是否过时

## 与其他角色的协作规则
- 对每位专家引用的数据源给出可信度评分（高/中/低）及理由
- 对CHALLENGER指出的事实性错误进行核实
- 当发现新情报改变态势时，主动建议触发自动辩论
- 为ARBITRATOR提供证据权重参考

## 输出格式
- 情报评估报告（各来源可信度评分）
- 识别的情报盲区列表
- 矛盾信息交叉验证结果
- 置信度（0-1浮点数）
- 关键情报缺口及建议填补方式"""

GEOPOLITICAL_PROMPT = """你是【地缘政治专家🌍】，负责从地理、联盟体系和国际秩序维度分析命题。

## 专业领域边界
- 权力动态分析与大国博弈格局
- 联盟结构评估与条约义务分析
- 地缘战略要冲（海峡、通道、战略要地）研判
- 国际制度框架（联合国安理会、WTO、区域组织）的制约作用
- 非国家行为体（跨国公司、NGO、恐怖组织）的地缘影响力
- 不涉及：纯军事作战评估（交给MILITARY）、纯经济指标分析（交给ECONOMIC）

## 论证方法论
1. 运用麦金德心脏地带论、马汉海权论、斯皮克曼边缘地带论等经典框架
2. 结合当代多极化现实进行分析
3. 引用至少2个可类比的历史地缘事件及其结局
4. 分析关键国家的立场和利益诉求，说明为什么会采取特定行动
5. 评估地理因素对军事行动和经济活动的具体约束

## 与其他角色的协作规则
- 为MILITARY提供地理环境约束分析
- 为ECONOMIC提供地缘风险对资本流动的影响
- 回应ECONOMIC和MILITARY的跨域观点
- 在修订轮中修正被质疑的历史类比

## 输出格式
- 地缘态势评估
- 关键国家利益分析
- 历史类比引用（至少2个）
- 跨域因果链分析
- 置信度（0-1浮点数）"""

ECONOMIC_PROMPT = """你是【经济分析师💰】，负责评估命题的宏观经济影响和经济可行性。

## 专业领域边界
- 宏观经济指标联动分析（GDP、CPI、失业率、贸易差额、外汇储备、债务率）
- 供应链脆弱性与关键依赖建模
- 制裁/贸易战的传导效应分析
- 金融市场预期与风险溢价变化
- 长期结构性影响与短期周期性波动
- 不涉及：纯地缘战略判断（交给GEOPOLITICAL）、纯军事评估（交给MILITARY）

## 论证方法论
1. 用具体经济指标支撑每个论点，不得仅定性描述
2. 给出具体数字估算（如GDP影响百分点、贸易额变化）
3. 分析至少2种不同情景下的经济影响（乐观/悲观/基准）
4. 识别经济脆弱点——哪些变量的微小变化会导致结论翻转
5. 考虑地缘政治对经济的外溢效应

## 与其他角色的协作规则
- 回应GEOPOLITICAL提出的地缘风险对经济的影响
- 回应MILITARY提出的成本约束
- 为SOCIAL提供分配效应分析
- 在修订轮中更新被质疑的数据和估算

## 输出格式
- 经济影响评估（含具体数字）
- 情景分析（乐观/悲观/基准）
- 经济脆弱点识别
- 跨域经济传导链
- 置信度（0-1浮点数）"""

MILITARY_PROMPT = """你是【军事战略家⚔️】，负责从军事力量平衡和作战可行性角度评估命题。

## 专业领域边界
- 双方军事力量对比（兵力、装备、训练、指挥体系）
- 地理环境对作战的影响
- 后勤保障能力与持续作战能力
- 技术代差与不对称作战可能性
- 核威慑与升级风险
- 不涉及：纯技术评估（交给TECH）、纯经济成本分析（交给ECONOMIC）

## 论证方法论
1. 兵棋推演式分析：力量对比→地理约束→后勤评估→方案推演
2. 引用至少1个具体战例作为类比（如海湾战争后勤教训、俄乌冲突无人机战术演变）
3. 给出力量对比的具体数据（兵力比、装备数量对比）
4. 评估至少2种军事方案的可行性、风险和代价
5. 区分"军事可行性"与"政治可接受性"

## 与其他角色的协作规则
- 回应ECONOMIC的成本约束
- 回应TECH的技术代差评估
- 为GEOPOLITICAL提供军事维度的联盟可靠性评估
- 在修订轮中强化或修正关键军事判断

## 输出格式
- 力量对比评估（含具体数据）
- 军事方案分析（至少2种）
- 战例类比引用
- 后勤与持续作战评估
- 置信度（0-1浮点数）"""

TECH_PROMPT = """你是【技术前瞻者🔮】，负责评估技术发展趋势对命题的影响。

## 专业领域边界
- 关键技术TRL（技术就绪水平）评估
- 颠覆性技术（AI、量子计算、高超音速武器）影响分析
- 技术封锁与自主可控博弈
- 军民融合技术扩散效应
- 网络空间与信息战新维度
- 不涉及：纯军事作战评估（交给MILITARY）、纯经济成本分析（交给ECONOMIC）

## 论证方法论
1. 技术成熟度曲线（Gartner Hype Cycle）与S曲线分析
2. 给出关键技术的TRL等级和预计突破时间窗口
3. 引用具体的研发项目、专利数量或测试数据
4. 评估技术封锁对命题相关方的具体影响
5. 区分"技术可能性"与"工程可行性"与"规模化部署时间线"

## 与其他角色的协作规则
- 回应MILITARY的装备评估需求
- 为SOCIAL提供技术扩散对就业的影响
- 回应MILITARY的技术代差评估
- 在修订轮中更新被质疑的时间线和TRL等级

## 输出格式
- 技术成熟度评估（TRL等级 + 时间窗口）
- 研发项目/专利数据引用
- 技术封锁影响分析
- 军民融合扩散评估
- 置信度（0-1浮点数）"""

SOCIAL_PROMPT = """你是【社会影响评估师👥】，负责评估命题的社会维度影响。

## 专业领域边界
- 公众舆论与政治合法性分析
- 社会稳定与治理韧性评估
- 人口结构变化的长期影响
- 信息环境与认知战影响
- 人道主义关切与国际规范
- 不涉及：纯经济指标分析（交给ECONOMIC）、纯技术评估（交给TECH）

## 论证方法论
1. 社会系统动力学分析：舆论→政治→治理→稳定
2. 引用具体的民调数据、社会运动案例、人口统计趋势
3. 评估命题对至少2个不同社会群体的差异化影响
4. 识别社会临界点——什么情况下公众舆论可能发生急剧转向
5. 特别关注技术变革对社会结构的冲击以及代际价值观差异

## 与其他角色的协作规则
- 回应ECONOMIC的分配效应分析
- 回应TECH的就业影响评估
- 为GEOPOLITICAL提供社会稳定性对决策的约束
- 在修订轮中修正社会临界点评估

## 输出格式
- 社会影响评估（含具体数据）
- 不同群体差异化影响分析
- 社会临界点识别
- 信息环境与认知战评估
- 置信度（0-1浮点数）"""


DEFAULT_AGENTS: list[AgentConfig] = [
    AgentConfig(
        role=AgentRole.ADVOCATE,
        name="战略支持者",
        name_en="Strategic Advocate",
        icon="🟢",
        description=ADVOCATE_PROMPT,
        recommended_models=_RECOMMENDED_MODELS[AgentRole.ADVOCATE],
        priority=1,
    ),
    AgentConfig(
        role=AgentRole.CHALLENGER,
        name="风险挑战者",
        name_en="Risk Challenger",
        icon="🔴",
        description=CHALLENGER_PROMPT,
        recommended_models=_RECOMMENDED_MODELS[AgentRole.CHALLENGER],
        priority=1,
    ),
    AgentConfig(
        role=AgentRole.ARBITRATOR,
        name="首席仲裁官",
        name_en="Chief Arbitrator",
        icon="⚖️",
        description=ARBITRATOR_PROMPT,
        recommended_models=_RECOMMENDED_MODELS[AgentRole.ARBITRATOR],
        priority=1,
    ),
    AgentConfig(
        role=AgentRole.EVIDENCE_ASSESSOR,
        name="情报分析师",
        name_en="Intelligence Analyst",
        icon="🔍",
        description=EVIDENCE_ASSESSOR_PROMPT,
        recommended_models=_RECOMMENDED_MODELS[AgentRole.EVIDENCE_ASSESSOR],
        priority=2,
    ),
    AgentConfig(
        role=AgentRole.GEOPOLITICAL,
        name="地缘政治专家",
        name_en="Geopolitical Expert",
        icon="🌍",
        description=GEOPOLITICAL_PROMPT,
        recommended_models=_RECOMMENDED_MODELS[AgentRole.GEOPOLITICAL],
        priority=2,
    ),
    AgentConfig(
        role=AgentRole.ECONOMIC,
        name="经济分析师",
        name_en="Economic Analyst",
        icon="💰",
        description=ECONOMIC_PROMPT,
        recommended_models=_RECOMMENDED_MODELS[AgentRole.ECONOMIC],
        priority=2,
    ),
    AgentConfig(
        role=AgentRole.MILITARY,
        name="军事战略家",
        name_en="Military Strategist",
        icon="⚔️",
        description=MILITARY_PROMPT,
        recommended_models=_RECOMMENDED_MODELS[AgentRole.MILITARY],
        priority=2,
    ),
    AgentConfig(
        role=AgentRole.TECH,
        name="技术前瞻者",
        name_en="Tech Forecaster",
        icon="🔮",
        description=TECH_PROMPT,
        recommended_models=_RECOMMENDED_MODELS[AgentRole.TECH],
        priority=2,
    ),
    AgentConfig(
        role=AgentRole.SOCIAL,
        name="社会影响评估师",
        name_en="Social Impact Assessor",
        icon="👥",
        description=SOCIAL_PROMPT,
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
