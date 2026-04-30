# 明鉴 -- 证据驱动的多智能体决策推演平台

## 摘要

明鉴 是一个**"证据驱动、可解释、可复验"的统一决策推演平台**。它以同一套内核同时支持企业/产业生态推演与军事/冲突推演，并通过多模型辩论、自校准闭环和虚拟董事会等机制，将传统仿真系统升级为具备自我进化能力的智能决策辅助系统。

本文档全面梳理 明鉴 的功能模块、创新性架构设计与技术实现，涵盖从情报采集到报告输出的完整链路。

---

## 目录

1. [平台定位与核心理念](#1-平台定位与核心理念)
2. [系统整体架构](#2-系统整体架构)
3. [核心功能模块](#3-核心功能模块)
   - 3.1 [多源情报融合引擎](#31-多源情报融合引擎12-源适配器)
   - 3.2 [证据链与置信度分级](#32-证据链与置信度分级)
   - 3.3 [知识图谱构建](#33-知识图谱构建)
   - 3.4 [统一推演内核](#34-统一推演内核规则驱动--agent-based--事件注入)
   - 3.5 [双领域包注册机制](#35-双领域包domain-pack注册机制)
   - 3.6 [场景分支与 What-If 分析](#36-场景分支与-what-if-分析)
   - 3.7 [多模型辩论机制](#37-多模型辩论机制model-debate-protocol)
   - 3.8 [假设校准闭环](#38-假设校准闭环calibration-loop)
   - 3.9 [多模型自助复验迭代引擎](#39-多模型自助复验迭代引擎jarvis-集成)
   - 3.10 [战略助手](#310-战略助手strategic-assistant)
   - 3.11 [规则监控与自动触发](#311-规则监控与自动触发watch-rule)
   - 3.12 [统一工作台](#312-统一工作台workbench)
   - 3.13 [报告生成](#313-报告生成)
   - 3.14 [事件总线与 Worker 编排](#314-事件总线与-worker-编排)
   - 3.15 [配置系统](#315-配置系统)
4. [创新性架构总结](#4-创新性架构总结)
5. [前端可视化](#5-前端可视化)
6. [技术栈](#6-技术栈)
7. [实施阶段](#7-实施阶段)

---

## 1. 平台定位与核心理念

传统决策分析系统面临三个核心问题：

1. **信息碎片化**：情报来源分散，无法形成统一的证据链
2. **推理黑箱化**：决策过程不可解释，难以追溯"为什么做出这个判断"
3. **系统静态化**：规则和模型一旦设定便不会自我修正，越用越脱离现实

明鉴 的设计目标是同时解决这三个问题：

- **证据驱动**：每一条决策都可以追溯到原始情报来源和证据链
- **可解释**：完整的 `DecisionRecord` 包含 `why_selected`、`evidence_ids`、`policy_rule_ids`、`expected_effect` 和 `actual_effect`
- **可复验**：推演结果不可变（immutable），相同参数和种子永远产出相同结果，支持完整回放
- **自进化**：推演产生的预测假设经过自动校准后反馈到规则权重，形成闭环自优化

---

## 2. 系统整体架构

### 2.1 运行拓扑

```
                         ┌─────────────────────────────┐
                         │    Next.js Frontend (SPA)    │
                         │  Dashboard / Assistant / Sim │
                         │  Debate / Intelligence       │
                         └──────────────┬───────────────┘
                                        │ HTTP / SSE
                         ┌──────────────▼───────────────┐
                         │   FastAPI Control Plane       │
                         │   (65+ REST/SSE endpoints)    │
                         └──┬───┬───┬───┬───┬───┬───┬───┘

> **依赖注入工厂模式**：`api/routes/_deps.py` 实现了工厂函数模式——`ensure_app_services(request)` 惰性初始化共享服务（`event_bus`、`rule_registry`、`openai_service`）到 `request.app.state`；各 `get_*_service()` 工厂函数（`get_pipeline_service`、`get_simulation_service`、`get_analysis_service`、`get_debate_service`、`get_assistant_service` 等）组合注入所需依赖，确保每个 API 端点获取完整配置的服务实例。
                            │   │   │   │   │   │   │
           ┌────────────────┘   │   │   │   │   │   └────────────────┐
           ▼                    ▼   ▼   ▼   ▼   ▼                    ▼
    ┌────────────┐  ┌────────┐ ┌───┐ ┌───┐ ┌───┐ ┌────────┐  ┌──────────────┐
    │ingest-     │  │knowledge│ │sim│ │rev│ │rpt│ │watch-  │  │strategic-    │
    │worker      │  │worker  │ │ula│ │iew│ │gen│ │ingest  │  │watch-worker  │
    └────────────┘  └────────┘ │tio│ │   │ │   │ │worker  │  └──────────────┘
                               │n  │ └───┘ └───┘ └────────┘
    ┌────────────┐             └───┘
    │graph-worker│  ┌──────────────┐
    └────────────┘  │calibration-  │
                    │worker        │
                    └──────────────┘

    ┌────────────────────────────────────────────────────┐
    │              Redis Streams (事件总线)                │
    │  raw.ingested / evidence.created / simulation.*    │
    │  debate.* / report.* / claim.review_requested     │
    └────────────────────────────────────────────────────┘

    ┌────────────────────────────────────────────────────┐
    │         PostgreSQL + pgvector + PostGIS             │
    │  证据表 / 推演表 / 图谱表 / 辩论表 / 校准表        │
    └────────────────────────────────────────────────────┘

    ┌────────────┐
    │   MinIO    │  源快照存储
    └────────────┘
```

### 2.2 数据流全景

外部原始信息统一流转为：

```
RawSourceItem                原始采集（12 个源适配器）
    ↓
NormalizedItem               标准化（去重、规范化 URL、hash）
    ↓
EvidenceItem                 证据化（置信度评估、类型分类）
    ↓
Claim                        声明提取（Subject-Predicate-Object 三元组）
    ↓
Signal / Event / Trend       层级升级（按置信度自动分级）
    ↓
ExternalShock                外部冲击注入（映射到推演域的状态扰动）
    ↓
DecisionRecord               决策记录（含完整推理链）
    ↓
StateSnapshot                状态快照（推演每步的完整状态）
    ↓
GeneratedReport              报告生成（含 "Why This Happened"）
    ↓
Hypothesis                   预测假设（推演结果的可验证预测）
    ↓
CalibrationRecord            校准记录（假设验证结果 → 规则权重反馈）
    ↑ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ 反馈闭环 ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─┘
```

### 2.3 事件主题

系统内部使用 12 个事件主题进行 Worker 间通信：

| 主题 | 生产者 | 消费者 |
|------|--------|--------|
| `raw.ingested` | ingest-worker | knowledge-worker |
| `evidence.created` | knowledge-worker | graph-worker, simulation-worker |
| `evidence.updated` | review-worker | (下游消费者) |
| `claim.review_requested` | knowledge-worker | review-worker |
| `knowledge.extracted` | knowledge-worker | graph-worker |
| `simulation.completed` | simulation-worker | report-worker |
| `scenario.completed` | simulation-worker | report-worker |
| `report.generated` | report-worker | (下游消费者) |
| `verification.failed` | calibration-worker | (告警) |
| `debate.triggered` | API 层 | (审计) |
| `debate.completed` | debate-service | (审计) |
| `watch.rule_triggered` | watch-ingest-worker | (自动触发推演/辩论) |

---

## 3. 核心功能模块

### 3.1 多源情报融合引擎（12 源适配器）

明鉴 集成了 12 个公开数据源适配器，覆盖全球新闻、技术社区、社交媒体、航空 OSINT 和气象情报：

| 数据源 | 接口方式 | 覆盖范围 |
|--------|---------|---------|
| Google News | RSS 聚合 | 全球新闻覆盖 |
| Reddit | JSON API | 社区讨论与舆情 |
| Hacker News | Algolia API | 技术前沿动态 |
| GitHub | REST API (repos / issues / PRs) | 开源项目活跃度 |
| RSS Feeds | 可配置源列表 | 自定义信息源 |
| GDELT | 文档搜索 API | 全球事件数据库 |
| Open-Meteo | 天气 API | 气象 / 灾害情报 |
| OpenSky | 航空 API | 军事空域 OSINT |
| X / Twitter | 官方 API + 模型回退搜索 | 社交媒体情报 |
| Linux.do | Discourse API | 中文技术社区 |
| 小红书 | 平台抓取 | 中文消费舆情 |
| 抖音 | 平台抓取 | 中文短视频舆情 |

**架构设计要点：**

- **策略模式的 SourceAdapter**：每个数据源封装为 `key / label / enabled / limit / fetcher` 的标准结构体，统一迭代、统一限流、统一健康追踪。新增数据源只需定义一个 `SourceAdapter` 实例并注册到列表中
- **地理包围盒映射**：根据查询关键词（如"台海""乌克兰""红海"）自动映射到对应地理区域的经纬度范围，用于 OpenSky 航空 OSINT 查询
- **双路径 X 搜索**：优先使用模型回退搜索（`PLANAGENT_OPENAI_X_SEARCH_*`），无配置时自动切换到官方 X API（`PLANAGENT_X_BEARER_TOKEN`），保证在任何配置下都不会阻断主流程
- **CJK 感知查询构建**：自动检测中日韩字符并适配不同平台的搜索策略和查询格式
- **信源健康追踪**：每个源维护独立的连续失败计数器和 DEGRADED 状态阈值（连续 5 次失败标记为 DEGRADED）
- **去重规则**：规范 URL + 标题/正文 hash + 近似标题相似度 + 时间窗口语义近重复
- **DB-backed TTL 缓存**：`POST /analysis` 使用数据库缓存，可通过 `PLANAGENT_ANALYSIS_CACHE_ENABLED` 和 `PLANAGENT_API_CACHE_TTL_SECONDS` 控制

### 3.2 证据链与置信度分级

所有进入系统的原始信息经过标准化、去重、抽取后形成证据链，并按置信度自动分级：

**三档置信度门槛：**

| 置信度区间 | 处置方式 | 说明 |
|-----------|---------|------|
| `≥ 0.70` | 进入推演主链 | 自动参与仿真推演 |
| `0.45 ~ 0.70` | 进入人工审核队列 | 需分析师确认后参与推演 |
| `< 0.45` | 仅留存检索 | 不进入主链，但可在图谱中检索 |

**Claim 提取：**

从 `EvidenceItem` 中提取结构化的 `Subject-Predicate-Object` 三元组声明，每条 Claim 包含：
- `subject`（主体）、`predicate`（谓词）、`object_text`（客体）
- `statement`（完整声明文本）
- `confidence`（置信度）
- `kind`（声明类型分类）
- `requires_review`（是否需要审核）

**信号/事件/趋势升级：**

Claim 可被自动升级为更高层级的分析对象：
- `Signal`：即时信号（如股价异动、新闻发布）
- `EventRecord`：结构化事件（如并购、打击、谈判）
- `Trend`：趋势性变化（如市场份额持续下降、军事消耗率上升）

### 3.3 知识图谱构建

`GraphWorker` 从证据和声明中自动构建知识图谱，支持语义搜索：

**图结构：**
- 节点类型：EvidenceItem、Claim、Signal、Event、Trend
- 边类型：`evidence_to_claim`、`claim_to_signal`、`claim_to_event`、`claim_to_trend`

**创新设计：**

- **SHA-256 哈希嵌入**：使用 SHA-256 对文本 token 做哈希，映射到固定维度的向量索引，通过 hash 奇偶性决定向量元素的正负符号，最后 L2 归一化。这是一个**零外部依赖的确定性向量嵌入方案**，无需调用任何 embedding 模型即可完成语义相似度检索，且结果完全可复现
- **双引擎相似度搜索**：
  - 生产环境（PostgreSQL）：使用 CTE + `jsonb_array_elements` + `CROSS JOIN unnest()` 在数据库内完成向量余弦相似度计算
  - 开发环境（SQLite）：自动回退到 Python 纯计算余弦相似度
- **SQLite 开发兼容层**：`db.py` 的 `init_models()` 包含动态 PRAGMA 检查机制——启动时扫描已有表的列结构，对缺失的列自动执行 `ALTER TABLE` 补齐。这使得开发者可以直接使用 SQLite 进行本地开发而无需运行 Alembic 迁移脚本，同时生产环境通过 Alembic 统一管理 schema 演进
- **缓存感知批量 Upsert**：在处理前批量加载现有节点/边到内存缓存字典，每次 upsert 先查缓存决定 insert 还是 update，避免 N+1 查询

### 3.4 统一推演内核（规则驱动 + Agent-Based + 事件注入）

推演内核是平台的核心引擎，采用**离散时间步（discrete tick）**模型，不绑定具体行业语义。

#### 3.4.1 时间模型

| 域 | 默认 tick 粒度 | 可配置 |
|----|---------------|--------|
| 企业域 | 1 tick = 1 week | 1 day / 1 month |
| 军事域 | 1 tick = 6 hours | 1 hour / 24 hours |

跨域推演（企业 + 军事混合场景）使用最细粒度 tick，粗粒度域在非活跃 tick 跳过处理。

#### 3.4.2 单步执行顺序

每个 tick 内的执行顺序固定为：

```
1. 注入本 tick 窗口内的 ExternalShock
2. 所有 Actor 并行提议 CandidateAction（无互相感知）
3. DecisionPolicy 按优先级排序、冲突解决、选择执行
4. 按选定动作顺序执行 OutcomeDelta
5. 生成 StateSnapshot 和 DecisionRecord
```

#### 3.4.3 Actor 三级降级决策模型

这是推演内核最关键的创新设计。Actor 的决策采用三级降级策略，保证系统在任何条件下都能正常运行：

> **SimulationRun 模型**：每个推演运行记录包含 `military_use_mode` 字段（`nullable String(32)`），取值为 `"osint"`、`"training"` 或 `"full_domain"`（默认），控制军事推演的执行模式——OSINT 模式仅采集情报、训练模式简化推演逻辑、完整域模式启用全部军事能力。

| 级别 | 方法 | 触发条件 | 特点 |
|------|------|---------|------|
| **Level 1** | 规则引擎 | 默认（确定性） | 可解释、可复现、零 LLM 成本 |
| **Level 2** | LLM 辅助 | 规则匹配为空或所有 total_score < 0.6（`_DECISION_MIN_SCORE`） | 复杂推理，超时 10s |
| **Level 3** | 随机加权 | LLM 超时 / 失败 | 按历史成功率加权随机选择，标记 `fallback_random` |

**Level 1 — 规则引擎（默认）：**
- 基于当前 StateSnapshot + ExternalShock，匹配 YAML / Python 规则
- 输出 CandidateAction 列表，每个附带 `score` 和 `rule_id`
- 优点：可解释、可复现、零 LLM 成本
- 适用：常规场景、训练教学模式、回归测试

**Level 2 — LLM 辅助：**
- 当规则匹配结果为空或 score 均 < 30 时触发
- 将当前状态 + 历史 3 步 DecisionRecord + 可用动作列表发给 LLM
- 模型路由：企业域 → Claude，军事域 → Claude
- 超时限制：10 秒，超时降级到 Level 3
- 超时：10s，超时则降级到 Level 3

**Level 3 — 随机加权（降级兜底）：**
- 从当前可用动作中按历史成功率加权随机选择
- 标记 `decision_method: "fallback_random"`，在报告中高亮提示

#### 3.4.4 规则表示格式（YAML + Python 双层）

规则采用**声明式 YAML + 命令式 Python** 双层结构：

**YAML 层**（声明触发条件、影响目标、参数范围，供非技术分析员编辑）：

```yaml
rules:
  - id: "corp.gpu_price_shock"
    domain: "corporate"
    trigger:
      event_type: "market_price_change"
      conditions:
        - field: "asset"
          op: "eq"
          value: "gpu"
        - field: "change_pct"
          op: "gte"
          value: 0.20
    effects:
      - target: "infra_cost"
        op: "multiply"
        value: 1.25
      - target: "delivery_velocity"
        op: "multiply"
        value: 0.85
    cooldown_ticks: 4
    priority: 80
    explanation_template: "GPU 价格上涨 {change_pct}%，基础设施成本增加，交付速度下降"
```

**Python 层**（复杂计算逻辑，通过 `@rule_handler` 装饰器注册）：

```python
@rule_handler("mil.supply_disruption_cascade")
def handle_supply_disruption(shock: ExternalShock, state: StateSnapshot) -> list[OutcomeDelta]:
    affected_units = find_units_on_supply_line(state, shock.target_id)
    deltas = []
    for unit in affected_units:
        severity = calculate_disruption_severity(unit, shock)
        deltas.append(OutcomeDelta(
            target=unit.id,
            field="logistics_throughput",
            op="multiply",
            value=1.0 - severity,
        ))
    return deltas
```

#### 3.4.5 DecisionPolicy 选择器

- 输入：所有 Actor 的 CandidateAction 列表
- 冲突检测：标记修改同一资源的动作对
- 选择策略：当前实现为单 Actor 单动作选择（每个 tick 选取 score 最高的动作），不涉及多 Actor 冲突解决
- 冲突解决规则：当前为单 Actor 模型，不存在多 Actor 资源竞争
- 输出：选定的 Action 列表 + 被拒绝的 Action 列表（含拒绝原因）

### 3.5 双领域包（Domain Pack）注册机制

领域包通过抽象基类 + 自动扫描注册，内核不硬编码任何领域语义。新增领域只需添加子包，零修改内核代码。

#### DomainPack 抽象接口

```python
class DomainPack(ABC):
    @property
    @abstractmethod
    def domain_id(self) -> str: ...

    @property
    @abstractmethod
    def entity_types(self) -> list[EntityTypeSpec]: ...

    @property
    @abstractmethod
    def state_fields(self) -> list[StateFieldSpec]: ...

    @property
    @abstractmethod
    def action_library(self) -> list[ActionSpec]: ...

    @property
    @abstractmethod
    def event_types(self) -> list[EventTypeSpec]: ...

    @property
    @abstractmethod
    def actor_templates(self) -> list[ActorTemplate]: ...

    def rules_dir(self) -> Path:
        return Path(f"rules/{self.domain_id}")
```

#### 企业领域包（CorporateDomainPack）

**15 个状态字段：**

| 字段 | 含义 |
|------|------|
| `cash` | 现金储备 |
| `runway_weeks` | 资金跑道（周） |
| `infra_cost_index` | 基础设施成本指数 |
| `delivery_velocity` | 交付速度 |
| `brand_index` | 品牌指数 |
| `market_share` | 市场份额 |
| `team_morale` | 团队士气 |
| `pipeline` | 销售管线 |
| `active_deployments` | 活跃部署数 |
| `implementation_capacity` | 实施能力 |
| `support_load` | 客户支持负载 |
| `reliability_debt` | 可靠性技术债 |
| `gross_margin` | 毛利率 |
| `nrr` | 净收入留存率 |
| `churn_risk` | 流失风险 |

**8 个动作：** hire、optimize_cost、ship_feature、raise_price、focus_vertical、tighten_scope、improve_reliability、monitor

**2 个演员模板：** `ai_model_provider`（AI 模型提供商）、`developer_tools_saas`（开发者工具 SaaS）

#### 军事领域包（MilitaryDomainPack）

**19 个状态字段：**

| 字段 | 含义 |
|------|------|
| `readiness` | 战备状态 |
| `ammo` | 弹药 |
| `fuel` | 油料 |
| `isr_coverage` | ISR（情报/监视/侦察）覆盖 |
| `ew_control` | 电子战控制 |
| `air_defense` | 防空 |
| `logistics_throughput` | 后勤吞吐 |
| `supply_network` | 补给网络 |
| `mobility` | 机动性 |
| `command_cohesion` | 指挥协同 |
| `objective_control` | 目标控制 |
| `recovery_capacity` | 恢复力 |
| `civilian_risk` | 平民风险 |
| `escalation_index` | 升级指数 |
| `ally_support` | 盟友支持 |
| `attrition_rate` | 消耗率 |
| `information_advantage` | 信息优势 |
| `enemy_readiness` | 敌方战备 |
| `enemy_pressure` | 敌方压力 |

**11 个动作：** redeploy、fortify、increase_isr、rebalance_air_defense、open_supply_line、commit_reserves、protect_civilians、deescalate_posture、secure_objective、suppress_enemy_fires、rotate_and_repair

**2 个演员模板：** `brigade`（旅级战斗队）、`air_defense_battalion`（防空营）

**军事域独有：敌方响应建模**——模拟敌方选择反制动作并计算火力平衡、目标态势变化、补给增量和恢复增量。

#### 场景模板示例

平台还提供了可复用的场景模板包，如 `examples/agent_startup/` 下的企业级 Agent 创业场景，包含：
- 证据采集配置
- 基线推演配置
- 基线 / 乐观 / 悲观三种分支场景
- 一键预设 API：`POST /presets/agent-startup/runs`

### 3.6 场景分支与 What-If 分析

#### 分支机制

Baseline 先完整推演，再在**高影响拐点**进行分支：

**拐点识别条件：**
- 高影响外部事件到达
- 关键资源阈值跌破
- 连续 KPI 恶化
- 新参与者进入
- 合作 / 制裁 / 打击 / 事故触发

**分支搜索参数：**
- `depth` 默认 2，最大 3（分支深度）
- `beam_width` 默认 3，最大 5（束搜索宽度）
- 排序分数 = `plausibility × impact × survivability × explainability`

**分支输出字段：**
- `branch_id`、`parent_id`、`fork_step`
- `assumptions`（假设列表）
- `decision_deltas`（决策差异）
- `kpi_trajectory`（KPI 轨迹）
- `probability_band`（概率区间）
- `notable_events`（重要事件）
- `evidence_summary`（证据摘要）

#### 纯函数分支比较

`simulation_branching.py` 将分支评分逻辑提取为**无副作用的纯函数模块**：

- 每个状态字段都有完整的 `MetricPolicy`（首选方向、预警阈值、危险阈值）
- 企业域 9 个追踪指标、军事域 13 个追踪指标用于分支评分（`tracked_branch_metrics`），另有 14/19 个 MetricPolicy 定义用于状态告警
- `score_branch_delta()` 对所有指标的归一化偏差求和
- `summarize_branch_trajectory()` 按绝对分数排序生成人类可读摘要

#### 地理资产生成

军事推演自动为部队生成带真实经纬度偏移的地理资产：

- 补给枢纽（supply_hub）
- 桥梁（bridge）
- 防空阵地（air_defense_site）
- 侦察节点（isr_node）
- 指挥所（command_post）

所有资产基于战区基准坐标 + 随机偏移生成，支持 `GET /runs/{run_id}/geo-assets` 和 `GET /runs/{run_id}/geojson` 导出。

### 3.7 多模型辩论机制（Model Debate Protocol）

辩论机制是项目中**最具创新性的架构设计之一**——引入对抗性并行推理，多个模型同时针对同一问题给出独立判断，通过结构化辩论轮次暴露盲点、消除偏见，最终由仲裁者基于论据质量（而非模型身份）做出裁决。

#### 辩论角色

| 角色 | 职责 | 配置目标 |
|------|------|---------|
| Advocate（正方） | 论证命题成立 | `debate_advocate` → 回退 `primary` |
| Challenger（反方） | 挑战命题，寻找反例和漏洞 | `debate_challenger` → `extraction` → `primary` |
| Arbitrator（仲裁） | 基于论据质量裁决，不参与辩论 | `debate_arbitrator` → `report` → `primary` |

> 模型分配通过 OpenAI 配置路由，非硬编码。每个角色可独立配置不同的 API 端点和模型。

#### 辩论协议（2 轮辩论 + 仲裁裁决）

```
Round 1：Advocate 和 Challenger 并行调用，各自独立给出立场，互不可见
    ↓
Round 2：各自看到对方 Round 1 论点后反驳 + 补充，可修正立场、可让步
    ↓
Arbitrator 裁决：基于两轮论据质量做出最终裁决 → DebateVerdictRecord
```

> LLM 路径执行完整的 2 轮辩论 + 仲裁；启发式回退路径简化为 2 轮（正方+反方 → 仲裁）。

#### 5 种触发场景

| 场景 | 触发条件 | 辩论焦点 |
|------|---------|---------|
| 证据可信度评估 | Claim 的 confidence 在 0.45-0.70 灰区 | 该 Claim 是否应进入推演主链 |
| 冲突证据裁决 | 同一实体存在矛盾 Claim（confidence 差值 < 0.2） | 哪条 Claim 更可信 |
| 推演拐点决策 | 规则引擎产出 ≥ 3 个 score 接近的 CandidateAction | 应选择哪个动作方向 |
| 场景分支评估 | top-3 分支 score 差距 < 10% | 哪些分支值得保留展开 |
| 报告结论挑战 | 报告生成后的最终质量关卡 | 结论是否被证据充分支撑 |

#### 裁决输出

裁决通过 `DebateVerdictRecord`（SQLAlchemy ORM 模型）持久化到 `debate_verdicts` 表：

| 字段 | 类型 | 说明 |
|------|------|------|
| `debate_id` | PK, FK → debate_sessions | 关联辩论会话 |
| `topic` | Text | 辩论主题 |
| `trigger_type` | String(64) | 触发场景类型 |
| `rounds_completed` | Integer | 实际完成轮数 |
| `verdict` | String(32) | ACCEPTED / REJECTED / CONDITIONAL / SPLIT |
| `confidence` | Float | 裁决置信度 |
| `winning_arguments` | JSON | 胜出论点列表 |
| `decisive_evidence` | JSON | 决定性证据 ID 列表 |
| `conditions` | JSON, nullable | 附加条件 |
| `minority_opinion` | Text, nullable | 少数意见 |

#### 辩论与各层集成

- **证据层**：confidence 0.45-0.70 的 Claim 若存在冲突 Claim → 触发辩论；无冲突 → 进入人工审核队列
- **推演层**：最高 score 动作 > 70 且领先第二名 > 20 → 直接选择；否则 → 触发辩论
- **分支层**：top-1 与 top-2 的 score 差距 ≤ 10% → 触发辩论决定保留哪些分支
- **报告层**：报告草稿 top-3 关键结论各触发一次辩论挑战

#### LLM 优先 + 启发式回退

辩论服务实现了双路径评估：
1. **LLM 路径**：通过 `openai_service.generate_debate_position()` 调用不同目标的 LLM 生成辩论立场
2. **启发式回退**：当 LLM 不可用时，使用 Jaccard token 相似度 + 方向关键词（正向如 "increase/growth"，负向如 "decline/risk"）进行启发式评估

每个辩论结果还会自动通过 `_ensure_debate_prediction()` 产生预测假设，进入校准闭环。

### 3.8 假设校准闭环（Calibration Loop）

这是项目**最核心的创新架构**——形成自动化预测市场与自校准反馈闭环。

#### 闭环流程

```
推演执行 → 产出 DecisionOption + Hypothesis（预测假设）
    ↓
假设带有时间窗口（如 3_months）
    ↓
CalibrationWorker 定期检查到期假设
    ↓
搜索新证据验证假设（token overlap ≥ 0.15）
    ↓
判定结果：CONFIRMED / PARTIAL / REFUTED
    ↓
聚合 CalibrationRecord（按领域）
    ↓
计算每条规则的历史精度
    ↓
反馈到 RuleRegistry 校准权重
    ↓
未来推演使用更新后的权重 → 更准确
```

#### `CalibrationWorker` 三阶段执行

**阶段 1 — 验证待定假设：**
- 扫描所有 `PENDING` 状态且超过时间窗口的 `Hypothesis` 记录
- 通过 token overlap 搜索匹配的新证据
- 验证阈值：
  - 相似度 ≥ 0.35 → `CONFIRMED`
  - 相似度 ≥ 0.20 → `PARTIAL`
  - 相似度 < 0.20 → `REFUTED`

**阶段 2 — 聚合校准记录：**
- 按领域分组已验证假设
- 计算校准分数：`(confirmed + 0.5 × partial) / total`
- 持久化 `CalibrationRecord`，其 `rule_accuracy` 字段为 `dict[str, float]`，映射每条规则的 ID 到其历史决策准确率

**阶段 3 — 计算规则精度并反馈：**
- 将 `DecisionRecord` 通过 `run_id` 关联到 `Hypothesis`
- 计算每条规则（`policy_rule_ids`）的历史决策准确率
- 合并近期校准记录的规则精度
- 调用 `rule_registry.apply_calibration()` 更新权重

#### 规则自适应机制

`RuleRegistry.apply_calibration()` 使用**指数移动平均 EMA（40/60 混合）**漂移规则权重：

| 规则精度 | 权重调整 | 效果 |
|---------|---------|------|
| ≥ 0.75（高精度） | 增强至 1.3× | 高精度规则在推演中被优先触发 |
| 0.35 ~ 0.75（正常） | 线性插值 | 保持现有权重 |
| ≤ 0.35（低精度） | 抑制至 0.6× | 低精度规则在推演中被降权 |

这创造了一个**自动纠正的反馈循环**：系统越推演，规则越准确。

#### 前端校准可视化

Dashboard 页面展示完整的校准计分板：
- 预测总数 / 已确认 / 已驳回 / 待验证
- Brier Score 校准分数
- 对比人类基线的提升幅度（Lift over human baseline）
- Source Reputation 信源声誉排名（每个信源的 confirmed / refuted 计数）——声誉计算实现在 `admin.py` 的 `POST /calibration/compute` 端点中，`reputation.py` 提供辅助函数如 `due_at_for()`

### 3.9 多模型自助复验迭代引擎（Jarvis 集成）

Jarvis 当前实现是一个轻量级的多目标验证编排器，核心代码位于 `src/mingjian/services/jarvis.py`。它不会引入额外的修复循环、人工仲裁状态机或外部 Profile 配置，而是根据任务类型选择一组 LLM target，对这些 target 发起验证调用，并汇总执行结果。

#### 固定状态路径

`STATE_PATH` 是一条固定的顺序路径，用于描述 Jarvis 任务的阶段元数据：

```
INIT → INGEST → EXTRACT → ANALYZE → SIMULATE → DEBATE → DONE
```

当前代码没有实现 `IMPLEMENTING → SELF_REVIEWING → CROSS_MODEL_REVIEWING → ARBITRATING → REPAIRING → REVERIFYING` 这类复杂状态机，也没有多轮修复或人工审核分支。`JarvisOrchestrator.orchestrate()` 创建 `JarvisResult` 后，将上述 `STATE_PATH` 写入结果，并按任务路由执行对应 target。

#### 任务路由

Jarvis 使用代码内置的 `TASK_ROUTES` 决定不同任务类型需要调用哪些 target：

| 任务类型 | target 列表 |
|---------|-------------|
| `analysis` | `primary` |
| `extraction` | `extraction` |
| `x_search` | `x_search` |
| `report` | `report` |
| `debate` | `debate_advocate`、`debate_challenger`、`debate_arbitrator` |
| `full_pipeline` | `primary`、`extraction`、`x_search`、`report`、`debate_advocate`、`debate_challenger`、`debate_arbitrator` |

如果传入未知 `task_type`，默认只路由到 `primary`。provider 与 model 不是由 YAML Profile 指定，而是通过 `Settings` 中的 `openai_{target}_provider` 和 `resolved_openai_{target}_model` 动态读取。

#### 7 维验证维度

`VALIDATION_DIMENSIONS` 当前包含 7 个维度，作为结果元数据返回：

| 维度 | 说明 |
|------|------|
| `source_coverage` | 跨平台信源完整性 |
| `evidence_quality` | 声明置信度与来源深度 |
| `simulation_fidelity` | tick 真实性与规则覆盖度 |
| `debate_rigor` | 多轮辩证质量 |
| `prediction_calibration` | 相对人类基线的 Brier Score 校准 |
| `response_latency` | 端到端流水线速度 |
| `cost_efficiency` | 单位决策质量输出的 token 成本 |

这些维度没有单独权重表，也没有 10 维需求覆盖 / 代码质量 / 场景逻辑等验证配置。

#### 执行与评分

每个 target 会生成一个 `validate_{target}` step。若该 target 未配置，step 状态为 `skipped`，并返回 `Target {target} not configured`；若调用失败，step 状态为 `failed`；调用成功则状态为 `success`，输出为模型返回的 JSON。

最终评分由成功和失败数量直接聚合：

| 条件 | `status` | `verdict` | `pass_score` |
|------|----------|-----------|--------------|
| 没有任何成功 step | `FAILED` | `FAIL` | `0` |
| 存在失败 step，且至少一个成功 step | `PARTIAL` | `CONDITIONAL_PASS` | `max(40, int(88 * success / total))` |
| 全部成功 | `COMPLETED` | `PASS` | `88` |

因此当前通过分是 `88`，不是 `80`；`critical_issues` 等于失败 step 数量。

#### Prompt 构造方式

Jarvis 没有读取外部 prompt 文件。`_execute_target()` 在代码中内联构造 system prompt：

```text
You are Jarvis orchestration. Validate {target} stage for '{task_type}'.
Respond JSON: {"status":"ok|warn|fail","findings":[],"recommendations":[]}
```

user content 取自 `payload.query` 或 `payload.topic`，并截断到 2000 字符。模型调用通过 `OpenAIService.generate_json_for_target()` 完成，最大输出 token 为 500。

### 3.10 战略助手（Strategic Assistant）

战略助手是平台的顶层编排器，将分析 → 采集 → 推演 → 辩论 → 报告链路为一个**流式工作流**。

#### 流式管道

`StrategicAssistantService.stream()` 返回 `AsyncIterator[AssistantEvent]`，前端通过 SSE 实时接收每个阶段的进展：

```
Step 1: 流式分析（12 源并行采集 + LLM 综合）
    ↓ 事件：step / source / result
Step 2: 创建 IngestRun（证据入库）
    ↓ 事件：ingest
Step 3: 创建 SimulationRun（推演执行）
    ↓ 事件：simulation
Step 4: 触发辩论（推演结果评估）
    ↓ 事件：debate
Step 5: 构建工作台视图（聚合所有数据）
    ↓ 事件：workbench
Step 6: 生成面板讨论（虚拟董事会）
    ↓ 事件：discussion
Step 7: 持久化会话和运行快照
    ↓ 事件：done
```

#### "虚拟董事会"面板讨论（Panel Discussion）

这是战略助手最具特色的功能——生成一个由 4 个 LLM 视角组成的虚拟决策会议：

| 角色 | 关注点 | stance 标签 |
|------|--------|------------|
| 首席战略官（Lead Strategist） | 综合战略视角 | `support` |
| 证据审计官（Evidence Auditor） | 质疑证据充分性 | `monitor` |
| 社会脉搏分析师（Social Pulse） | 对抗性外部信号挑战 | `challenge` |
| 作战规划官（Operations Planner） | 执行可行性 | `support` |

> 当 LLM 不可用时，系统降级为仅生成 3 个角色（Lead Strategist、Evidence Auditor、Operations Planner）的启发式评估。

每个角色使用不同 LLM 目标、不同立场、不同置信度，输出结构化的 `PanelDiscussionMessageRead`（含 stance / summary / key_points / recommendation / confidence）。

#### 自动领域识别

从用户输入文本中自动推断领域：
- 包含"旅""营""补给线""防空""战区"等关键词 → 军事域
- 包含"创业""SaaS""融资""市场份额"等关键词 → 企业域
- 无法识别时默认 `auto` 模式

#### 智能模板选择

根据市场关键词自动选择推演模板：
- "enterprise-agents" / "AI startup" → `developer_tools_saas`
- "GPU" / "foundation models" → `ai_model_provider`
- "brigade" / "military" → `brigade`

#### 时区感知的自动刷新

每个战略会话可配置：
- `refresh_timezone`：独立时区
- `refresh_hour_local`：本地刷新时间（默认 9:00）
- `next_refresh_at`：精确计算的下次刷新时间戳

`StrategicWatchWorker` 定期检查到期会话，自动执行 `daily_brief()` 生成每日战略简报。

### 3.11 规则监控与自动触发（Watch Rule）

用户可配置自动化监控规则，系统定期轮询并自动执行完整的情报 → 推演 → 辩论链路。

#### WatchRule 模型

```python
class WatchRule:
    name: str                    # 规则名称
    domain_id: str               # 域标识
    query: str                   # 查询文本
    source_types: list[str]      # 指定数据源
    keywords: list[str]          # 匹配关键字
    exclude_keywords: list[str]  # 排除关键字
    entity_tags: list[str]       # 实体标签（第三匹配维度，优先于 query 拆词）
    trigger_threshold: float     # 触发阈值（评分）
    min_new_evidence_count: int  # 最少新证据数
    importance_threshold: float  # 重要性阈值
    poll_interval_minutes: int   # 轮询间隔（分钟）
    auto_trigger_simulation: bool  # 自动触发推演
    auto_trigger_debate: bool    # 自动触发辩论
    lease_owner: str | None      # 分布式 Worker 协调：当前持有租约的 Worker ID
    lease_expires_at: datetime | None  # 分布式 Worker 协调：租约过期时间
```

#### 关键字评分机制

```
基础分 = 0.35
+ 匹配关键字（每个 0.18，上限 0.45）
+ 互动量加成（engagement bonus，+0.1）
+ 发布时间加成（publication date bonus，+0.1）
- 排除关键字命中 → 归零
```

当源数量和最高评分达到阈值时，自动触发推演和辩论。

### 3.12 统一工作台（Workbench）

`GET /runs/{run_id}/workbench` 返回一次推演运行的完整聚合视图：

| 组件 | 说明 |
|------|------|
| Review Queue | 待审核证据/声明队列 |
| Evidence Graph | 知识图谱节点和边 |
| Timeline | 按 tick 标记的事件时间线 |
| Geo Map | 地理资产分布（经纬度 + 属性） |
| Scenario Tree | 分支场景树结构 |
| Decision Trace | 完整决策链（why_selected + evidence_ids + policy_rule_ids） |
| KPI Comparator | 多分支指标对比数据 |
| Startup KPI Pack | 企业创业场景专用计分卡（含 10 个派生 KPI：Design Partner Capacity、ROI Proof、Deployment Window 等，按 good/watch/risk 三级分级） |
| Debate Records | 该运行关联的所有辩论记录 |

### 3.13 报告生成

报告在推演完成后自动生成，结构固定包含：

| 章节 | 内容 |
|------|------|
| 执行摘要 | 一句话结论 + 关键指标 |
| 证据摘要 | 引用的证据列表与摘要 |
| 时间线 | 按 tick 排列的事件序列 |
| 当前信号 | 最新的 Signal / Event / Trend |
| 地图视图 | GeoAsset 空间分布 |
| 场景树 | 分支结构与概率区间 |
| 决策链 | 每个 tick 的 DecisionRecord（含完整 why 链） |
| 场景对比 | 多分支 KPI 轨迹对比 |
| 领先指标 | 可能预示变化的早期信号 |
| 策略建议 | 基于推演结果的行动建议 |
| **Why This Happened** | **关键证据 + 命中的规则 + 采取的动作 + 导致的指标变化** |

"**Why This Happened**" 是报告中最重要的创新章节——它将决策过程完全透明化，展示从证据到结论的完整推理链。

报告输出格式：
- JSON payload（API 结构化数据）
- Markdown / HTML report（人类可读报告）
- Scenario replay package（场景回放包，可完整复现推演过程）

### 3.14 事件总线与 Worker 编排

#### EventBus Protocol 多态设计

```python
class EventBus(Protocol):
    async def publish(self, topic: str, payload: dict) -> str: ...
    async def consume(self, topic: str, group: str, count: int) -> list[ConsumedEvent]: ...
    async def ack(self, topic: str, group: str, message_id: str) -> None: ...
    async def publish_dead_letter(self, topic: str, payload: dict, error: str) -> str: ...
    async def close(self) -> None: ...
```

两个实现：
- **`InMemoryEventBus`**：进程内字典 + 集合实现，用于开发和测试
- **`RedisStreamEventBus`**：基于 Redis Streams（`XADD` / `XREADGROUP` / `XACK`），用于生产环境，支持 Approximate maxlen 裁剪

此外，`EventArchive` ORM 模型将关键事件（如 `debate.triggered`、`debate.completed`、`simulation.completed`、`report.generated` 等）持久化到 PostgreSQL `event_archive` 表，提供完整的事件审计轨迹。

同一事件总线接口在不同环境下零代码切换。

#### 双执行模式

采集与推演入口均支持 `ExecutionMode`：

```python
class ExecutionMode(StrEnum):
    INLINE = "INLINE"
    QUEUED = "QUEUED"
```

`INLINE` 模式在 API 请求内同步处理本次任务，请求返回时已经完成核心处理链路，适合开发、测试和单机调试。`QUEUED` 模式只创建运行记录并通过事件总线分发给 Worker，由后台进程异步消费，适合生产环境的水平扩展与故障隔离。默认模式由 `inline_ingest_default` 和 `inline_simulation_default` 控制，二者默认均为 `True`，可按部署环境切换为队列优先。

#### Worker 流式消费模式

Worker 同时支持两种运行方式：传统 poll 模式会按固定间隔调用 `run_once()` 扫描待处理任务；stream consumer 模式则根据 Worker 声明的 `consumes` 主题阻塞等待事件，再触发 `run_once()` 处理。`RedisStreamEventBus` 使用 Redis Streams 的 `XREADGROUP` 进行阻塞读取，天然支持 consumer group、ack 和多实例消费；`InMemoryEventBus` 提供同一接口的进程内实现，便于开发和测试。流式模式的批量大小与阻塞时间由 `stream_consumer_count`、`stream_consumer_block_ms` 配置。

#### Worker 依赖关系

```
ingest-worker ──→ knowledge-worker ──→ graph-worker
                     │
                     ├──→ simulation-worker ──→ report-worker
                     │
                     └──→ review-worker

watch-ingest-worker (独立轮询)
strategic-watch-worker (独立轮询)
calibration-worker (独立轮询)
```

#### Worker 故障策略

| 故障类型 | 策略 |
|---------|------|
| Worker 崩溃 | Consumer Group 自动将 pending 消息重分配给存活实例 |
| 处理失败 | 指数退避重试 3 次（1s / 4s / 16s），超限同时持久化到 Redis DLQ stream 和 `dead_letter_events` 数据库表 |
| 上游超时 | knowledge-worker 对单条处理设 60s 超时 |
| 背压 | pending 消息数 > 1000 时暂停采集 |
| 数据源不可用 | 连续 5 次失败标记源为 DEGRADED |

#### 乐观锁租约模式

所有 Worker 使用统一的乐观锁租约模式进行任务分配：

```sql
UPDATE table
SET lease_owner = :worker_id, lease_expires_at = :expires
WHERE id IN (
    SELECT id FROM table
    WHERE status = 'PENDING'
      AND (lease_owner IS NULL OR lease_expires_at < now())
    LIMIT :batch_size
    FOR UPDATE SKIP LOCKED
)
```

这保证了多实例 Worker 的安全水平扩展。

### 3.15 配置系统

#### 级联回退的多目标 OpenAI 配置

系统支持 7 个独立的 LLM 目标：

| 目标 | 用途 | 推荐模型 |
|------|------|---------|
| `primary` | 默认 / 测试 | GPT-5.x |
| `extraction` | 证据抽取 | Gemini |
| `x_search` | X/Twitter 搜索 | Grok |
| `report` | 报告增强 | Claude |
| `debate_advocate` | 辩论正方 | Claude |
| `debate_challenger` | 辩论反方 | Gemini |
| `debate_arbitrator` | 辩论仲裁 | Codex |

每个目标的 `api_key`、`base_url`、`model` 均支持**级联回退**：

```
debate_challenger.api_key
  → extraction.api_key
    → primary.api_key
      → OPENAI_API_KEY（环境变量）
```

#### 诊断溯源

配置系统提供三个诊断方法：
- `openai_model_source(target)` → 返回实际提供 model 值的环境变量名
- `openai_api_key_source(target)` → 返回实际提供 api_key 值的环境变量名
- `openai_base_url_source(target)` → 返回实际提供 base_url 值的环境变量名

通过 `GET /admin/openai/status` 可查看每个目标的实际配置来源，快速定位配置问题。

#### LLM Provider 抽象层

LLM 调用被隔离在 `services/providers/`，上层服务只依赖 `LLMProvider` 协议，不直接绑定具体厂商 SDK：

```python
class LLMProvider(Protocol):
    provider_name: str
    is_configured: bool

    async def generate_text(...) -> LLMResponse | None: ...
    async def generate_json(...) -> tuple[LLMResponse | None, dict | None]: ...
    async def close() -> None: ...
```

`LLMResponse` 统一封装 `text`、`model`、`response_id`、`api_mode` 和 `usage`，使 OpenAI / Anthropic 的返回结构可以进入同一条后处理链路。`OpenAIProvider` 基于 `AsyncOpenAI` 和 Chat Completions 实现普通文本与 JSON 输出，JSON 模式使用 `response_format={"type": "json_object"}`。`AnthropicProvider` 基于 `AsyncAnthropic.messages.create()` 实现相同能力，结构化输出通过 JSON 指令与 schema 提示约束，并对 Markdown 代码块包裹进行清理后解析。

这层抽象让系统可以在不改业务服务的情况下替换模型供应商；当 provider 未配置、SDK 不存在或调用失败时，方法返回 `None`，由上层继续走启发式降级路径。

---

## 4. 创新性架构总结

### 创新 1：自校准反馈闭环

```
推演 → 预测假设 → 自动验证 → 规则权重调整 → 推演精度提升
      ↑                                          |
      └────────────── 反馈闭环 ←────────────────┘
```

整个系统形成了一个**自动化预测市场**，推演结果产生的预测假设会被自动校准，校准结果反向修正规则引擎的权重。使用指数平滑（40/60 混合）实现渐进式权重漂移。这是传统仿真系统不具备的自进化能力。

### 创新 2：对抗性多模型辩论

不是简单的"多个模型投票"，而是**结构化的对抗性推理**：
- 正方和反方并行独立推理（互不可见），消除信息锚定效应
- 交叉反驳阶段暴露各自论点的漏洞
- 独立仲裁者基于论据质量（而非模型身份）做出裁决
- 支持 5 种触发场景，覆盖从证据评估到报告挑战的全链路
- 辩论结果自动产生预测假设，进入校准闭环

### 创新 3：Actor 三级降级决策

```
Level 1 (规则引擎) → Level 2 (LLM 辅助) → Level 3 (随机加权)
```

保证系统在任何条件下（LLM 不可用、网络中断、配置缺失）都能正常运行，同时在有条件时自动提升推理质量。所有降级操作都记录在 `DecisionRecord.decision_method` 字段中，确保完全透明。

### 创新 4：零依赖确定性向量嵌入

使用 SHA-256 哈希实现的向量嵌入方案：
- 无需调用任何外部 embedding 模型
- 结果完全确定性可复现
- 双引擎搜索：PostgreSQL CTE（生产）/ Python（开发）

### 创新 5：虚拟董事会面板讨论

4 个 LLM 分别扮演战略角色（首席战略官、证据审计官、社会脉搏分析师、作战规划官），各自独立分析后形成结构化的"董事会意见"，模拟真实决策场景中的多维视角碰撞。

### 创新 6：双路径 LLM 回退架构

系统中**每一个涉及 LLM 的环节**（辩论、分析、推演决策、报告生成）都实现了 LLM 优先 + 启发式兜底的双路径设计：
- OpenAI 可用时 → LLM 高质量推理
- OpenAI 不可用时 → 自动降级到确定性启发式方法
- 降级行为完全透明，记录在输出元数据中

### 创新 7：Protocol 多态事件总线

```python
class EventBus(Protocol): ...
class InMemoryEventBus: ...    # 开发 / 测试
class RedisStreamEventBus: ... # 生产
```

使用 Python Protocol 定义接口，内存实现用于开发/测试，Redis Streams 用于生产。**零代码切换，零配置改动**。

### 创新 8：声明式领域扩展

```python
class DomainPack(ABC):
    domain_id: str
    entity_types: list[EntityTypeSpec]
    state_fields: list[StateFieldSpec]
    action_library: list[ActionSpec]
    event_types: list[EventTypeSpec]
```

新领域（如金融、能源、供应链）只需：
1. 在 `domain_packs/` 下添加子包
2. 实现 `DomainPack` 抽象类
3. 定义 YAML 规则文件

**内核代码零修改**，自动扫描注册。

---

## 5. 前端可视化

### 5.1 技术选型

- Next.js 15 + React 19 + TypeScript
- SWR 数据获取与自动刷新
- SSE（Server-Sent Events）流式数据
- 纯 CSS 可视化（无外部图表库依赖）

### 5.2 五大页面

#### Dashboard（仪表盘）
- SWR 自动刷新：会话 30s / 计分板 60s / 队列 15s / 监控规则 30s
- 核心指标卡片：活跃会话数、预测精度（含 Brier Score）、队列健康度、监控规则数
- 预测计分板：总数 / 已确认 / 已驳回 / 待验证 / 对比人类基线
- 战略会话列表

#### Strategic Assistant（战略助手）
- 三栏布局：任务输入（左）| 实时推理 + 结果（中）| 面板讨论 + 辩论追踪（右）
- SSE 实时流式更新：步骤事件、源事件、讨论事件、辩论轮次、最终结果
- 中止控制器支持取消长时间运行的任务
- 面板讨论卡片带颜色编码立场（支持/绿、挑战/红、监控/黄）

#### Simulation（推演中心）
- 双栏布局：运行列表（左）| 工作台详情（右）
- 自定义 `StateChart` 组件：CSS 定位柱状图展示 KPI 偏差（绿色正值、红色负值、中心基线）
- 工作台展示：KPI 对比图表、时间线、地理资产

#### Debate Center（辩论中心）
- 按 ID 查找辩论
- 裁决展示：结果、置信度百分比、获胜论点、少数意见
- 多轮辩论追踪：按轮次分组，三色卡片展示（正方绿 / 反方红 / 仲裁紫），含论点和反驳

#### Intelligence（情报中心）
- 5 个标签页：
  - **Evidence**：证据表格，标题/摘要/彩色置信度
  - **Claims**：声明表格，声明/置信度/状态标签（ACCEPTED/REJECTED/PENDING_REVIEW）
  - **Knowledge Graph**：搜索框 + 实时结果，节点/边计数，节点卡片网格
  - **Source Reputation**：排序表格，声誉分数/已确认/已驳回计数
  - **Calibration**：计分板，总假设数/精度/Brier Score/对比人类基线

---

## 6. 技术栈

| 层次 | 技术 |
|------|------|
| 后端框架 | FastAPI + SQLAlchemy (async ORM) |
| 前端框架 | Next.js 15 + React 19 + TypeScript |
| 数据库 | PostgreSQL + pgvector（向量检索）+ PostGIS（空间数据） |
| 数据库连接池 | pool_size=20, max_overflow=10, pool_recycle=300（可在 `db_pool_size` / `db_max_overflow` / `db_pool_recycle` 配置项中覆盖） |
| 缓存 / 事件 | Redis Streams（事件总线）+ Redis String（缓存/信号） |
| 对象存储 | MinIO / 本地文件系统（可切换） |
| LLM 集成 | OpenAI Responses API + 多厂商回退（Anthropic / Google Gemini / xAI Grok） |
| 配置管理 | Pydantic Settings + 级联回退 + 诊断溯源 |
| 容器化 | Docker Compose（8+ 服务编排） |
| 数据库迁移 | Alembic（17 个版本迁移脚本） |
| ID 生成 | UUID v7（含时间戳） |
| 前端数据获取 | SWR（自动刷新 + 缓存） |
| 流式通信 | Server-Sent Events (SSE) |

#### 双 Docker Compose 部署拓扑

项目提供两个编排文件，面向不同场景：

| 文件 | 场景 | Worker 拓扑 | 数据库 | 特点 |
|------|------|------------|--------|------|
| `compose.yml` | 开发/测试 | 9 个独立 Worker 进程 | PostgreSQL (标准) | 每个 Worker 独立扩缩、独立日志 |
| `docker-compose.yml` | 生产部署 | 合并 Worker + Frontend | pgvector/pgvector:pg16 | 含健康检查、前端构建、pgvector 镜像 |

开发环境使用 `compose up` 启动全栈；生产环境使用 `docker-compose.yml`，Worker 合并为单容器以减少资源占用。

#### 测试策略

项目包含 9 个测试文件，覆盖所有核心阶段：

| 测试文件 | 覆盖范围 |
|---------|---------|
| `test_phase1_api.py` | 证据采集、审核队列、Worker 联动 |
| `test_phase2_simulation_api.py` | 企业推演、场景分支、创业预设 |
| `test_phase3_military_api.py` | 军事推演、地理资产、外部冲击 |
| `test_phase4_workbench_and_debates.py` | 工作台、辩论、规则热加载 |
| `test_simulation_action_selection.py` | 动作选择、规则匹配、LLM 降级 |
| `test_analysis_api.py` | 分析端点、缓存、健康检查 |
| `test_analysis_x_search.py` | X/Twitter 搜索集成 |
| `test_strategic_assistant.py` | 战略助手会话、每日简报 |
| `test_new_features.py` | LLM 决策、辩论、假设、校准 |

测试模式：SQLite 内存数据库 + `InMemoryEventBus` + `TestClient` 集成测试，LLM 调用通过 monkeypatch 禁用或 mock。所有测试通过 `pytest-asyncio` 的 `auto` 模式运行异步用例。

---

## 7. 实施阶段

| 阶段 | 内容 | 状态 |
|------|------|------|
| Phase 1 | 证据核心与最小审核队列 | 已完成 |
| Phase 2 | 企业域 MVP 与基础报告 | 已完成 |
| Phase 3 | 军事域 MVP 与前三种模式 | 已完成 |
| Phase 4 | 统一工作台与地图/决策链 | 已完成 |
| Phase 5 | 多模型复验引擎与 Jarvis profile 接入 | 已完成 |
| Phase 6 | 危机升级、训练教学、Replay package、Gym/RL adapter | 规划中 |

---

## 附录：API 端点清单（65+）

### 系统状态
- `GET /` — 根状态页（含 OpenAI 配置摘要）
- `GET /health` — 简单健康检查
- `GET /health/live` — 存活探针（含版本号）
- `GET /health/ready` — 就绪探针（检查 DB + Redis 连通性）
- `GET /console` — 战略控制台页面

### 情报采集
- `POST /ingest/runs` — 创建采集运行
- `POST /analysis` — 一次性分析（带缓存）
- `POST /analysis/stream` — 流式分析（实时事件）
- `GET /evidence` — 查询证据（分页）
- `GET /claims` — 查询声明（分页）
- `GET /signals` — 查询信号（分页）
- `GET /events` — 查询事件（分页）
- `GET /trends` — 查询趋势（分页）

### 推演
- `POST /simulation/runs` — 创建推演运行
- `POST /scenario/runs/{simulation_run_id}` — 创建场景分支
- `POST /runs/{run_id}/scenario-search` — 分支搜索
- `GET /runs/{run_id}/decision-trace` — 决策链
- `GET /runs/{run_id}/scenario-compare` — 场景对比
- `GET /runs/{run_id}/geo-assets` — 地理资产
- `GET /runs/{run_id}/geojson` — GeoJSON 导出
- `GET /runs/{run_id}/external-shocks` — 外部冲击
- `GET /runs/{run_id}/replay-package` — 回放包
- `GET /runs/{run_id}/startup-kpis` — 创业 KPI
- `GET /scenarios/{scenario_id}/reports/latest` — 场景报告

### 决策选项与假设
- `GET /runs/{run_id}/options` — 决策选项列表
- `POST /runs/{run_id}/options` — 生成决策选项
- `GET /hypotheses/scoreboard` — 假设计分板
- `GET /hypotheses` — 假设列表
- `POST /hypotheses/{id}/verify` — 验证假设
- `POST /calibration/compute` — 触发校准计算
- `GET /calibration` — 校准记录列表

### 工作台与报告
- `GET /runs/{run_id}/workbench` — 统一工作台
- `GET /companies/{company_id}/reports/latest` — 企业报告
- `GET /military/scenarios/{scenario_id}/reports/latest` — 军事报告

### 辩论
- `POST /debates/trigger` — 触发辩论
- `GET /debates/{debate_id}` — 查询辩论详情
- `GET /runs/{run_id}/debates` — 查询运行关联辩论

### 审核
- `GET /review/items` — 审核队列
- `POST /review/items/{id}/accept` — 接受审核项
- `POST /review/items/{id}/reject` — 拒绝审核项

### 战略助手
- `POST /assistant/sessions` — 创建会话
- `GET /assistant/sessions` — 列出会话
- `GET /assistant/sessions/{session_id}` — 会话详情
- `POST /assistant/daily-brief` — 每日简报
- `POST /assistant/runs` — 执行推演
- `POST /assistant/stream` — 流式战略推理

### 知识图谱
- `GET /knowledge/graph` — 完整图谱
- `GET /knowledge/search?q=...` — 图谱搜索

### 信源管理
- `GET /sources/health` — 信源健康状态
- `GET /sources/snapshots` — 信源快照
- `GET /sources/provider-contracts` — 外部 Provider 契约

### Watch Rules（规则监控）
- `GET /watch/rules` — 列出所有监控规则
- `POST /watch/rules` — 创建监控规则
- `GET /watch/rules/{rule_id}` — 查询单条规则
- `PUT /watch/rules/{rule_id}` — 更新规则
- `DELETE /watch/rules/{rule_id}` — 删除规则
- `POST /watch/rules/{rule_id}/events` — 推送事件到规则

### 预设与管理
- `POST /presets/agent-startup/runs` — Agent 创业场景一键预设
- `POST /admin/rules/reload` — 规则热加载
- `GET /admin/runtime/queues` — 运行时队列状态
- `GET /admin/analysis/cache` — 分析缓存状态
- `GET /admin/openai/status` — LLM 配置状态
- `POST /admin/openai/test` — LLM 连通性测试
- `POST /jarvis/runs` — Jarvis 运行记录
- `GET /jarvis/runs` — 查询 Jarvis 运行
- `GET /jarvis/profiles` — Jarvis 配置文件列表
- `POST /jarvis/test` — Jarvis 连通性测试

---

*文档版本：2026-04-29*
*项目版本：v0.1.0*
