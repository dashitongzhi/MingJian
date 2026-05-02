# 明鉴“长时间持续监测 + 不断修正预测”实施计划

## 现状判断

当前仓库实际模型集中在 `src/planagent/domain/models.py`、API schema 在 `src/planagent/domain/api.py`，事件总线在 `src/planagent/events/bus.py`，没有审查报告中提到的 `src/planagent/models/`、`src/planagent/core/event_bus.py`、`src/planagent/services/event_archive.py`。实施时应沿用现有结构，避免新增并行目录造成维护分叉。

现有能力已经具备闭环雏形：`WatchIngestWorker` 可按 `WatchRule.next_poll_at` 轮询，`PhaseOnePipelineService` 有哈希去重与 `EventArchive`，`KnowledgeWorker` 可重估 Claim 置信度，`SimulationService` 可生成 `DecisionOption` 与 `Hypothesis`，`CalibrationWorker` 可做假说验证。但“预测”还不是一等对象，证据到预测的影响只隐含在 `DecisionRecordRecord.evidence_ids`、`DecisionOption.evidence_ids`、`Hypothesis.run_id` 中，缺少版本轨迹和自动重推编排。

兼容原则：

- 不修改现有 `/simulation/runs`、`/runs/{run_id}/hypotheses`、`/watch/rules` 的语义，只追加字段、表、事件和新端点。
- 旧 `Hypothesis` 继续可读写；新增预测版本表与 `Hypothesis` 建立可空关联，逐步迁移。
- 自动修正采用“新建版本/新建派生 run”，不覆盖旧 run、旧 hypothesis、旧 report。
- Redis Streams 增强必须保持 `InMemoryEventBus` 在测试和本地开发可用。

## Phase 1：打通核心修正闭环

### 目标

把“新证据进入系统后，自动定位受影响预测并生成新预测版本”打通。Phase 1 不追求复杂增量采集，先复用现有 WatchRule 重抓、Pipeline 去重、Simulation 一次性推演能力，建立预测版本化、证据影响映射、自动重推编排和 Redis pending 恢复的最小可交付闭环。

### 新增/修改文件列表

新增：

- `src/planagent/services/prediction.py`：预测版本、影响映射、重推任务服务。
- `src/planagent/workers/prediction_revision.py`：自动修正编排 worker。
- `src/planagent/api/routes/prediction.py`：预测版本、影响、手动重推 API。
- `tests/test_prediction_revision.py`：核心闭环服务测试。
- `tests/test_event_bus_pending.py`：Redis pending 恢复逻辑测试，可用 fake Redis 或集成测试标记。

修改：

- `src/planagent/domain/models.py`：新增预测相关 ORM 表，给 `Hypothesis` 增加可空 `prediction_version_id`。
- `src/planagent/domain/api.py`：新增 Prediction schema，给 `HypothesisRead` 可选返回 `prediction_version_id`。
- `src/planagent/domain/enums.py`：新增事件主题和预测/修正状态枚举。
- `src/planagent/events/bus.py`：增加 pending reclaim 能力。
- `src/planagent/worker_cli.py`：启动流式 worker 时先 reclaim pending，再消费新消息。
- `src/planagent/worker_cli.py`：注册 `prediction-revision-worker`。
- `src/planagent/api/routes/__init__.py`：挂载 prediction router。
- `src/planagent/api/routes/_deps.py`：缓存 `PredictionService`。
- `src/planagent/services/simulation.py`：生成 `DecisionOption/Hypothesis` 后同步创建预测 series/version/link；重推完成后写新版本。
- `src/planagent/workers/knowledge.py`：在 Claim 置信度变化、状态变化时携带 `claim_id/evidence_item_id/tenant_id/preset_id` 发布可定位的事件。
- `src/planagent/db.py`：SQLite 兼容性补列；生产数据库建议补 Alembic migration，如果项目当前没有 Alembic，先按现有 `create_all + SQLite ALTER` 模式处理。

### 核心数据模型

`PredictionSeries`

- `id`
- `subject_type`: `company | force | scenario | watch_rule | custom`
- `subject_id`
- `domain_id`
- `tenant_id`, `preset_id`
- `source_run_id`: 首次产生预测的 simulation run
- `current_version_id`
- `status`: `ACTIVE | ARCHIVED`
- `created_at`, `updated_at`

`PredictionVersion`

