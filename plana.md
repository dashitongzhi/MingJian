# PlanAgent 计划补充完善方案

## 整体架构总览

PlanAgent 是一个"证据驱动、可解释、可复验"的双域推演平台，采用**七层架构 + 模块化单体 + 异步 Worker** 模式。

### 七层架构一览

```
┌─────────────────────────────────────────────────────────────────────┐
│  Layer 7: Analyst Workspace & Delivery                             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌─────────┐  │
│  │ Review   │ │ Evidence │ │ Scenario │ │ Decision │ │ Report  │  │
│  │ Queue    │ │ Graph    │ │ Tree     │ │ Trace    │ │ Output  │  │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └─────────┘  │
├─────────────────────────────────────────────────────────────────────┤
│  Layer 6: Scenario Branching & Mode                                │
│  ┌────────────────┐  ┌─────────────────────────────────────────┐   │
│  │ Branch Search   │  │ Modes: Monitoring | Review | Simulation│   │
│  │ depth=3 beam=5  │  │        Branch Compare | Replay         │   │
│  └────────────────┘  └─────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────────┤
│  Layer 5: Domain Packs (可插拔)                                     │
│  ┌───────────────────┐  ┌───────────────────┐  ┌───────────────┐   │
│  │ Corporate Pack    │  │ Military Pack     │  │ Future Packs  │   │
│  │ 4 模板/15 状态/   │  │ 6 实体/14 状态/   │  │ (financial,   │   │
│  │ 15 动作/4 模式    │  │ 12 事件/14 动作/  │  │  energy...)   │   │
│  │                   │  │ 5 模式            │  │               │   │
│  └───────────────────┘  └───────────────────┘  └───────────────┘   │
├──────────────────────────────────────────────┬──────────────────────┤
│  Layer 4: Simulation Kernel (领域无关)       │  Debate Protocol     │
│  ┌──────┐ ┌───────────┐ ┌──────────────┐    │  ┌────────────────┐  │
│  │Actor │→│Candidate  │→│Decision      │    │  │Advocate(Claude)│  │
│  │      │ │Action     │ │Policy        │    │  │Challenger(Gem) │  │
│  └──────┘ └───────────┘ └──────┬───────┘    │  │Arbitrator(Cdx) │  │
│                                ↓             │  │ 3轮/共识0.85   │  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐   │  └────────────────┘  │
│  │State     │  │Outcome   │  │Decision  │   │  触发: 灰区证据/     │
│  │Snapshot  │  │Delta     │  │Record    │   │  冲突Claim/拐点/     │
│  └──────────┘  └──────────┘  └──────────┘   │  分支评估/报告挑战   │
├──────────────────────────────────────────────┴──────────────────────┤
│  Layer 3: Knowledge Fusion                                         │
│  NLP Pipeline: 清洗→实体→关系→事件→情绪→地理→向量→聚类→趋势       │
│  Output: Entity | Relationship | Signal | Event | Trend | GeoAsset │
│  置信度分流: >=0.70 主链 | 0.45-0.70 审核 | <0.45 仅检索           │
├─────────────────────────────────────────────────────────────────────┤
│  Layer 2: Evidence & Provenance                                    │
│  EvidenceItem → Claim (来源链接/原始片段/抽取方法/置信度/时间区间)   │
│  全链路: RawSourceItem→NormalizedItem→EvidenceItem→Claim→Event     │
├─────────────────────────────────────────────────────────────────────┤
│  Layer 1: Source Ingestion                                         │
│  SourceAdapter.fetch() → normalize() → store_raw()                 │
│  公司源: GitHub/HN/Reddit/RSS/Blog  军事源: OSINT/航空海事/智库    │
│  去重: URL规范化 + hash + 标题相似度 + 时间窗口语义去重             │
└─────────────────────────────────────────────────────────────────────┘
```

### 运行拓扑与数据流程图

