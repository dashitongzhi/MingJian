# PlanAgent 完整实施计划（含双域推演与 Jarvis 编排）

## 摘要
构建一个"证据驱动、可解释、可复验"的统一推演平台：同一套内核同时支持公司/产业生态推演与军事/冲突推演，并通过 `Jarvis` 提供多模型计划、复验、修复和重试闭环。首版采用"模块化单体 + 异步 Worker"，先打通证据链、推演链和复验链，再逐步扩展地图、工作台和高级模式。

## 关键实现

### 1. 平台核心与数据流
- 运行拓扑固定为：`FastAPI control-api + ingest-worker + knowledge-worker + graph-worker + simulation-worker + review-worker + report-worker + Redis + PostgreSQL(pgvector+PostGIS) + MinIO`。
- 外部输入统一流转为：`RawSourceItem -> NormalizedItem -> EvidenceItem -> Claim -> Signal/Event/Trend -> ExternalShock -> DecisionRecord -> Report`。
- 首批数据源固定为：
  - 公司域：GitHub Trending/Releases/Issues/PR、Hacker News、Reddit、开发者论坛/RSS、官方博客/公告/融资新闻。
  - 军事域：RSS/新闻源、公开 OSINT 事件源、航空/海事公开流、天气/灾害源、官方声明/智库简报。
- 去重规则固定为：规范 URL + 标题/正文 hash + 近似标题相似度 + 时间窗口语义近重复。
- 置信度门槛固定为：
  - `>= 0.70` 进入推演主链
  - `0.45 - 0.70` 进入人工审核队列
  - `< 0.45` 仅留存检索

### 2. 核心类型、接口与内部主题
- 主类型固定为：`RawSourceItem`、`NormalizedItem`、`EvidenceItem`、`Claim`、`Entity`、`Relationship`、`Signal`、`Event`、`Trend`、`GeoAsset`、`CompanyProfile`、`ForceProfile`、`StateSnapshot`、`ExternalShock`、`DecisionRecord`、`ScenarioBranch`、`AnalystReview`、`GeneratedReport`、`DebateSession`、`DebateRound`、`DebateVerdict`。
- `DecisionRecord` 必须包含：`why_selected`、`evidence_ids`、`policy_rule_ids`、`expected_effect`、`actual_effect`。
- 控制面 API 固定为：
  - `POST /ingest/runs`
  - `GET /evidence`
  - `GET /claims`
  - `GET /signals`
  - `GET /events`
  - `GET /trends`
  - `POST /simulation/runs`
  - `POST /scenario/runs/{simulation_run_id}`
  - `GET /runs/{run_id}/decision-trace`
  - `GET /companies/{company_id}/reports/latest`
  - `GET /military/scenarios/{scenario_id}/reports/latest`
  - `POST /review/items/{id}/accept`
  - `POST /review/items/{id}/reject`
  - `GET /debates/{debate_id}`
  - `GET /runs/{run_id}/debates`
  - `POST /debates/trigger`
  - `POST /admin/rules/reload`
- 内部事件主题固定为：`raw.ingested`、`evidence.created`、`claim.review_requested`、`knowledge.extracted`、`simulation.completed`、`scenario.completed`、`report.generated`、`verification.failed`、`debate.triggered`、`debate.completed`。

### 3. Worker 编排与故障策略

#### Worker 依赖关系
- `ingest-worker`: 无上游依赖；监听定时调度或 `POST /ingest/runs`；产出 `raw.ingested` 事件。
- `knowledge-worker`: 监听 `raw.ingested`；产出 `evidence.created`、`claim.review_requested`、`knowledge.extracted`。
- `graph-worker`: 监听 `knowledge.extracted`；更新证据图谱关系表；无下游事件（被动查询）。
- `simulation-worker`: 监听 `knowledge.extracted` 或 `POST /simulation/runs`；产出 `simulation.completed`、`scenario.completed`。
- `review-worker`: 监听 `claim.review_requested`；人工操作后产出 `evidence.created`（升级）或标记驳回。
- `report-worker`: 监听 `simulation.completed` / `scenario.completed`；产出 `report.generated`。