- `id`
- `series_id`
- `version_number`
- `run_id`: 本版本对应的 simulation run
- `hypothesis_id`: 兼容现有假说，可空
- `decision_option_id`: 可空
- `parent_version_id`: 前一版本，可空
- `trigger_type`: `initial | evidence_update | manual | backtest`
- `trigger_event_id`: `EventArchive.id` 或 Redis message id，可空
- `prediction_text`
- `time_horizon`
- `probability`: 先从 `DecisionOption.confidence` 或 Hypothesis 默认置信度估算
- `confidence`
- `status`: `DRAFT | ACTIVE | SUPERSEDED | FAILED`
- `summary_delta`: 相对上一版本的摘要，例如概率变化、关键状态变化
- `created_at`, `superseded_at`

`PredictionEvidenceLink`

- `id`
- `prediction_version_id`
- `evidence_item_id`
- `claim_id`
- `run_id`
- `decision_record_id`: 可空
- `link_type`: `supporting | conflicting | shock | decision_basis | revision_trigger`
- `impact_score`: 0 到 1
- `impact_direction`: `positive | negative | neutral | unknown`
- `impact_reason`: Phase 1 用规则解释，Phase 2 增强为差异解释
- `created_at`

`PredictionRevisionJob`

- `id`
- `series_id`
- `base_version_id`
- `trigger_claim_id`
- `trigger_evidence_item_id`
- `trigger_topic`
- `status`: `PENDING | PROCESSING | COMPLETED | FAILED | SKIPPED`
- `reason`
- `lease_owner`, `lease_expires_at`, `attempts`, `last_error`
- `new_run_id`, `new_version_id`
- `created_at`, `updated_at`, `completed_at`

### 关键接口

新增事件：

- `prediction.version_created`
- `prediction.revision_requested`
- `prediction.revision_completed`
- `prediction.revision_failed`

新增 API：

- `GET /predictions?tenant_id=&preset_id=&domain_id=&subject_id=`
- `GET /predictions/{series_id}`
- `GET /predictions/{series_id}/versions`
- `GET /predictions/{series_id}/impact`
- `POST /predictions/{series_id}/reforecast`
- `GET /predictions/revision-jobs?status=`

服务方法：

- `PredictionService.create_initial_versions_for_run(session, run)`
- `PredictionService.link_run_evidence(session, run, version)`
- `PredictionService.enqueue_revisions_for_evidence(session, claim_id, evidence_item_id, reason)`
- `PredictionService.process_revision_jobs(session, worker_id, limit)`
- `PredictionService.compare_versions(session, old_version, new_version)`

Worker 行为：

- `prediction-revision-worker` 消费 `evidence.created`、`evidence.updated`、`knowledge.extracted`。
- 启动时先扫 `PredictionRevisionJob.PENDING/PROCESSING lease expired`。
- 对命中的 series 创建派生 `SimulationRun`，配置中写入：
  - `revision_of_run_id`
  - `prediction_series_id`
  - `base_prediction_version_id`
  - `trigger_claim_id`
  - `trigger_evidence_item_id`
- 运行完成后创建新 `PredictionVersion`，旧版本标记 `SUPERSEDED`，但不删除旧 run 和 hypothesis。

Redis pending 恢复：

- `RedisStreamEventBus` 增加 `reclaim_pending(topics, group, consumer, min_idle_ms, count)`，内部使用 `XAUTOCLAIM`，不支持时退化为 `XPENDING + XCLAIM`。
- `worker_cli._run_stream_worker` 每轮或每 N 秒优先处理 reclaim 到的消息；失败仍写 `DeadLetterEvent` 并 ack，避免永久卡 pending。

### 验证标准

- 创建 WatchRule 并手动触发或等待轮询后，现有 ingest、knowledge、simulation、report 流程仍可完成。
- 新 simulation run 完成后，至少生成一个 `PredictionSeries` 和一个 `PredictionVersion(version_number=1)`，并能通过 `GET /predictions/{series_id}/versions` 查询。
- 新增或重估相关 Claim 后，系统创建 `PredictionRevisionJob`；worker 处理后生成派生 run 和 `version_number=2`，旧版本为 `SUPERSEDED`。
- `PredictionEvidenceLink` 能回答“哪些证据影响了哪个预测版本”，至少包含 `claim_id/evidence_item_id/impact_score/impact_reason`。
- 关闭 worker 后制造 Redis pending，再重启 worker，pending 消息能被 reclaim 并完成或进入 DLQ。
- 旧接口 `/runs/{run_id}/hypotheses`、`/runs/{run_id}/options`、`/watch/rules` 返回兼容，只多出可选字段。

### 工作量预估

8 到 12 人天。

## Phase 2：增强增量采集与变化检测

### 目标

在 Phase 1 闭环之上，减少无效重抓和重复重推，补齐 cursor/ETag/Last-Modified、内容变化检测、差异解释和自动触发重分析。此阶段交付后，系统可长期运行且对“真正发生变化的来源”做精确处理。