```
                         外部数据源
          ┌──────────────────┴──────────────────┐
          │                                      │
    公司/技术源                              军事/OSINT源
    (GitHub,HN,                              (RSS,航空,
     Reddit,RSS)                              海事,智库)
          │                                      │
          └──────────────────┬───────────────────┘
                             ▼
               ┌──────────────────────┐
               │   ingest-worker      │  ← POST /ingest/runs 或定时调度
               │   (采集 + 去重)       │
               └──────────┬───────────┘
                          │ raw.ingested (Redis Stream)
                          ▼
               ┌──────────────────────┐
               │  knowledge-worker    │  NLP 抽取 + 向量化 + 置信度评分
               │  (证据+知识抽取)      │
               └──┬─────────┬────────┘
                  │         │
    evidence.     │         │ knowledge.extracted
    created       │         │
    claim.review  │         │
    _requested    │         │
                  ▼         ▼
          ┌───────────┐  ┌──────────────────────┐
          │  review-  │  │   graph-worker        │  更新证据图谱关系表
          │  worker   │  │   (图谱更新)           │
          │ (人工审核) │  └──────────────────────┘
          └───────────┘
                  │         │
                  │         │ knowledge.extracted
                  │         ▼
                  │  ┌──────────────────────┐
                  │  │ simulation-worker     │  ← POST /simulation/runs
                  │  │ (推演引擎)            │
                  │  │                       │
                  │  │ ┌───────────────────┐ │
                  │  │ │ 单步 tick 循环:    │ │
                  │  │ │ 1.注入 Shock      │ │
                  │  │ │ 2.Actor 提议      │ │  ←── 辩论协议可在此触发
                  │  │ │ 3.Policy 选择     │ │      (拐点决策/分支评估)
                  │  │ │ 4.执行 Delta      │ │
                  │  │ │ 5.记录 Decision   │ │
                  │  │ └───────────────────┘ │
                  │  │                       │
                  │  │ baseline → 拐点分支    │
                  │  │ (depth=3, beam=5)      │
                  │  └──────────┬────────────┘
                  │             │ simulation.completed
                  │             │ scenario.completed
                  │             ▼
                  │  ┌──────────────────────┐
                  │  │  report-worker       │
                  │  │  (报告生成)           │  ←── 辩论协议在此触发
                  │  │  Markdown/HTML/JSON   │      (报告结论挑战)
                  │  └──────────┬────────────┘
                  │             │ report.generated
                  │             ▼
                  └──→  ┌─────────────────────────────────┐
                        │   FastAPI control-api            │
                        │   REST API + WebSocket           │
                        │                                  │
                        │ /evidence  /claims  /signals     │
                        │ /simulation/runs  /scenario/runs │
                        │ /runs/{id}/decision-trace        │
                        │ /debates/{id}                    │
                        │ /review/items/{id}/accept|reject │
                        └───────────────┬─────────────────┘
                                        │
                                        ▼
                        ┌─────────────────────────────────┐
                        │   Analyst Workspace (前端)       │
                        │                                  │
                        │ Review Queue | Evidence Graph    │
                        │ Geo Timeline | Scenario Tree    │
                        │ Decision Trace | KPI Comparator │
                        │ Debate Records | 2D Map         │
                        └─────────────────────────────────┘


          ┌─────────── 基础设施 ───────────┐
          │                                 │
          │  PostgreSQL                     │
          │  ├── evidence schema            │
          │  │   (evidence_items, claims,   │
          │  │    signals, events, trends)  │
          │  ├── simulation schema          │
          │  │   (state_snapshots,          │
          │  │    decision_records,         │
          │  │    scenario_branches,        │
          │  │    debate_sessions)          │
          │  ├── pgvector (HNSW 索引)       │
          │  └── PostGIS (GIST 索引)        │
          │                                 │
          │  Redis                          │
          │  ├── stream:* (事件总线)         │
          │  ├── cache:* (API 缓存)         │
          │  └── signal:* (协调信号)        │
          │                                 │
          │  MinIO                          │
          │  └── 原始数据快照存储             │
          └─────────────────────────────────┘
```

### 多模型辩论流程图

```
        触发条件命中
  (灰区证据/冲突Claim/拐点/分支/报告)
              │
              ▼
    ┌─────────────────────┐
    │  构建辩论上下文       │
    │  topic + evidence    │
    │  + state snapshot    │
    └──────────┬──────────┘
               │
    ╔══════════▼══════════╗
    ║   Round 1: 独立立场  ║
    ╠═══════════════════════╣
    ║                       ║
    ║  ┌─────────┐ 并行 ┌─────────┐
    ║  │Advocate │ ←──→ │Challenger│
    ║  │(Claude) │      │(Gemini)  │
    ║  │论证成立  │      │论证不成立 │
    ║  └────┬────┘      └────┬─────┘
    ║       └──────┬─────────┘
    ╚══════════════▼══════════╝
               │
    ┌──────────▼──────────┐
    │ Arbitrator (Codex)  │
    │ 评估共识度           │
    └──────────┬──────────┘
               │
        ┌──────┴──────┐
        │             │
   consensus      consensus
   >= 0.85        < 0.85
        │             │
        ▼             ▼
    ┌────────┐  ╔═══════════════╗
    │ 终止   │  ║ Round 2: 反驳  ║
    │ 输出   │  ║ 各自看到对方   ║
    │ Verdict│  ║ 论点后反驳     ║
    └────────┘  ╚═══════╤═══════╝
                        │
                 Arbitrator 再评估
                        │
                 ┌──────┴──────┐
                 │             │
            consensus      consensus
            >= 0.85        < 0.85
                 │             │
                 ▼             ▼
             ┌────────┐  ╔═══════════════╗
             │ 终止   │  ║ Round 3: 终陈  ║
             └────────┘  ║ 可修正/让步    ║
                         ╚═══════╤═══════╝
                                 │
                          Arbitrator 最终裁决
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │ DebateVerdict            │
                    │ verdict: ACCEPTED /      │
                    │   REJECTED / CONDITIONAL │
                    │   / SPLIT                │
                    │ winning_arguments: [...]  │
                    │ decisive_evidence: [...]  │
                    │ minority_opinion: "..."   │
                    └─────────────────────────┘
                                 │
                    ┌────────────┴────────────┐
                    ▼                         ▼
            写入 DecisionRecord       附在 Report
            .debate_verdict_id       "Why This Happened"
```