#### 事件总线
- 使用 **Redis Streams**（非 Pub/Sub），每个主题一个 Stream key。
- 每个 Worker 使用 Consumer Group，支持多实例水平扩展。
- 消息确认使用 `XACK`；未确认消息在超时后自动重投（pending entries list）。
- 保留策略：`MAXLEN ~10000`（每个 Stream），历史事件归档到 PostgreSQL `event_archive` 表。

#### 故障与重试策略

| 故障类型 | 策略 |
|---------|------|
| Worker 崩溃 | Consumer Group 自动将 pending 消息重分配给存活实例 |
| 处理失败 | 指数退避重试 3 次（1s/4s/16s），超限进入 dead-letter stream `{topic}.dlq` |
| 上游超时 | knowledge-worker 对单条 NormalizedItem 设 60s 处理超时，超时标记 `TIMEOUT` 并跳过 |
| 背压 | 当 pending 消息数 > 1000 时，ingest-worker 暂停采集（backpressure signal via Redis key） |
| 数据源不可用 | ingest-worker 记录失败，下次调度重试；连续 5 次失败标记源为 `DEGRADED` |

### 4. Redis 职责与 PostgreSQL 索引策略

#### Redis 职责划分
Redis 承担三个独立职责，通过 key 前缀隔离：

| 职责 | Key 前缀 | 数据结构 | 说明 |
|------|---------|---------|------|
| 事件总线 | `stream:` | Redis Streams | 10 个事件主题，Consumer Group 消费 |
| 缓存 | `cache:` | String (TTL) | API 响应缓存、热点查询结果，TTL 5min |
| 协调信号 | `signal:` | String / Set | Worker 背压信号、分布式锁、采集游标 |

- 不使用 Redis 做持久化存储；所有持久数据在 PostgreSQL。
- Redis 配置 `maxmemory-policy allkeys-lru`，内存上限 2GB。

#### PostgreSQL Schema 与索引策略
- 使用单实例 PostgreSQL，双 schema 隔离：
  - `evidence` schema：证据链相关表（evidence_items, claims, signals, events, trends）。
  - `simulation` schema：推演相关表（state_snapshots, decision_records, scenario_branches, debate_sessions）。
- pgvector 索引：
  - 向量维度固定 1536（OpenAI embedding）或 1024（本地模型），建表时确定。
  - 索引类型：HNSW（`lists=100, m=16, ef_construction=200`），适合 < 500 万条记录的 MVP 阶段。
  - 向量列仅在 `evidence_items` 和 `claims` 表上，不在推演表上。
- PostGIS 索引：
  - `geo_assets` 表使用 `GEOMETRY(Point, 4326)` 类型 + GIST 索引。
  - 空间查询主要用于：范围搜索（ST_DWithin）、覆盖计算（ST_Covers）、路径分析（ST_MakeLine）。
- 分区策略：`evidence_items` 按 `created_at` 月分区（当数据量 > 100 万时启用）。

### 5. 统一推演内核与双领域包

#### 时间模型
- 推演采用**离散时间步（discrete tick）**模型，非事件驱动。
- 每个 tick 代表一个固定时间窗口，由 Domain Pack 定义：
  - 公司域默认：`1 tick = 1 week`（可配置为 1 day / 1 month）。
  - 军事域默认：`1 tick = 6 hours`（可配置为 1 hour / 24 hours）。
- tick 内事件处理顺序固定为：
  1. 注入本 tick 窗口内的 ExternalShock。
  2. 所有 Actor 并行提议 CandidateAction（无互相感知）。
  3. DecisionPolicy 按优先级排序、冲突解决、选择执行。
  4. 按选定动作顺序执行 OutcomeDelta。
  5. 生成 StateSnapshot 和 DecisionRecord。
- 冲突解决规则：当多个 Actor 修改同一资源时，按 `priority_score`（由规则计算）排序，高优先级先执行；若资源已耗尽，后续动作标记为 `BLOCKED`。
- 跨域推演（公司+军事混合场景）使用最细粒度 tick，粗粒度域在非活跃 tick 跳过处理。