### 新增/修改文件列表

新增：

- `src/planagent/services/source_state.py`：来源 cursor、ETag、变化快照服务。
- `src/planagent/services/change_detection.py`：内容差异、语义差异和影响级别判定。
- `src/planagent/workers/change_analysis.py`：对变更来源触发重分析和修正任务。
- `tests/test_source_state.py`
- `tests/test_change_detection.py`

修改：

- `src/planagent/domain/models.py`：新增来源状态、变更记录；扩展 `RawSourceItem` 元数据不破坏原表语义。
- `src/planagent/domain/api.py`：新增 SourceState、SourceChange schema；扩展 WatchRule schema。
- `src/planagent/domain/enums.py`：新增 `source.changed`、`source.unchanged`、`source.change_explained` 事件。
- `src/planagent/services/analysis.py`：各 provider 返回 cursor/etag/last_modified/response_hash；支持条件请求。
- `src/planagent/services/pipeline.py`：将 dedupe 从“只按内容防重复”扩展为“同 URL 多版本快照 + unchanged 跳过知识抽取”。
- `src/planagent/workers/watch_ingest.py`：轮询时读取/更新 SourceState，只对变化来源创建知识处理 item；触发 source change 事件。
- `src/planagent/api/routes/admin.py`：修复兼容路由，保留 `/watch/rules`，增加 `/admin/watch-rules` 别名，避免前端旧调用失败。
- `src/planagent/db.py`：SQLite 兼容补表/补列。

### 核心数据模型

`SourceCursorState`

- `id`
- `watch_rule_id`: 可空，支持全局 provider 状态
- `source_type`
- `source_url_or_query`
- `tenant_id`, `preset_id`
- `cursor`: 分页或 provider cursor
- `etag`
- `last_modified`
- `last_seen_hash`
- `last_seen_raw_source_item_id`
- `last_success_at`, `last_failure_at`
- `consecutive_failures`
- `created_at`, `updated_at`

`SourceChangeRecord`

- `id`
- `source_state_id`
- `watch_rule_id`
- `old_raw_source_item_id`
- `new_raw_source_item_id`
- `old_hash`, `new_hash`
- `change_type`: `new | unchanged | updated | deleted | recovered`
- `significance`: `none | low | medium | high`
- `diff_summary`
- `changed_fields`: JSON，例如 title/body/published_at/metadata
- `claim_ids`: 变化影响到的 claims
- `prediction_revision_job_ids`: 已触发的重推任务
- `created_at`

扩展 `WatchRule`

- `incremental_enabled`: 默认 `True`
- `force_full_refresh_every`: 默认 24 小时或 N 次
- `last_cursor_reset_at`
- `change_significance_threshold`: 默认 `medium`

### 关键接口

新增 API：

- `GET /sources/states?watch_rule_id=&source_type=`
- `GET /sources/changes?watch_rule_id=&significance=`
- `POST /watch/rules/{rule_id}/cursor/reset`
- `POST /sources/changes/{change_id}/reanalyze`

服务行为：

- Provider 返回统一 `FetchResult(items, cursor, etag, last_modified, request_metadata)`。
- `SourceStateService.should_fetch()` 根据 poll 间隔、ETag、Last-Modified、强制全量周期决定是否请求。
- `ChangeDetectionService.compare(old_snapshot, new_item)` 输出结构化 diff 和 significance。
- 只有 `significance >= rule.change_significance_threshold` 时才发布 `source.changed` 并进入知识抽取/预测修正；`unchanged` 只更新 `last_success_at`。

### 验证标准

- 同一 WatchRule 连续轮询同一来源，无变化时不新增 Claim，不触发 PredictionRevisionJob。
- 来源返回 ETag/Last-Modified 时，第二次请求能带条件头；304 或等价未变化时记录 `source.unchanged`。
- 内容发生小幅变化时写 `SourceChangeRecord(significance=low)`，默认不重推预测。
- 内容发生关键变化时写 `significance=medium/high`，自动进入知识抽取并触发 Phase 1 修正编排。
- `/watch/rules` 与 `/admin/watch-rules` 都可用，前后端路由不一致问题关闭。
- 旧的哈希去重仍生效，历史 `SourceSnapshot` 不被破坏。

### 工作量预估

10 到 15 人天。

## Phase 3：完善前端展示、轨迹和回测闭环

### 目标

把持续监测和预测修正从后台能力变成可解释、可运营的前端体验：用户能看到预测跨时间版本轨迹、每次修正的触发证据、差异解释、回测结果和监测任务健康状态。此阶段不改变核心闭环，只增强展示、人工干预和校准反馈。

