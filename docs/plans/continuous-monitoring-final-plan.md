# 明鉴"持续监测 + 不断修正预测" — 最终实施计划

> **目标**：实现"长时间持续监测 + 不断修正预测"的完整闭环
> **整合自**：奴才方案（Hermes）+ Codex方案 的辩证融合

---

## 辩证对比

| 维度 | 奴才方案 | Codex方案 | 最终取舍 |
|------|----------|-----------|----------|
| **数据模型** | `Forecast` 单表（内含version字段） | `PredictionSeries` + `PredictionVersion` + `PredictionEvidenceLink` 三表分离 | ✅ 采用Codex三表分离——更清晰的职责分离，便于查询版本链 |
| **修正触发** | `ForecastRevisionWorker` 直接消费事件 | `PredictionRevisionJob` 队列 + Worker 消费 | ✅ 采用Codex Job队列——可重试、可监控、有租约锁 |
| **证据匹配** | Embedding相似度匹配 | 规则+Claim关联 | ✅ 融合——Phase 1用规则匹配（快），Phase 3可升级为Embedding（准） |
| **Redis恢复** | 未考虑 | `XAUTOCLAIM` pending恢复 | ✅ 采纳——生产环境必须 |
| **增量采集** | `SourceCursor` 简单游标 | `SourceCursorState` + ETag/Last-Modified + 条件请求 | ✅ 采用Codex——更完整的HTTP条件请求支持 |
| **变化检测** | 简单哈希对比 | `SourceChangeRecord` + significance分级 | ✅ 采用Codex——significance分级避免微小变化触发重推 |
| **回测闭环** | 简单标记REFUTED | `PredictionBacktestRecord` + 版本级校准 | ✅ 采用Codex——可量化预测准确率 |
| **工作量估算** | 8-11人天 | 26-41人天 | 最终：18-25人天（融合后精简） |

### 奴才方案的优势（保留）
- ✅ 嵌入式相似度匹配思路 → Phase 3 可选增强
- ✅ 与现有 Hypothesis 模型的关联设计
- ✅ 架构图清晰展示闭环流程

### Codex方案的优势（采纳）
- ✅ 三表分离的预测模型（Series/Version/Link）
- ✅ Job队列模式的修正编排
- ✅ Redis pending恢复
- ✅ significance分级变化检测
- ✅ 更精确的文件修改清单
- ✅ 向后兼容策略（只追加，不修改现有接口语义）

---

## Phase 1：打通核心修正闭环（10-14 人天）

### 目标
新证据进入系统后，自动定位受影响预测并生成新预测版本。

### 新增数据模型

#### PredictionSeries（预测系列）
```
id                    PK
subject_type          company | force | scenario | watch_rule | custom
subject_id            关联主体ID
domain_id             corporate | military
tenant_id, preset_id  多租户
source_run_id         首次产生预测的 simulation run
current_version_id    当前最新版本
status                ACTIVE | ARCHIVED
created_at, updated_at
```

#### PredictionVersion（预测版本）
```
id                    PK
series_id             FK -> PredictionSeries
version_number        版本号，从1开始
run_id                本版本对应的 simulation run
hypothesis_id         兼容现有假说，可空
decision_option_id    可空
parent_version_id     前一版本，可空
trigger_type          initial | evidence_update | manual | backtest
trigger_event_id      触发事件ID，可空
prediction_text       预测内容
time_horizon          1_month | 3_months | 6_months | 1_year
probability           概率 0-1
confidence            置信度 0-1
status                DRAFT | ACTIVE | SUPERSEDED | FAILED
summary_delta         相对上一版本的变更摘要
created_at, superseded_at
```

#### PredictionEvidenceLink（证据-预测关联）
```
id                    PK
prediction_version_id FK -> PredictionVersion
evidence_item_id      FK -> evidence_items
claim_id              FK -> claims
run_id                关联run
decision_record_id    可空
link_type             supporting | conflicting | shock | decision_basis | revision_trigger
impact_score          0-1
impact_direction      positive | negative | neutral | unknown
impact_reason         影响原因（Phase 1规则解释，Phase 2增强为语义解释）
created_at
```