### Jarvis 编排 × PlanAgent 集成全景

```
    用户/分析员发起任务
              │
              ▼
    ┌─────────────────────┐
    │  Jarvis Orchestrator │ (Codex 驱动)
    │  plan-agent profile  │
    └──────────┬──────────┘
               │
    INIT → CODEX_ANALYZING → REQUESTING_CLAUDE_PLAN
               │                      │
               │               Claude 生成计划
               │               claude_plan_r{n}.md
               │                      │
               ▼                      ▼
    CLAUDE_PLAN_READY → CODEX_IMPLEMENTING
                              │
                              ▼
                     SELF_REVIEWING (10维验证)
                      ┌───────┴───────┐
                      │               │
                    PASS            FAIL
                      │               │
                      ▼               ▼
              CROSS_MODEL_       REPAIRING
              REVIEWING          → REVERIFYING
              (Gemini)           (≤3次循环)
                      │
               ┌──────┴──────┐
               │             │
             PASS          FAIL
               │             │
               ▼             ▼
        CODEX_FINALIZING  ARBITRATING
               │          ┌──┴──┐
               ▼         REPAIR NEEDS_HUMAN
             DONE          │
                      REPAIRING
                      → 重新验证
```

---

## Context

用户已有两份计划文档（`PLAN.md` 107 行 + `PLAN_REVISED.md` 427 行），架构完整度高，但在以下方面存在缺口：Worker 编排与故障策略、时间模型、规则表示格式、Agent 决策模型、领域包扩展机制、Redis 角色定义、数据库索引策略、性能基线、数据版本策略、Jarvis profile 具体定义。本方案逐项补充这些缺失内容，直接追加到 `PLAN_REVISED.md` 末尾。

---

## 补充内容清单

### 1. Worker 编排 DAG 与故障策略

**追加位置**: `PLAN_REVISED.md` "运行拓扑" 章节之后

```markdown
## Worker 编排与故障策略

### Worker 依赖 DAG

```text
ingest-worker ──→ knowledge-worker ──→ simulation-worker ──→ report-worker
                        │                      │
                        ↓                      ↓
                  graph-worker           review-worker
```

- `ingest-worker`: 无上游依赖；监听定时调度或 `POST /ingest/runs`；产出 `raw.ingested` 事件
- `knowledge-worker`: 监听 `raw.ingested`；产出 `evidence.created`、`claim.review_requested`、`knowledge.extracted`
- `graph-worker`: 监听 `knowledge.extracted`；更新证据图谱关系表；无下游事件（被动查询）
- `simulation-worker`: 监听 `knowledge.extracted` 或 `POST /simulation/runs`；产出 `simulation.completed`、`scenario.completed`
- `review-worker`: 监听 `claim.review_requested`；人工操作后产出 `evidence.created`（升级）或标记驳回
- `report-worker`: 监听 `simulation.completed` / `scenario.completed`；产出 `report.generated`

### 事件总线

- 使用 **Redis Streams**（非 Pub/Sub），每个主题一个 Stream key
- 每个 Worker 使用 Consumer Group，支持多实例水平扩展
- 消息确认使用 `XACK`；未确认消息在超时后自动重投（pending entries list）
- 保留策略：`MAXLEN ~10000`（每个 Stream），历史事件归档到 PostgreSQL `event_archive` 表

### 故障与重试策略

| 故障类型 | 策略 |
|---------|------|
| Worker 崩溃 | Consumer Group 自动将 pending 消息重分配给存活实例 |
| 处理失败 | 指数退避重试 3 次（1s/4s/16s），超限进入 dead-letter stream `{topic}.dlq` |
| 上游超时 | knowledge-worker 对单条 NormalizedItem 设 60s 处理超时，超时标记 `TIMEOUT` 并跳过 |
| 背压 | 当 pending 消息数 > 1000 时，ingest-worker 暂停采集（backpressure signal via Redis key） |
| 数据源不可用 | ingest-worker 记录失败，下次调度重试；连续 5 次失败标记源为 `DEGRADED` |
```