#### 推演内核
- 推演内核固定为"规则驱动 + agent-based + 事件注入"，不绑定具体行业语义。
- 内核通用概念：`Actor`、`StateSnapshot`、`ExternalShock`、`CandidateAction`、`DecisionPolicy`、`OutcomeDelta`、`DecisionRecord`。
- 单步执行顺序固定为：读取窗口内 `Signal/Event/Trend` -> 映射 `ExternalShock` -> 各角色提议动作 -> 策略器选动作 -> 更新状态与 KPI -> 产出 `DecisionRecord`。
- 必须支持：固定 seed、全量事件日志、快照回放、A/B 场景比较。

#### 规则表示格式
- 规则采用 **YAML 声明式 + Python 函数** 双层结构：
  - **YAML 层**：声明触发条件、影响目标、参数范围，供非技术分析员编辑。
  - **Python 层**：复杂计算逻辑，通过 `@rule_handler` 装饰器注册。
- YAML 规则示例：
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
- Python 规则示例：
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
- 规则加载顺序：YAML 规则先加载为 `RuleSpec` 对象，Python handler 通过 `rule_id` 关联。
- 热加载：规则文件变更后，通过 `POST /admin/rules/reload` 触发重载，不需重启 Worker。
- 规则优先级：0-100，数字越大优先级越高；同优先级按注册顺序执行。

#### Actor 决策模型
Actor 的决策采用**三级降级策略**：

- **Level 1: 规则引擎（默认，确定性）**
  - 基于当前 StateSnapshot + ExternalShock，匹配 YAML/Python 规则。
  - 输出 CandidateAction 列表，每个附带 `score` 和 `rule_id`。
  - 优点：可解释、可复现、零 LLM 成本。
  - 适用：常规场景、训练教学模式、回归测试。
- **Level 2: LLM 辅助（可选，用于复杂推理）**
  - 当规则匹配结果为空或 score 均 < 30 时，触发 LLM 辅助。
  - 将当前状态 + 历史 3 步 DecisionRecord + 可用动作列表发给 LLM。
  - LLM 返回 JSON 格式的动作建议，附带 reasoning。
  - 模型路由：公司域 → Claude；军事域 → Claude（Codex/Gemini 不参与推演决策）。
  - token 预算：单次 Actor 决策 ≤ 2000 input + 500 output tokens。
  - 超时：10s，超时则降级到 Level 3。
- **Level 3: 随机加权（降级兜底）**
  - 从当前可用动作中按历史成功率加权随机选择。
  - 标记 `decision_method: "fallback_random"`，在报告中高亮提示。

#### DecisionPolicy 选择器
- 输入：所有 Actor 的 CandidateAction 列表。
- 冲突检测：标记修改同一资源的动作对。
- 选择策略：按 `score * actor_priority` 排序，贪心选择无冲突子集。
- 输出：选定的 Action 列表 + 被拒绝的 Action 列表（含拒绝原因）。

#### 领域包注册与扩展机制
领域包通过 Python 类 + YAML 配置注册，内核不硬编码任何领域语义：

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
    @abstractmethod
    def map_shock(self, event: Event, state: StateSnapshot) -> ExternalShock | None: ...
    @abstractmethod
    def default_actor_templates(self) -> list[ActorTemplate]: ...
    def rules_dir(self) -> Path:
        return Path(f"rules/{self.domain_id}")