#### PredictionRevisionJob（修正任务队列）
```
id                    PK
series_id             FK -> PredictionSeries
base_version_id       基于哪个版本修正
trigger_claim_id      触发修正的Claim
trigger_evidence_item_id  触发修正的证据
trigger_topic         触发主题
status                PENDING | PROCESSING | COMPLETED | FAILED | SKIPPED
reason                修正原因
lease_owner           租约锁
lease_expires_at      租约过期时间
attempts              重试次数
last_error            最后错误
new_run_id            新生成的run
new_version_id        新生成的版本
created_at, updated_at, completed_at
```

### 新增/修改文件

| 操作 | 文件 | 说明 |
|------|------|------|
| 新增 | `src/planagent/services/prediction.py` | 预测版本、影响映射、修正任务服务 |
| 新增 | `src/planagent/workers/prediction_revision.py` | 自动修正编排Worker |
| 新增 | `src/planagent/api/routes/prediction.py` | 预测相关API |
| 新增 | `tests/test_prediction_revision.py` | 核心闭环测试 |
| 新增 | `tests/test_event_bus_pending.py` | Redis pending恢复测试 |
| 修改 | `src/planagent/domain/models.py` | 新增4个ORM表 |
| 修改 | `src/planagent/domain/api.py` | 新增Prediction schema |
| 修改 | `src/planagent/domain/enums.py` | 新增事件主题枚举 |
| 修改 | `src/planagent/events/bus.py` | 增加 `reclaim_pending()` |
| 修改 | `src/planagent/worker_cli.py` | 注册新Worker + pending恢复 |
| 修改 | `src/planagent/services/simulation.py` | 模拟完成后创建预测版本 |
| 修改 | `src/planagent/workers/knowledge.py` | Claim变化时发布可定位事件 |
| 修改 | `src/planagent/api/routes/__init__.py` | 挂载prediction router |

### 新增事件
```
prediction.version_created     — 新预测版本创建
prediction.revision_requested  — 修正请求入队
prediction.revision_completed  — 修正完成
prediction.revision_failed     — 修正失败
```

### 新增API
```
GET  /predictions                                      — 预测列表
GET  /predictions/{series_id}                          — 预测详情
GET  /predictions/{series_id}/versions                 — 版本链
GET  /predictions/{series_id}/impact                   — 证据影响映射
POST /predictions/{series_id}/reforecast               — 手动触发重推
GET  /predictions/revision-jobs?status=                 — 修正任务队列
```

### 核心流程

```
新证据入库 → KnowledgeWorker提取Claim
    → Claim变化事件 (knowledge.extracted)
    → PredictionService.enqueue_revisions_for_evidence()
        → 通过 evidence_item_id 定位关联的 PredictionSeries
        → 创建 PredictionRevisionJob(PENDING)
    → PredictionRevisionWorker 消费 Job
        → 创建派生 SimulationRun（配置写入 revision_of_run_id, prediction_series_id）
        → 运行模拟 → 生成新 DecisionOption/Hypothesis
        → 创建 PredictionVersion(version_number=N+1)
        → 旧版本标记 SUPERSEDED
        → 发布 prediction.revision_completed
```

### Redis Pending恢复
```
RedisStreamEventBus 增加 reclaim_pending()
  → 使用 XAUTOCLAIM（Redis 6.2+），不支持时退化为 XPENDING + XCLAIM
  → Worker 启动时先 reclaim pending，再消费新消息
  → 失败消息写入 DeadLetterEvent 并 ack，避免永久卡 pending
```

### 验证标准
- [ ] 现有 ingest → knowledge → simulation → report 流程不受影响
- [ ] 新 simulation run 完成后自动生成 PredictionSeries + PredictionVersion(v=1)
- [ ] 相关 Claim 变化后自动创建 RevisionJob，Worker 处理后生成 v=2
- [ ] PredictionEvidenceLink 可回答"哪些证据影响了哪个预测版本"
- [ ] 关闭Worker制造pending后重启，pending消息被reclaim
- [ ] 旧接口返回兼容，只多出可选字段