---

### 2. 时间模型

**追加位置**: `PLAN_REVISED.md` "Simulation Kernel Layer" 章节内

```markdown
### 时间模型

- 推演采用 **离散时间步（discrete tick）** 模型，非事件驱动
- 每个 tick 代表一个固定时间窗口，由 Domain Pack 定义：
  - 公司域默认: `1 tick = 1 week`（可配置为 1 day / 1 month）
  - 军事域默认: `1 tick = 6 hours`（可配置为 1 hour / 24 hours）
- tick 内事件处理顺序固定为：
  1. 注入本 tick 窗口内的 ExternalShock
  2. 所有 Actor 并行提议 CandidateAction（无互相感知）
  3. DecisionPolicy 按优先级排序、冲突解决、选择执行
  4. 按选定动作顺序执行 OutcomeDelta
  5. 生成 StateSnapshot 和 DecisionRecord
- 冲突解决规则：当多个 Actor 修改同一资源时，按 `priority_score`（由规则计算）排序，高优先级先执行；若资源已耗尽，后续动作标记为 `BLOCKED`
- 跨域推演（公司+军事混合场景）使用最细粒度 tick，粗粒度域在非活跃 tick 跳过处理
```

---

### 3. 规则表示格式

**追加位置**: `PLAN_REVISED.md` "Simulation Kernel Layer" 章节内

```markdown
### 规则表示格式

- 规则采用 **YAML 声明式 + Python 函数** 双层结构：
  - **YAML 层**：声明触发条件、影响目标、参数范围，供非技术分析员编辑
  - **Python 层**：复杂计算逻辑，通过 `@rule_handler` 装饰器注册

#### YAML 规则示例

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

#### Python 规则示例

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

- 规则加载顺序：YAML 规则先加载为 `RuleSpec` 对象，Python handler 通过 `rule_id` 关联
- 热加载：规则文件变更后，通过 `POST /admin/rules/reload` 触发重载，不需重启 Worker
- 规则优先级：0-100，数字越大优先级越高；同优先级按注册顺序执行
```

---

### 4. Agent 决策模型

**追加位置**: `PLAN_REVISED.md` "Simulation Kernel Layer" 章节内

```markdown
### Actor 决策模型

Actor 的决策采用 **三级降级策略**：

#### Level 1: 规则引擎（默认，确定性）
- 基于当前 StateSnapshot + ExternalShock，匹配 YAML/Python 规则
- 输出 CandidateAction 列表，每个附带 `score` 和 `rule_id`
- 优点：可解释、可复现、零 LLM 成本
- 适用：常规场景、训练教学模式、回归测试

#### Level 2: LLM 辅助（可选，用于复杂推理）
- 当规则匹配结果为空或 score 均 < 30 时，触发 LLM 辅助
- 将当前状态 + 历史 3 步 DecisionRecord + 可用动作列表发给 LLM
- LLM 返回 JSON 格式的动作建议，附带 reasoning
- 模型路由：公司域 → Claude；军事域 → Claude（Codex/Gemini 不参与推演决策）
- token 预算：单次 Actor 决策 ≤ 2000 input + 500 output tokens
- 超时：10s，超时则降级到 Level 3

#### Level 3: 随机加权（降级兜底）
- 从当前可用动作中按历史成功率加权随机选择
- 标记 `decision_method: "fallback_random"`，在报告中高亮提示

### DecisionPolicy 选择器
- 输入：所有 Actor 的 CandidateAction 列表
- 冲突检测：标记修改同一资源的动作对
- 选择策略：按 `score * actor_priority` 排序，贪心选择无冲突子集
- 输出：选定的 Action 列表 + 被拒绝的 Action 列表（含拒绝原因）
```

---

### 5. 领域包注册接口

**追加位置**: `PLAN_REVISED.md` "Domain Pack Layer" 章节开头