```

- 注册方式：在 `domain_packs/` 目录下创建子包，内核启动时自动扫描并注册。
- 目录结构：
  ```
  domain_packs/
  ├── __init__.py
  ├── corporate/
  │   ├── pack.py
  │   ├── templates.yaml
  │   └── rules/
  └── military/
      ├── pack.py
      ├── entities.yaml
      └── rules/
  ```
- 新增领域（如 `financial`、`energy`）只需添加新子包，无需修改内核代码。

#### 公司领域包
- 模板：`AI model provider`、`AI application startup`、`developer tools SaaS`、`compute/infrastructure supplier`。
- 状态：现金、跑道、团队、基础设施成本、产品质量、交付速度、品牌、市场份额、定价、技术债、安全、士气、生态依赖。
- 动作：招聘、冻结招聘、涨价、降价、发功能、重构、买算力、优化成本、合作、融资、转向、营销、事故响应、开源策略、并购能力。
- 模式：市场竞争、产品演化、资本与跑道、生态位冲击。

#### 军事领域包
- 实体：部队单元、基地、补给线、ISR 节点、民用区域、作战目标。
- 状态：战备、弹药、油料、侦察覆盖、电子战控制、防空、后勤吞吐、机动、指挥协同、平民风险、升级指数、盟友支持、消耗率、信息优势。
- 事件：部队调动、打击、无人机蜂群、网络攻击、电子压制、补给中断、桥港损失、天气窗口、外交信号、卫星损失、空域侵犯、动员。
- 动作：重部署、加固、侦察增强、无人机试探、精确打击、反炮兵、防空重平衡、电子压制走廊、网络干扰、开辟补给线、投入预备队、降级姿态、平民保护、撤退迟滞。
- 模式：情报研判、战役对抗、后勤消耗、危机升级、训练教学。

#### 空间层
- 空间层固定为平台一级能力：
  - 公司域映射市场区、数据中心、供应链节点、社区传播路径。
  - 军事域映射战区网格、机场/港口/桥梁、补给线、防空覆盖圈、ISR 视域。
  - MVP 先做 2D 地图，3D 地球视图延后。

### 6. 场景分支、工作台与交付
- baseline 先跑完整，再在高影响拐点分支；拐点固定为：高影响外部事件、关键资源阈值跌破、连续 KPI 恶化、新参与者进入、合作/制裁/打击/事故触发。
- 分支搜索参数固定为：`depth = 3`、`beam width = 5`；排序分数 = `plausibility * impact * survivability * explainability`。
- 分支输出字段：`branch_id`、`parent_id`、`fork_step`、`assumptions`、`decision_deltas`、`kpi_trajectory`、`probability_band`、`notable_events`、`evidence_summary`。
- 平台模式固定为：`Monitoring`、`Analyst Review`、`Simulation`、`Branch Compare`、`Replay & Training`。
- 分析员工作台固定包含：`Review Queue`、`Evidence Graph`、`Timeline`、`Geo Map`、`Scenario Tree`、`Decision Trace`、`KPI Comparator`、`Debate Records`。
- 报告输出固定为：`JSON payload`、`Markdown/HTML report`、`Scenario replay package`。
- 报告结构固定包含：执行摘要、证据摘要、时间线、当前信号、地图视图、场景树、决策链、场景对比、领先指标、策略建议、`Why This Happened`。
- `Why This Happened` 必须展示：关键证据、命中的规则、采取的动作、导致的指标变化。

### 7. 多模型辩论机制（Model Debate Protocol）

辩论机制引入**对抗性并行推理**：多个模型同时针对同一问题给出独立判断，通过结构化辩论轮次暴露盲点、消除偏见，最终由仲裁者基于论据质量而非模型身份做出裁决。

#### 辩论适用场景

| 场景 | 触发条件 | 辩论焦点 |
|------|---------|---------|
| 证据可信度评估 | 单条 Claim 的 confidence 在 0.45-0.70 灰区 | 该 Claim 是否应进入推演主链 |
| 冲突证据裁决 | 同一实体/事件存在矛盾 Claim（confidence 差值 < 0.2） | 哪条 Claim 更可信，或两者如何调和 |
| 推演拐点决策 | 高影响 ExternalShock 到达，且规则引擎产出 >= 3 个 score 接近的 CandidateAction | 应选择哪个动作方向 |
| 场景分支评估 | 分支搜索产出的 top-3 分支 score 差距 < 10% | 哪些分支值得保留展开 |
| 报告结论挑战 | 报告生成后的最终质量关卡 | 结论是否被证据充分支撑 |

#### 辩论协议
```yaml
debate_protocol:
  max_rounds: 3
  min_rounds: 1
  early_stop: true
  consensus_threshold: 0.85
  roles:
    - id: "advocate"
      description: "正方：论证命题成立"
      default_model: "claude"
    - id: "challenger"
      description: "反方：挑战命题，寻找反例和漏洞"
      default_model: "gemini"
    - id: "arbitrator"
      description: "仲裁：基于论据质量裁决，不参与辩论"
      default_model: "codex"
  output_schema:
    position: "SUPPORT | OPPOSE | CONDITIONAL"
    confidence: 0.0-1.0
    arguments:
      - claim: "论点摘要"
        evidence_ids: ["引用的证据 ID"]
        reasoning: "推理过程"
        strength: "STRONG | MODERATE | WEAK"
    rebuttals:
      - target_argument_idx: 0
        counter: "反驳内容"
        evidence_ids: []
    concessions:
      - argument_idx: 0
        reason: "为什么承认"