---

## Phase 2：增强增量采集与变化检测（5-7 人天）

### 目标
减少无效重抓和重复重推，只对"真正发生变化的来源"做精确处理。

### 新增数据模型

#### SourceCursorState（数据源游标状态）
```
id                    PK
watch_rule_id         FK -> watch_rules，可空
source_type           rss | news | reddit | gdelt | x
source_url_or_query
tenant_id, preset_id
cursor                分页或provider cursor
etag                  HTTP ETag
last_modified         HTTP Last-Modified
last_seen_hash        内容哈希
last_seen_raw_source_item_id
last_success_at, last_failure_at
consecutive_failures
created_at, updated_at
```

#### SourceChangeRecord（来源变更记录）
```
id                    PK
source_state_id       FK -> SourceCursorState
watch_rule_id         FK -> watch_rules
old_raw_source_item_id, new_raw_source_item_id
old_hash, new_hash
change_type           new | unchanged | updated | deleted | recovered
significance          none | low | medium | high
diff_summary          变更摘要
changed_fields        JSON {title: true, body: true, ...}
claim_ids             影响到的claims
prediction_revision_job_ids  已触发的修正任务
created_at
```

### 扩展 WatchRule
```
+ incremental_enabled           默认 True
+ force_full_refresh_every      默认 24小时
+ last_cursor_reset_at
+ change_significance_threshold 默认 medium
```

### 新增/修改文件

| 操作 | 文件 | 说明 |
|------|------|------|
| 新增 | `src/planagent/services/source_state.py` | 游标、ETag、变化快照服务 |
| 新增 | `src/planagent/services/change_detection.py` | 内容差异、significance判定 |
| 修改 | `src/planagent/domain/models.py` | 新增2个表 + 扩展WatchRule |
| 修改 | `src/planagent/services/analysis.py` | Provider返回cursor/etag/last_modified |
| 修改 | `src/planagent/services/pipeline.py` | 扩展去重为"同URL多版本快照" |
| 修改 | `src/planagent/workers/watch_ingest.py` | 读取/更新SourceCursorState |
| 修改 | `src/planagent/api/routes/admin.py` | 修复 `/admin/watch-rules` 路由兼容 |

### 新增API
```
GET  /sources/states?watch_rule_id=&source_type=     — 游标状态
GET  /sources/changes?watch_rule_id=&significance=   — 变更记录
POST /watch/rules/{rule_id}/cursor/reset             — 重置游标
POST /sources/changes/{change_id}/reanalyze          — 手动触发重分析
```

### 核心流程

```
WatchIngestWorker 轮询
    → 读取 SourceCursorState
    → 带 ETag/Last-Modified 条件请求
    → 304/未变化 → 更新 last_success_at，跳过
    → 有变化 → ChangeDetectionService.compare()
        → significance=low → 记录 SourceChangeRecord，不重推
        → significance=medium/high → 记录 + 进入知识抽取
            → 触发 Phase 1 修正编排
    → 更新 SourceCursorState
```

### 验证标准
- [ ] 同一WatchRule连续轮询，无变化时不新增Claim，不触发RevisionJob
- [ ] ETag/Last-Modified 条件请求正确发送
- [ ] significance=low 的变化不触发重推
- [ ] significance=medium/high 的变化正确触发修正闭环
- [ ] `/watch/rules` 和 `/admin/watch-rules` 都可用

---

## Phase 3：前端展示 + 回测闭环（5-8 人天）

### 目标
持续监测和预测修正从后台能力变成可解释、可运营的前端体验。

### 新增数据模型

#### PredictionBacktestRecord（回测记录）
```
id                    PK
prediction_version_id FK -> PredictionVersion
series_id             FK -> PredictionSeries
verification_status   PENDING | CONFIRMED | REFUTED | PARTIAL
actual_outcome        实际结果
verification_claim_id 验证用的Claim
score                 0-1
calibration_bucket    概率分桶
verified_at
created_at, updated_at
```

