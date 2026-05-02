# 明鉴持续监测能力 — 奴才方案

> **目标**：实现"长时间持续监测 + 不断修正预测"的完整闭环

## 现状诊断

### 已有能力（可复用底座）
- **WatchRule**：定时轮询机制，`poll_interval_minutes` + `next_poll_at` + 租约锁
- **WatchIngestWorker**：可触发采集 + 可选自动触发 simulation/debate
- **Hypothesis 模型**：预测对象，有 `verification_status`、`time_horizon`、`actual_outcome`
- **CalibrationWorker**：假说到期验证 + 规则权重校准
- **Redis Streams**：事件总线，支持消费者组
- **DecisionRecordRecord**：决策追踪，含 `evidence_ids`、`expected_effect`、`actual_effect`

### 三大缺口
1. **预测无版本化**：Hypothesis 是一次性的，没有"版本链"
2. **证据→预测无影响映射**：新证据到来时不知道影响哪些旧预测
3. **无自动修正编排器**：没有"新证据→定位旧预测→增量重推→新版本"的编排逻辑

---

## Phase 1：打通核心闭环（预测版本化 + 自动修正）

### 目标
新证据到来时，自动定位受影响的预测，触发增量重推演，生成新版本预测。

### 1.1 新增数据模型：Forecast（预测版本化）

```python
# domain/models.py 新增
class Forecast(Base):
    __tablename__ = "forecasts"
    
    id: Mapped[str]                          # PK
    tenant_id: Mapped[str | None]            # 多租户
    topic: Mapped[str]                       # 预测主题（如"台海局势"、"AI芯片市场"）
    domain_id: Mapped[str]                   # corporate/military
    statement: Mapped[str]                   # 预测内容
    confidence: Mapped[float]                # 置信度 0-1
    time_horizon: Mapped[str]                # 1_month/3_months/6_months/1_year
    version: Mapped[int]                     # 版本号，从1开始
    parent_forecast_id: Mapped[str | None]   # 上一版本（版本链）
    status: Mapped[str]                      # ACTIVE/SUPERSEDED/VERIFIED/REFUTED
    
    # 关联
    evidence_ids: Mapped[list[str]]          # 支撑证据ID列表
    simulation_run_id: Mapped[str | None]    # 生成此预测的模拟运行
    hypothesis_id: Mapped[str | None]        # 对应的假说
    
    # 验证
    verification_status: Mapped[str]         # PENDING/CONFIRMED/REFUTED/PARTIAL
    actual_outcome: Mapped[str | None]       # 实际结果
    verified_at: Mapped[datetime | None]
    
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
```

### 1.2 新增数据模型：EvidenceImpact（证据影响映射）

```python
class EvidenceImpact(Base):
    __tablename__ = "evidence_impacts"
    
    id: Mapped[str]
    evidence_item_id: Mapped[str]            # FK -> evidence_items
    forecast_id: Mapped[str]                 # FK -> forecasts
    impact_type: Mapped[str]                 # SUPPORTS/CONTRADICTS/NUETRAL
    impact_score: Mapped[float]              # 影响程度 0-1
    explanation: Mapped[str]                 # 为什么这个证据影响这个预测
    created_at: Mapped[datetime]
```

### 1.3 新增 Worker：ForecastRevisionWorker

```
职责：监听新证据事件，定位受影响的预测，触发增量重推演

流程：
1. 消费 EventTopic.EVIDENCE_ADDED 事件
2. 对新证据做 embedding，与所有 ACTIVE 预测做相似度匹配
3. 如果匹配度 > 阈值，创建 EvidenceImpact 记录
4. 聚合同一预测的多个新证据影响
5. 如果累积影响超过 trigger_threshold，触发新一轮模拟
6. 新模拟生成新版本 Forecast（version++，parent_forecast_id 指向旧版）
7. 发布 EventTopic.FORECAST_REVISED 事件
```

### 1.4 修改 CalibrationWorker

```
增强：当假说验证结果为 REFUTED 时，自动检查是否有相关 Forecast
如果有，标记为 REFUTED，并通知前端
```

### 1.5 新增 API 端点

```
GET  /forecasts                    — 预测列表（支持按 topic/domain/status 过滤）
GET  /forecasts/{id}               — 预测详情
GET  /forecasts/{id}/history       — 预测版本链
GET  /forecasts/{id}/evidence-map  — 证据影响映射
POST /forecasts/{id}/re-evaluate   — 手动触发重新评估
```

### 验证标准
- [ ] 创建 Forecast 后，新证据能自动关联到对应 Forecast
- [ ] 超过阈值后自动触发新一轮模拟，生成新版本
- [ ] 旧预测标记为 SUPERSEDED，新预测版本号递增
- [ ] API 可查询预测历史和证据映射
- [ ] 现有功能不受影响

### 预估工作量：3-4 人天

---

## Phase 2：增强数据采集（增量 + 变化检测）

### 目标
实现基于 cursor/ETag 的增量采集，只在真正有新数据时触发更新。

### 2.1 新增数据模型：SourceCursor（数据源游标）