```

#### 辩论执行规则
- Round 1：Advocate 和 Challenger 并行调用，各自独立给出立场，互不可见。
- Arbitrator 评估共识度；若 >= 0.85 则提前终止输出裁决。
- Round 2：各自看到对方 Round 1 论点后反驳 + 补充。Arbitrator 再次评估。
- Round 3（最终轮）：各自最终陈述，可修正立场、可让步。Arbitrator 最终裁决。

#### 裁决输出
```python
@dataclass
class DebateVerdict:
    debate_id: str
    topic: str
    trigger_type: str
    rounds_completed: int
    verdict: str                         # ACCEPTED / REJECTED / CONDITIONAL / SPLIT
    confidence: float
    winning_arguments: list[str]
    decisive_evidence: list[str]
    conditions: list[str] | None
    minority_opinion: str | None
    audit_trail: list[DebateRound]
```

#### 辩论与各层集成
- **证据层**：confidence 0.45-0.70 的 Claim 若存在冲突 Claim → 触发辩论；无冲突 → 进入人工审核队列。
- **推演层**：最高 score 动作 > 70 且领先第二名 > 20 → 直接选择；否则 → 触发辩论，裁决写入 `DecisionRecord.debate_verdict_id`。
- **分支层**：top-1 与 top-2 的 score 差距 <= 10% → 触发辩论决定保留哪些分支。
- **报告层**：报告草稿 top-3 关键结论各触发一次辩论挑战，辩论记录附在 "Why This Happened" 章节。

#### 辩论可配置性
```yaml
debate_config:
  enabled: true
  mode: "auto"                     # auto / manual / off
  scenarios:
    evidence_assessment: true
    conflict_resolution: true
    pivot_decision: true
    branch_evaluation: true
    report_challenge: true
  cost_limit_tokens: 200000
  log_level: "full"                # full / summary / off
```

### 8. 多模型自助复验迭代引擎与 Jarvis 集成
- 该能力作为横向层，作用于证据抽取、事件识别、推演解释、报告生成四个环节。
- 模型角色固定为：
  - 主模型：初稿生成
  - 复验模型：挑错与找漏洞
  - 仲裁模型：决定 PASS / REPAIR / NEEDS_HUMAN
  - 修复模型：按反馈局部修复
- 验证维度固定为：`requirements_alignment`、`logical_correctness`、`error_handling`、`completeness`、`provenance_integrity`、`claim_consistency`、`scenario_logic`、`explainability`、`mode_fit`、`domain_rule_alignment`。
- 通过门槛固定为：总分 `>= 80` 且 `critical_issues = 0`；同一任务最大自动修复 3 次，超限进入人工审核。
- `Jarvis` 保持通用 orchestrator，不硬编码业务逻辑；新增 `plan-agent` profile 来描述本项目的模型路由、验证维度和门槛。
- `Jarvis` 改造固定为：
  - 新增 `verification-loop` 与 `model-routing` 参考文档
  - 新增 `self_reviewer`、`repairer`、多模型 reviewer prompts
  - 新增 reviewer 聚合与下一步决策脚本
  - 扩展状态机为：`INIT -> ANALYZING -> REQUESTING_PLAN -> IMPLEMENTING -> SELF_REVIEWING -> CROSS_MODEL_REVIEWING -> REPAIRING -> REVERIFYING -> ARBITRATING -> FINALIZING -> DONE | NEEDS_HUMAN`
- `Jarvis` 默认仍由 Codex 决策，Claude 负责计划，Gemini 负责二次验证；若后续扩模型，只能通过 profile 配置扩展，不改核心协议。

#### Jarvis plan-agent Profile
Profile 文件位置：`E:\Project\jarvis\source\jarvis\profiles\plan-agent.yaml`

```yaml
profile_id: "plan-agent"
display_name: "PlanAgent 推演平台"
work_dir: "E:\\Project\\plan-agent"

model_routing:
  planner: "claude"
  implementer: "codex"
  validator: "gemini"
  evidence_extractor: "claude"
  simulation_actor: "claude"