### 新增/修改文件

| 操作 | 文件 | 说明 |
|------|------|------|
| 新增 | `src/planagent/services/backtest.py` | 回测、校准、版本轨迹聚合 |
| 新增 | `src/planagent/api/routes/monitoring.py` | 监测视图API + SSE |
| 修改 | `src/planagent/services/workbench.py` | 加入预测版本轨迹 |
| 修改 | `src/planagent/services/assistant.py` | session中返回最新预测版本 |
| 修改 | `src/planagent/workers/calibration.py` | 扩展为验证PredictionVersion |
| 修改 | `frontend/` | 新增预测追踪页面 |

### 新增API
```
GET  /monitoring/dashboard                              — 监测看板
GET  /monitoring/events/stream                          — SSE实时推送
GET  /predictions/{series_id}/timeline                  — 预测时间线
GET  /predictions/{series_id}/versions/{id}/diff?against= — 版本对比
POST /predictions/{series_id}/versions/{id}/verify      — 手动验证
GET  /predictions/backtests?domain_id=&tenant_id=       — 回测结果
```

### 前端新增页面

1. **持续监测看板** — WatchRule健康状态、来源变更趋势、修正任务队列
2. **预测时间线** — 版本号、触发证据、概率/置信度变化曲线
3. **证据影响面板** — 哪些证据改变了预测、变更摘要、diff对比
4. **回测与校准仪表盘** — 版本命中率、按domain/rule分组的准确率

### SSE实时推送
```
WS /monitoring/events/stream
  → source.changed        — 来源变更
  → prediction.revision_* — 预测修正
  → watch.rule_triggered  — 规则触发
```

### 验证标准
- [ ] 监测看板展示WatchRule状态、变更趋势、修正队列
- [ ] 预测时间线展示v1→v2→v3的完整演化
- [ ] SSE在事件发生时实时推送到浏览器
- [ ] 手动verify后PredictionBacktestRecord正确更新
- [ ] 现有workbench/assistant页面不受影响

---

## 总体交付顺序

```
Phase 1 (10-14天)          Phase 2 (5-7天)           Phase 3 (5-8天)
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│ 预测版本化       │      │ 增量采集         │      │ 前端展示         │
│ 证据影响映射     │ ───▶ │ 变化检测         │ ───▶ │ 回测闭环         │
│ 自动修正编排     │      │ significance分级 │      │ SSE实时推送      │
│ Redis pending恢复│      │ 路由兼容修复     │      │ 校准仪表盘       │
└─────────────────┘      └─────────────────┘      └─────────────────┘
     可独立验证               复用Phase1              读取Phase1/2结果
```

**总工作量：20-29 人天**

---

## 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 修正循环（修正触发修正） | 系统过载 | 每个series最大修订次数限制 + 冷却时间 |
| Embedding匹配不准 | 证据映射错误 | Phase 1先用规则匹配，Phase 3可选升级Embedding |
| ETag/条件请求兼容性 | 增量采集失败 | 降级为全量抓取 + 哈希对比 |
| WebSocket连接管理 | 内存泄漏 | 心跳 + 自动断开 + 重连 |
| 向后兼容 | 现有功能破坏 | 只追加不修改，旧接口保留原语义 |
| 生产数据库迁移 | 数据丢失 | Alembic migration脚本 + 回滚方案 |

---

## 可复用底座（不重写，只扩展）

| 现有组件 | 复用方式 |
|----------|----------|
| WatchRule + WatchIngestWorker | 扩展SourceCursorState，增加增量模式 |
| Hypothesis | 通过可空prediction_version_id关联 |
| CalibrationWorker | 扩展为验证PredictionVersion |
| Redis Streams EventBus | 增加reclaim_pending |
| SimulationService | 模拟完成后创建PredictionVersion |
| KnowledgeWorker | Claim变化时发布定位事件 |
| DecisionRecordRecord | evidence_ids用于影响映射 |