```markdown
### 领域包注册与扩展机制

领域包通过 Python 类 + YAML 配置注册，内核不硬编码任何领域语义：

```python
class DomainPack(ABC):
    """领域包抽象基类"""

    @property
    @abstractmethod
    def domain_id(self) -> str: ...          # e.g. "corporate", "military"

    @property
    @abstractmethod
    def entity_types(self) -> list[EntityTypeSpec]: ...  # 实体类型定义

    @property
    @abstractmethod
    def state_fields(self) -> list[StateFieldSpec]: ...  # 状态字段定义

    @property
    @abstractmethod
    def action_library(self) -> list[ActionSpec]: ...    # 动作库

    @property
    @abstractmethod
    def event_types(self) -> list[EventTypeSpec]: ...    # 事件类型

    @abstractmethod
    def map_shock(self, event: Event, state: StateSnapshot) -> ExternalShock | None: ...

    @abstractmethod
    def default_actor_templates(self) -> list[ActorTemplate]: ...

    def rules_dir(self) -> Path:
        """YAML 规则目录，默认 rules/{domain_id}/"""
        return Path(f"rules/{self.domain_id}")
```

- 注册方式：在 `domain_packs/` 目录下创建子包，内核启动时自动扫描并注册
- 目录结构：
  ```
  domain_packs/
  ├── __init__.py            # 自动发现逻辑
  ├── corporate/
  │   ├── __init__.py
  │   ├── pack.py            # CorporateDomainPack(DomainPack)
  │   ├── templates.yaml     # 公司模板定义
  │   └── rules/             # YAML 规则文件
  └── military/
      ├── __init__.py
      ├── pack.py            # MilitaryDomainPack(DomainPack)
      ├── entities.yaml      # 军事实体定义
      └── rules/             # YAML 规则文件
  ```
- 新增领域（如 `financial`、`energy`）只需添加新子包，无需修改内核代码
```

---

### 6. Redis 角色与 PostgreSQL 索引策略

**追加位置**: `PLAN_REVISED.md` "运行拓扑" 章节内

```markdown
### Redis 职责划分

Redis 承担三个独立职责，通过 key 前缀隔离：

| 职责 | Key 前缀 | 数据结构 | 说明 |
|------|---------|---------|------|
| 事件总线 | `stream:` | Redis Streams | 8 个事件主题，Consumer Group 消费 |
| 缓存 | `cache:` | String (TTL) | API 响应缓存、热点查询结果，TTL 5min |
| 协调信号 | `signal:` | String / Set | Worker 背压信号、分布式锁、采集游标 |

- 不使用 Redis 做持久化存储；所有持久数据在 PostgreSQL
- Redis 配置 `maxmemory-policy allkeys-lru`，内存上限 2GB

### PostgreSQL Schema 与索引策略

- 使用单实例 PostgreSQL，双 schema 隔离：
  - `evidence` schema：证据链相关表（evidence_items, claims, signals, events, trends）
  - `simulation` schema：推演相关表（state_snapshots, decision_records, scenario_branches）
- pgvector 索引：
  - 向量维度固定 1536（OpenAI embedding）或 1024（本地模型），建表时确定
  - 索引类型：HNSW（`lists=100, m=16, ef_construction=200`），适合 < 500 万条记录的 MVP 阶段
  - 向量列仅在 `evidence_items` 和 `claims` 表上，不在推演表上
- PostGIS 索引：
  - `geo_assets` 表使用 `GEOMETRY(Point, 4326)` 类型 + GIST 索引
  - 空间查询主要用于：范围搜索（ST_DWithin）、覆盖计算（ST_Covers）、路径分析（ST_MakeLine）
- 分区策略：`evidence_items` 按 `created_at` 月分区（当数据量 > 100 万时启用）
```

---

### 7. 性能基线与成本预估

**追加位置**: `PLAN_REVISED.md` "测试与验收" 章节之后

```markdown
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
| 报告摘要生成 | 1 次 | 5000 in + 2000 out | ~7K |
| 复验引擎（Jarvis） | 3-5 次 | 3000 in + 1000 out | ~20K |
| **总计** | | | **~427K tokens/次** |

### 资源需求（MVP 单机部署）

- CPU: 4 核（推荐 8 核）
- RAM: 16 GB（PostgreSQL 4GB + Redis 2GB + Workers 8GB + 余量）
- 存储: 100 GB SSD（PostgreSQL + MinIO）
- GPU: 不需要（使用 API 调用 LLM）
```

---

### 8. 数据版本与迁移策略

**追加位置**: `PLAN_REVISED.md` "MVP 默认边界" 章节之前