validation_dimensions:
  - id: "requirements_coverage"
    weight: 1.0
  - id: "logical_correctness"
    weight: 1.0
  - id: "error_handling"
    weight: 0.8
  - id: "code_quality"
    weight: 0.7
  - id: "completeness"
    weight: 1.0
  - id: "provenance_integrity"
    weight: 1.0
    description: "证据链完整性：所有推演输入可追溯到 EvidenceItem"
  - id: "claim_consistency"
    weight: 0.9
    description: "Claim 一致性：无矛盾声明进入同一推演"
  - id: "scenario_logic"
    weight: 1.0
    description: "场景逻辑：分支条件合理，无死分支"
  - id: "explainability"
    weight: 1.0
    description: "可解释性：DecisionRecord 包含完整 why 链"
  - id: "domain_rule_alignment"
    weight: 0.8
    description: "领域规则对齐：动作效果符合领域常识"

thresholds:
  pass_score: 80
  critical_issues_max: 0
  max_rounds: 5
  max_retry_same_plan: 3

extended_states:
  - "SELF_REVIEWING"
  - "CROSS_MODEL_REVIEWING"
  - "REPAIRING"
  - "REVERIFYING"
  - "ARBITRATING"
```

#### 状态机扩展
在 Jarvis 原状态机 `CODEX_IMPLEMENTING` 之后插入复验子流程：
- `CODEX_IMPLEMENTING` → `SELF_REVIEWING`（Codex 自检，写 self-validation.json）
  - PASS → `CROSS_MODEL_REVIEWING`（Gemini 交叉验证）
  - FAIL → `REPAIRING` → `REVERIFYING`（循环，<= 3 次）
- `CROSS_MODEL_REVIEWING`
  - PASS → `CODEX_FINALIZING`
  - FAIL → `ARBITRATING`
- `ARBITRATING`
  - REPAIR → `REPAIRING`
  - PASS → `CODEX_FINALIZING`
  - NEEDS_HUMAN → `NEEDS_HUMAN`

#### 新增 Prompt 文件

| 文件 | 用途 |
|------|------|
| `prompts/plan-agent/self_reviewer.md` | Codex 自检 prompt，含 10 维验证清单 |
| `prompts/plan-agent/cross_reviewer.md` | Gemini 交叉验证 prompt |
| `prompts/plan-agent/repairer.md` | 按反馈局部修复 prompt |
| `prompts/plan-agent/arbitrator.md` | 仲裁决策 prompt |
| `prompts/plan-agent/debate_advocate.md` | 辩论正方 prompt |
| `prompts/plan-agent/debate_challenger.md` | 辩论反方 prompt |
| `prompts/plan-agent/debate_arbitrator.md` | 辩论仲裁 prompt |

## 性能基线与成本预估

### 延迟目标（MVP）

| 操作 | 目标延迟 | 说明 |
|------|---------|------|
| 单条数据采集 → 证据入库 | < 30s | 含去重、NLP 抽取、向量化 |
| 单步推演 tick（纯规则） | < 500ms | 10 个 Actor、50 条规则 |
| 单步推演 tick（含 LLM） | < 15s | 1-2 个 Actor 触发 LLM 辅助 |
| 完整 baseline 推演（52 ticks） | < 10min | 公司域一年，纯规则 |
| 分支搜索（depth=3, beam=5） | < 30min | 含所有分支 tick |
| 报告生成 | < 60s | 含 LLM 摘要润色 |
| API 查询响应 | < 200ms | 带 Redis 缓存 |

### LLM 调用量预估（单次完整推演）

| 环节 | 调用次数 | 单次 tokens | 小计 tokens |
|------|---------|------------|------------|
| 证据抽取（knowledge-worker） | ~100 条/批 | 1500 in + 500 out | ~200K |
| Actor 决策（仅 Level 2 触发） | ~20 次/baseline | 2000 in + 500 out | ~50K |
| 分支推演 Actor 决策 | ~60 次 | 2000 in + 500 out | ~150K |
| 辩论（证据+拐点+分支+报告） | ~20 次 | ~3000 in + 1000 out | ~136K |
| 报告摘要生成 | 1 次 | 5000 in + 2000 out | ~7K |
| 复验引擎（Jarvis） | 3-5 次 | 3000 in + 1000 out | ~20K |
| **总计** | | | **~563K tokens/次** |

### 资源需求（MVP 单机部署）
- CPU: 4 核（推荐 8 核）
- RAM: 16 GB（PostgreSQL 4GB + Redis 2GB + Workers 8GB + 余量）
- 存储: 100 GB SSD（PostgreSQL + MinIO）
- GPU: 不需要（使用 API 调用 LLM）

## 测试计划
- 采集层：重复抓取不产生脏重复，原始快照可回放，错误源可重试并进入死信。
- 证据层：`Claim` 必须能回溯原文，错误事件不得绕过置信度门槛进入主链。
- 公司推演：验证 GPU 涨价、竞品发布、开源项目爆发能正确影响 KPI 与动作选择。
- 军事推演：验证补给中断、天气恶化、ISR 增强、电子压制会改变态势与决策结果。
- 分支层：同一 baseline + 同一 seed 下分支树稳定，关键拐点必产出候选分支。
- 报告层：必须同时包含证据摘要、时间线、地图、场景树、决策链和 `Why This Happened`。
- 复验引擎：构造通过、返工、超限人工介入三类样例；验证评分门槛、重试次数、仲裁状态与日志工件完整。
- Jarvis：验证计划生成、实现、自检、二次验证、修复、重规划、人工升级整条状态链可重复执行。
- 辩论机制：
  - 构造灰区 Claim（confidence=0.55）+ 冲突 Claim 样例，验证辩论触发逻辑。
  - 构造推演拐点（3 个 score 接近的 CandidateAction），验证辩论→裁决→DecisionRecord 链路。
  - 验证辩论 token 上限生效：超限后自动降级为单模型评估。
  - 验证辩论记录可通过 `GET /debates/{debate_id}` 完整回溯。

## 数据版本与迁移策略

### Schema 版本管理
- 使用 **Alembic** 管理 PostgreSQL schema 迁移。
- 迁移文件存储在 `migrations/versions/`，每次 schema 变更必须生成迁移脚本。
- 迁移命名规范：`{序号}_{描述}.py`（如 `0001_init_evidence_schema.py`）。

### 推演结果版本化
- 每次推演运行生成唯一 `run_id`（UUID v7，含时间戳）。
- `StateSnapshot` 按 `(run_id, tick, actor_id)` 唯一索引。
- `DecisionRecord` 按 `(run_id, tick, sequence)` 唯一索引。
- 推演结果不可变（immutable）：修改参数后重新运行，生成新 `run_id`。

### 类型定义变更策略
- 新增字段：使用 `ALTER TABLE ADD COLUMN ... DEFAULT`，向后兼容。
- 修改字段类型：生成迁移脚本 + 数据转换函数，必须可回滚。
- 删除字段：先标记 `deprecated`，下一版本再物理删除。
- Domain Pack 类型变更：通过 YAML 版本号标记，旧版本推演结果保留原始 schema 快照。

### 数据保留策略
- `RawSourceItem`（MinIO）：保留 90 天，之后按需归档。
- `EvidenceItem`：永久保留。
- `StateSnapshot`：推演结果保留 30 天，标记为重要的永久保留。
- `event_archive`（Redis 事件归档）：保留 7 天。

## 实施节奏
- Phase 1：证据核心与最小审核队列
- Phase 2：公司域 MVP 与基础报告
- Phase 3：军事域 MVP 与前三种模式
- Phase 4：统一工作台与地图/决策链
- Phase 5：多模型复验引擎与 Jarvis profile 接入
- Phase 6：危机升级、训练教学、Replay package、Gym/RL adapter

## 假设与默认值
- 语言默认英文优先，保留多语言字段，中文知识抽取放后续增强。
- 地图 MVP 为 2D；3D globe、图数据库投影、强化学习接口均不阻塞首发。
- 数据存储默认：PostgreSQL + pgvector + PostGIS、Redis、MinIO。
- 首发只接入公开可验证数据源，不接封闭或无法复核的数据。
- `Jarvis` 的默认阈值沿用现有协议：`max_rounds = 5`、`max_retry_same_plan = 3`、`pass_threshold = 80`，仅通过 `plan-agent` profile 追加业务级验证维度，不改变默认核心门槛。