### 新增/修改文件列表

新增：

- `src/planagent/services/backtest.py`：预测回测、校准结果与版本轨迹聚合。
- `src/planagent/api/routes/monitoring.py`：监测视图聚合 API 与 SSE。
- `tests/test_prediction_backtest.py`
- 前端若继续使用单文件控制台：
  - 修改 `src/planagent/ui/strategic_console.html`
- 如果前端已迁移到独立 app：
  - 修改对应 `frontend/src/...` 的 watch rules、prediction timeline、SSE store 组件。

修改：

- `src/planagent/domain/models.py`：新增或扩展回测记录；可复用现有 `CalibrationRecord`，但建议增加版本粒度表。
- `src/planagent/domain/api.py`：新增 timeline、impact diff、backtest schema。
- `src/planagent/api/routes/__init__.py`：挂载 monitoring router。
- `src/planagent/services/workbench.py`：把预测版本轨迹、影响证据和回测摘要加入 `RunWorkbenchRead` 或新增聚合接口。
- `src/planagent/services/assistant.py`：在 session detail/recent runs 中返回 latest prediction version 和 revision summary。
- `src/planagent/workers/calibration.py`：从验证 `Hypothesis` 扩展到验证 `PredictionVersion`，将结果写回版本级回测。

### 核心数据模型

`PredictionBacktestRecord`

- `id`
- `prediction_version_id`
- `series_id`
- `verification_status`: `PENDING | CONFIRMED | REFUTED | PARTIAL`
- `actual_outcome`
- `verification_claim_id`
- `score`: 0 到 1
- `calibration_bucket`: 概率分桶
- `verified_at`
- `created_at`, `updated_at`

聚合读模型，不一定落表：

- `PredictionTimelineRead`: series、versions、version deltas、trigger evidence、run/report links。
- `MonitoringDashboardRead`: WatchRule 健康、SourceChange 趋势、RevisionJob 队列、PredictionBacktest 摘要。
- `PredictionImpactDiffRead`: 新旧版本概率/置信度/文本/状态指标差异。

### 关键接口

新增 API：

- `GET /monitoring/dashboard`
- `GET /monitoring/events/stream`：SSE 推送 `source.changed`、`prediction.revision_*`、`watch.rule_triggered`。
- `GET /predictions/{series_id}/timeline`
- `GET /predictions/{series_id}/versions/{version_id}/diff?against=`
- `POST /predictions/{series_id}/versions/{version_id}/verify`
- `GET /predictions/backtests?domain_id=&tenant_id=`

前端视图：

- Watch Rules 管理：统一使用 `/watch/rules`，可显示 `/admin/watch-rules` 兼容状态但不依赖。
- 持续监测看板：每条规则的 next poll、last poll、source changes、失败次数、队列 backlog。
- 预测时间线：版本号、创建时间、触发证据、概率/置信度变化、关联 run/report/debate。
- 影响解释面板：证据链接、Claim 状态变化、diff summary、为什么触发重推。
- 回测与校准：版本命中率、CONFIRMED/REFUTED/PARTIAL、按 domain/rule 分组。

### 验证标准

- 用户打开控制台能看到至少一个 WatchRule 的监测状态、最近 source changes、revision jobs。
- 对同一 prediction series，前端能展示 version 1 到 version N 的时间线，点击版本能看到触发证据和关联 run。
- SSE 在后台产生 `source.changed` 或 `prediction.revision_completed` 时能推送到浏览器，刷新后数据仍来自持久化 API。
- 手动 verify 某个 prediction version 后，`PredictionBacktestRecord` 更新，`CalibrationWorker` 后续聚合能包含版本级分数。
- 旧 workbench、assistant session 页面仍可使用；未启用新预测功能的历史 run 显示为空状态而不是报错。

### 工作量预估

8 到 14 人天。

## 总体交付顺序与依赖

1. Phase 1 先交付后台闭环：预测版本化、证据影响映射、自动修正编排、Redis pending 恢复。它只依赖现有重抓和一次性推演，可以独立验证。
2. Phase 2 再降低长期运行成本：增量采集、变化检测、差异解释和路由兼容。它复用 Phase 1 的 `PredictionRevisionJob` 作为重推入口。
3. Phase 3 最后产品化：展示时间线、SSE、回测校准。它读取 Phase 1/2 的持久化结果，不应成为核心闭环的前置条件。

总工作量预估：26 到 41 人天。若要求生产级迁移脚本、端到端浏览器测试、真实 Redis 集成测试和多个外部 provider 的条件请求全部覆盖，建议按上限排期。