```markdown
## 数据版本与迁移策略

### Schema 版本管理
- 使用 **Alembic** 管理 PostgreSQL schema 迁移
- 迁移文件存储在 `migrations/versions/`，每次 schema 变更必须生成迁移脚本
- 迁移命名规范：`{序号}_{描述}.py`（如 `0001_init_evidence_schema.py`）

### 推演结果版本化
- 每次推演运行生成唯一 `run_id`（UUID v7，含时间戳）
- `StateSnapshot` 按 `(run_id, tick, actor_id)` 唯一索引
- `DecisionRecord` 按 `(run_id, tick, sequence)` 唯一索引
- 推演结果不可变（immutable）：修改参数后重新运行，生成新 `run_id`

### 类型定义变更策略
- 新增字段：使用 `ALTER TABLE ADD COLUMN ... DEFAULT`，向后兼容
- 修改字段类型：生成迁移脚本 + 数据转换函数，必须可回滚
- 删除字段：先标记 `deprecated`，下一版本再物理删除
- Domain Pack 类型变更：通过 YAML 版本号标记，旧版本推演结果保留原始 schema 快照

### 数据保留策略
- `RawSourceItem`（MinIO）：保留 90 天，之后按需归档
- `EvidenceItem`：永久保留
- `StateSnapshot`：推演结果保留 30 天，标记为重要的永久保留
- `event_archive`（Redis 事件归档）：保留 7 天
```

---

### 9. Jarvis plan-agent Profile 定义

**追加位置**: `PLAN.md` "多模型自助复验迭代引擎与 Jarvis 集成" 章节内

基于现有 Jarvis 协议（`protocol.md`、`validation.md`），新增 `plan-agent` profile：

```markdown
### Jarvis plan-agent Profile

#### Profile 文件位置
`E:\Project\jarvis\source\jarvis\profiles\plan-agent.yaml`

#### Profile 定义

```yaml
profile_id: "plan-agent"
display_name: "PlanAgent 推演平台"
work_dir: "E:\\Project\\plan-agent"

# 模型路由（覆盖默认路由）
model_routing:
  planner: "claude"           # 计划生成
  implementer: "codex"        # 代码实现
  validator: "gemini"         # 二次验证
  evidence_extractor: "claude"  # 证据抽取 LLM
  simulation_actor: "claude"    # 推演 Actor LLM

# 验证维度（在 Jarvis 默认 5 维基础上追加 5 维）
validation_dimensions:
  # Jarvis 原有 5 维
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
  # plan-agent 新增 5 维
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

# 门槛（复用 Jarvis 默认值）
thresholds:
  pass_score: 80
  critical_issues_max: 0
  max_rounds: 5
  max_retry_same_plan: 3

# 扩展状态（追加到 Jarvis 原状态机）
extended_states:
  - "SELF_REVIEWING"         # 自检（Codex 完成后）
  - "CROSS_MODEL_REVIEWING"  # 双模型交叉验证
  - "REPAIRING"              # 按反馈修复
  - "REVERIFYING"            # 修复后重新验证
  - "ARBITRATING"            # 仲裁决定 PASS/REPAIR/NEEDS_HUMAN
```

#### 状态机扩展

在 Jarvis 原状态机基础上，`CODEX_IMPLEMENTING` 之后插入复验子流程：

```text
CODEX_IMPLEMENTING
  → SELF_REVIEWING (Codex 自检，写 self-validation.json)
    → [PASS] → CROSS_MODEL_REVIEWING (Gemini 交叉验证)
    → [FAIL] → REPAIRING → REVERIFYING → (循环，≤3 次)
  → CROSS_MODEL_REVIEWING
    → [PASS] → CODEX_FINALIZING
    → [FAIL] → ARBITRATING
  → ARBITRATING
    → [REPAIR] → REPAIRING
    → [PASS] → CODEX_FINALIZING
    → [NEEDS_HUMAN] → NEEDS_HUMAN
```

#### 新增 Prompt 文件

| 文件 | 用途 |
|------|------|
| `prompts/plan-agent/self_reviewer.md` | Codex 自检 prompt，含 10 维验证清单 |
| `prompts/plan-agent/cross_reviewer.md` | Gemini 交叉验证 prompt |
| `prompts/plan-agent/repairer.md` | 按反馈局部修复 prompt |
| `prompts/plan-agent/arbitrator.md` | 仲裁决策 prompt |
```

---

### 10. 多模型辩论机制（Model Debate Protocol）

**追加位置**: `PLAN_REVISED.md` 新增独立章节，位于 "Simulation Kernel Layer" 与 "Domain Pack Layer" 之间；同时在 `PLAN.md` "多模型自助复验迭代引擎" 章节内追加辩论子协议。

#### 设计理念