```python
class SourceCursor(Base):
    __tablename__ = "source_cursors"
    
    id: Mapped[str]
    source_type: Mapped[str]                 # rss/news/reddit/gdelt/x
    rule_id: Mapped[str]                     # FK -> watch_rules
    cursor_type: Mapped[str]                 # timestamp/etag/page_token/offset
    cursor_value: Mapped[str]                # 游标值
    last_fetched_at: Mapped[datetime]
    items_fetched: Mapped[int]               # 累计获取条数
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
```

### 2.2 修改数据源连接器

每个连接器（RSS、News、Reddit、GDELT、X）增加：
- `fetch_incremental(cursor)` 方法：基于游标增量获取
- 返回值增加 `new_items`、`updated_cursor`、`has_changes` 标志

### 2.3 修改 WatchIngestWorker

```
增强：
1. 读取上次的 SourceCursor
2. 调用 fetch_incremental(cursor) 而非 fetch_all()
3. 只处理 truly new items（不是哈希去重，是游标过滤）
4. 更新 SourceCursor
5. 如果有新证据，才发布 EventTopic.EVIDENCE_ADDED
6. 如果无新证据，跳过（不触发后续流程）
```

### 2.4 新增 API 端点

```
GET /sources/cursors              — 查看所有数据源游标状态
POST /sources/cursors/{id}/reset  — 重置游标（强制全量重抓）
```

### 验证标准
- [ ] 同一 WatchRule 连续两次轮询，第二次无新数据时不触发任何后续流程
- [ ] 游标持久化，Worker 重启后从上次位置继续
- [ ] 各数据源连接器的增量模式正确返回新数据
- [ ] 现有全量模式仍可用（降级策略）

### 预估工作量：2-3 人天

---

## Phase 3：前端展示 + 实时推送

### 目标
用户可以实时看到预测演化轨迹，新证据到来时前端自动刷新。

### 3.1 前端新增页面：预测追踪（Forecast Tracker）

```
功能：
- 预测列表（按 topic/domain 分组）
- 预测版本时间线（版本1 → 版本2 → 版本3...）
- 证据影响热力图（哪些证据改变了预测）
- 预测准确性仪表盘（confirmed vs refuted ratio）
```

### 3.2 WebSocket 实时推送

```
新增 WebSocket 端点：
WS /ws/forecasts    — 推送 FORECAST_REVISED 事件
WS /ws/evidence     — 推送 EVIDENCE_ADDED 事件

实现：
- 前端建立 WebSocket 连接
- 后端在发布事件时同步推送到 WebSocket
- 前端收到事件后自动刷新相关数据
```

### 3.3 修复已知 Bug

```
- 前端 /admin/watch-rules → 修正为 /watch/rules
- 前端 SWR 刷新间隔优化（从固定间隔改为事件驱动）
```

### 验证标准
- [ ] 预测追踪页面可展示版本时间线
- [ ] 新证据到来时前端自动刷新（无需手动刷新）
- [ ] 路由 bug 修复
- [ ] 四语 i18n 支持新页面

### 预估工作量：3-4 人天

---

## 总体架构图

```
┌─────────────────────────────────────────────────────────────┐
│                    持续监测闭环                               │
│                                                             │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐              │
│  │ 数据源    │───▶│ 增量采集  │───▶│ 变化检测  │              │
│  │ RSS/News │    │ Cursor   │    │ Diff     │              │
│  └──────────┘    └──────────┘    └────┬─────┘              │
│                                       │                     │
│                                       ▼                     │
│                                ┌──────────┐                 │
│                                │ 影响映射  │                 │
│                                │ Evidence │                 │
│                                │ →Forecast│                 │
│                                └────┬─────┘                 │
│                                     │                       │
│                              ┌──────┴──────┐                │
│                              │ 超过阈值？   │                │
│                              └──────┬──────┘                │
│                                     │ YES                   │
│                                     ▼                       │
│                              ┌──────────┐                   │
│                              │ 增量重推演 │                   │
│                              │ Simulation│                   │
│                              └────┬─────┘                   │
│                                   │                         │
│                                   ▼                         │
│                            ┌──────────┐                     │
│                            │ 新版本预测 │                     │
│                            │ Forecast │                     │
│                            │ v++      │                     │
│                            └────┬─────┘                     │
│                                 │                           │
│                                 ▼                           │
│                          ┌──────────┐                       │
│                          │ 前端推送  │                       │
│                          │ WebSocket│                       │
│                          └──────────┘                       │
└─────────────────────────────────────────────────────────────┘
```

---

## 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| Embedding 相似度匹配不准 | 证据→预测映射错误 | 使用 LLM 二次确认 + 置信度阈值 |
| 增量采集游标丢失 | 重复采集 | 游标持久化到数据库，重启后恢复 |
| 无限循环（修正触发修正） | 系统过载 | 设置每个预测的最大修订次数和冷却时间 |
| WebSocket 连接管理 | 内存泄漏 | 使用心跳 + 自动断开 + 重连机制 |
| 向后兼容 | 现有功能破坏 | 新功能全部是新增，不修改现有接口签名 |