当前计划中多模型协作是"串行流水线"模式（主模型生成 → 复验模型审查 → 仲裁模型裁决）。辩论机制引入**对抗性并行推理**：多个模型同时针对同一问题给出独立判断，通过结构化辩论轮次暴露盲点、消除偏见，最终由仲裁者基于论据质量而非模型身份做出裁决。

#### 辩论适用场景

| 场景 | 触发条件 | 辩论焦点 |
|------|---------|---------|
| **证据可信度评估** | 单条 Claim 的 confidence 在 0.45-0.70 灰区 | 该 Claim 是否应进入推演主链 |
| **冲突证据裁决** | 同一实体/事件存在矛盾 Claim（confidence 差值 < 0.2） | 哪条 Claim 更可信，或两者如何调和 |
| **推演拐点决策** | 高影响 ExternalShock 到达，且规则引擎产出 ≥ 3 个 score 接近的 CandidateAction | 应选择哪个动作方向 |
| **场景分支评估** | 分支搜索产出的 top-3 分支 score 差距 < 10% | 哪些分支值得保留展开 |
| **报告结论挑战** | 报告生成后的最终质量关卡 | 结论是否被证据充分支撑 |

#### 辩论协议

```yaml
debate_protocol:
  max_rounds: 3              # 辩论最多 3 轮
  min_rounds: 1              # 至少 1 轮（初始立场）
  early_stop: true           # 若所有辩手达成共识则提前终止
  consensus_threshold: 0.85  # 共识度 >= 0.85 时视为达成一致

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
    rebuttals:                 # 第 2 轮起
      - target_argument_idx: 0
        counter: "反驳内容"
        evidence_ids: []
    concessions:               # 承认对方有效论点
      - argument_idx: 0
        reason: "为什么承认"
```

#### 辩论执行流程

```text
┌─────────────────────────────────────────────────┐
│                 Debate Trigger                   │
│  (灰区证据 / 冲突 Claim / 拐点决策 / 分支评估)    │
└──────────────────┬──────────────────────────────┘
                   ▼
         ┌─── Round 1: 独立立场 ───┐
         │                         │
    Advocate                  Challenger
    (并行调用)                (并行调用)
    "论证 X 成立"            "论证 X 不成立"
         │                         │
         └────────┬────────────────┘
                  ▼
         Arbitrator 评估共识度
         ├─ consensus >= 0.85 → 提前终止，输出裁决
         └─ consensus < 0.85 → 进入 Round 2
                  ▼
         ┌─── Round 2: 交叉反驳 ───┐
         │                          │
    Advocate 看到              Challenger 看到
    Challenger 论点             Advocate 论点
    → 反驳 + 补充              → 反驳 + 补充
         │                          │
         └────────┬─────────────────┘
                  ▼
         Arbitrator 再次评估
         ├─ consensus >= 0.85 → 终止
         └─ 继续 → Round 3 (最终轮)
                  ▼
         ┌─── Round 3: 最终陈述 ───┐
         │                          │
    Advocate 最终立场          Challenger 最终立场
    (可修正、可让步)           (可修正、可让步)
         │                          │
         └────────┬─────────────────┘
                  ▼
         Arbitrator 最终裁决
         → 输出 DebateVerdict
```

#### 裁决输出结构

```python
@dataclass
class DebateVerdict:
    debate_id: str
    topic: str                           # 辩论主题
    trigger_type: str                    # 触发场景类型
    rounds_completed: int                # 实际完成轮次
    verdict: str                         # ACCEPTED / REJECTED / CONDITIONAL / SPLIT
    confidence: float                    # 仲裁信心度
    winning_arguments: list[str]         # 胜出的关键论点
    decisive_evidence: list[str]         # 决定性证据 ID
    conditions: list[str] | None        # CONDITIONAL 时的附加条件
    minority_opinion: str | None        # 少数意见（若有价值则保留）
    audit_trail: list[DebateRound]      # 完整辩论记录（可回溯）
```

#### 与现有系统的集成点

**1. 证据层集成**（knowledge-worker）

```text
NormalizedItem → 抽取 Claim
  → confidence >= 0.70 → 直接入主链
  → 0.45 <= confidence < 0.70 → 检查是否有冲突 Claim
       → 有冲突 → 触发辩论（冲突证据裁决）
       → 无冲突 → 进入人工审核队列（现有逻辑不变）
  → confidence < 0.45 → 仅检索
```

**2. 推演层集成**（simulation-worker）

```text
ExternalShock 到达 → Actor 生成 CandidateAction 列表
  → 最高 score 的动作 score > 70 且领先第二名 > 20 → 直接选择（规则确定性强）
  → 否则 → 触发辩论（推演拐点决策）
       → Advocate: 论证 Action A 最优
       → Challenger: 论证 Action B 更优或 Action A 风险
       → Arbitrator: 裁决
       → 裁决结果写入 DecisionRecord.debate_verdict_id
```

**3. 分支评估集成**（simulation-worker）

```text
分支搜索完成 → top-N 分支按 score 排序
  → top-1 与 top-2 的 score 差距 > 10% → 保留 top-beam_width（现有逻辑）
  → top-1 与 top-2 的 score 差距 <= 10% → 触发辩论
       → 每对接近分支单独辩论：是否值得保留
       → 裁决后可能调整保留的分支集合
```

**4. 报告层集成**（report-worker）

```text
报告草稿生成后 → 抽取报告中的 top-3 关键结论
  → 对每条结论触发辩论（报告结论挑战）
       → Challenger 尝试找到结论未覆盖的反面证据
       → 若 Challenger 成功提出有效挑战 → 修订结论或标记不确定性
       → 辩论记录附在报告 "Why This Happened" 章节中
```

#### Token 预算与性能影响

| 辩论场景 | 预计触发频率 | 单次辩论 tokens | 每次推演新增 |
|---------|------------|----------------|------------|
| 证据灰区 | ~10 次/批 | ~6K (3轮×2模型×1K) | ~60K |
| 推演拐点 | ~5 次/baseline | ~8K | ~40K |
| 分支评估 | ~2 次/搜索 | ~6K | ~12K |
| 报告挑战 | 3 次/报告 | ~8K | ~24K |
| **合计** | | | **~136K tokens** |

更新后的总 token 预估：427K（原有）+ 136K（辩论）= **~563K tokens/次完整推演**

#### 辩论可配置性

```yaml
# 在 simulation run 配置中可控制辩论行为
debate_config:
  enabled: true                    # 全局开关
  mode: "auto"                     # auto: 按触发条件自动启动; manual: 仅人工触发; off: 关闭
  scenarios:                       # 可单独启用/禁用各场景
    evidence_assessment: true
    conflict_resolution: true
    pivot_decision: true
    branch_evaluation: true
    report_challenge: true
  cost_limit_tokens: 200000        # 单次推演辩论总 token 上限，超限后降级为单模型
  log_level: "full"                # full: 记录完整辩论; summary: 仅记录裁决; off: 不记录
```

#### 新增类型

在主类型列表中追加：
- `DebateSession`: 辩论会话，关联触发条件和参与模型
- `DebateRound`: 单轮辩论记录，含双方论点和反驳
- `DebateVerdict`: 裁决结果，含胜出论点和决定性证据

#### 新增 API

- `GET /debates/{debate_id}`: 获取辩论完整记录
- `GET /runs/{run_id}/debates`: 获取某次推演的所有辩论记录
- `POST /debates/trigger`: 手动触发辩论（Analyst Review 模式下）

#### 新增事件主题

- `debate.triggered`: 辩论被触发
- `debate.completed`: 辩论完成，含裁决结果

#### 新增 Jarvis Prompt 文件

| 文件 | 用途 |
|------|------|
| `prompts/plan-agent/debate_advocate.md` | 正方 prompt：论证命题成立 |
| `prompts/plan-agent/debate_challenger.md` | 反方 prompt：挑战命题，寻找反例 |
| `prompts/plan-agent/debate_arbitrator.md` | 仲裁 prompt：基于论据质量裁决 |

---

## 修改文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `E:\Project\plan-agent\PLAN_REVISED.md` | 编辑 | 追加第 1-8、10 项补充内容 |
| `E:\Project\plan-agent\PLAN.md` | 编辑 | 追加第 9 项 Jarvis profile 定义（含辩论角色路由和 prompt） |

---

## 验证方法

1. **文档完整性检查**：逐项对照本方案的 10 个补充项，确认全部写入目标文件
2. **一致性检查**：验证补充内容与原计划无矛盾（如 Worker 名称、事件主题、类型定义）
3. **可执行性检查**：每个补充项包含具体的格式/数值/代码示例，开发时可直接参考
4. **辩论机制验证**：
   - 构造灰区 Claim（confidence=0.55）+ 冲突 Claim 样例，验证辩论触发逻辑
   - 构造推演拐点（3 个 score 接近的 CandidateAction），验证辩论→裁决→DecisionRecord 链路
   - 验证辩论 token 上限生效：超限后自动降级为单模型评估
   - 验证辩论记录可通过 `GET /debates/{debate_id}` 完整回溯
