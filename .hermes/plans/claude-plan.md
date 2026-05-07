# PlanAgent 前端优化实施计划

> 目标工作流：提交问题 → 多Agent分头搜索 → 辩论中心多模型交锋 → 首次结果展示 → 持续采集+定期/事件驱动更新 → 前端直接展示建议+刷新按钮

---

## 一、现状分析总结

### 已有能力（后端）
- 12 个 source adapter 并行搜索（analysis.py `_fetch_related_sources_with_events`）
- 4 轮辩论系统（debate.py `trigger_debate` → `_assess_debate` → `_llm_debate_rounds`）
- WatchRule 持续监控 + 自动触发 simulation/debate
- WebSocket 推送通知（ws.py `/ws/notifications`）
- SSE 流式分析（assistant.py `stream` 方法，逐事件 yield）

### 前端现状
- `/assistant` 页面：有 SSE 流式，已处理 `source_start/source_complete/source_error/step/source/discussion/debate_round/assistant_result` 事件
- `/workbench` 页面：静态加载 session → 展示 recommendation/findings/predictions
- `/debate` 页面：手动输入 debate ID 加载，展示 4 轮辩论 + 裁决
- `/monitoring` 页面：SSE 事件流 + WatchRule 健康状态

### 五大差距
1. **数据采集缺乏 Agent 身份** — `SourceSearchProgress` 已存在但标签仅显示 provider name，无"哪个Agent在搜什么"
2. **辩论过程非实时流式** — 后端 `_assess_debate` 同步执行 4 轮，前端一次性收到所有 rounds
3. **无建议版本时间线** — prediction_versions 在 workbench 有展示但无"建议演化"视图
4. **无醒目刷新按钮** — 工作台无 manual refresh 入口
5. **更新通知不够醒目** — WebSocket 通知仅在 header 小铃铛，无全屏横幅

---

## 二、具体改动清单

### 模块 A：增强数据采集的 Agent 身份透明度

#### A1. 后端：分析流增加 Agent 身份元数据
**文件**: `src/planagent/services/analysis.py`
- 在 `_fetch_related_sources_with_events` 中，每个 source adapter 执行时 yield 更丰富的事件：
  ```python
  yield AnalysisEvent("source_start", {
      "provider": adapter.key,
      "label": adapter.label,
      "agent_role": "scout",          # 新增：agent 角色
      "target": f"搜索 {adapter.label} 获取 {query[:50]}",  # 新增：任务描述
      "icon": adapter.icon_key,       # 新增：图标标识
  })
  ```
- 在 `SourceAdapter` dataclass 新增 `icon_key: str` 字段
- 在 adapter 注册处（`_build_source_adapters`）为每个 adapter 设置 icon

**工作量**: 2h

#### A2. 前端：重构 SourceSearchProgress 为 AgentDashboard 组件
**新文件**: `frontend/src/components/AgentDashboard.tsx`
- 展示每个搜索 Agent 的卡片：头像/图标 + 角色名 + "正在搜索 XX…" + 进度动画
- 用竖线时间轴串联各 Agent 的活动
- 搜索完成后显示收集数量 + 可展开查看具体 source 标题列表

**文件**: `frontend/src/app/assistant/page.tsx`
- 替换现有 `SourceSearchProgress` 为 `AgentDashboard`
- 处理新的 `agent_role`, `target`, `icon` 字段

**工作量**: 4h

#### A3. i18n 补充
**文件**: `frontend/src/i18n/zh.ts` + `frontend/src/i18n/en.ts`
```typescript
agent: {
  scout: "情报侦察",
  analyst: "深度分析",
  synthesizer: "综合研判",
  searching: "搜索中",
  completed: "已完成",
  failed: "失败",
  collectedItems: "条情报",
  agentActivity: "智能体活动",
}
```

**工作量**: 0.5h

---

### 模块 B：辩论实时流式展示

#### B1. 后端：辩论服务改为逐轮 yield
**文件**: `src/planagent/services/debate.py`
- 新增 `stream_debate` 异步生成器方法：
  ```python
  async def stream_debate(self, session, payload) -> AsyncIterator[DebateEvent]:
      # 第1轮：advocate position
      yield DebateEvent("debate_round_start", {"round": 1, "role": "advocate"})
      advocate_round = await self._llm_round("advocate", ...)
      yield DebateEvent("debate_round", advocate_round)
      
      # 第2轮：challenger 反驳
      yield DebateEvent("debate_round_start", {"round": 2, "role": "challenger"})
      challenger_round = await self._llm_round("challenger", ...)
      yield DebateEvent("debate_round", challenger_round)
      
      # 第3轮：advocate 回应
      yield DebateEvent("debate_round_start", {"round": 3, "role": "advocate"})
      # ...
      
      # 第4轮：arbitrator 裁决
      yield DebateEvent("debate_round_start", {"round": 4, "role": "arbitrator"})
      # ...
      
      # 最终裁决
      yield DebateEvent("debate_verdict", verdict_data)
  ```
- 保留现有 `trigger_debate` 作为兼容入口，内部调用 `stream_debate`

**文件**: `src/planagent/services/assistant.py`
- `stream` 方法中替换同步 `debate_service.trigger_debate` 为 `debate_service.stream_debate`
- 每收到一个 `debate_round` 事件就 yield 给前端

**工作量**: 6h

#### B2. 后端：新增辩论流式 SSE endpoint
**文件**: `src/planagent/api/routes/analysis.py`（或新建 `debate_stream.py`）
```python
@router.post("/debate/stream")
async def stream_debate_endpoint(payload, request, session):
    service = get_debate_service(request)
    async def event_stream():
        async for event in service.stream_debate(session, payload):
            yield f"event: {event.event}\ndata: {json.dumps(event.payload)}\n\n"
    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

**工作量**: 2h

#### B3. 前端：辩论中心增加"实时辩论"模式
**文件**: `frontend/src/app/debate/page.tsx`
- 新增"发起辩论"按钮（不仅手动输入 ID）
- 点击后连接 `/debate/stream` SSE
- 逐轮实时渲染辩论内容，每轮出现时有动画
- 显示"第 N 轮 · 支持方正在陈述…" 的状态指示器
- 辩论完成时展示最终裁决卡片（带 confetti 或脉冲动画）

**新文件**: `frontend/src/components/DebateStreamView.tsx`
- 实时辩论流组件：接收 SSE 事件，逐轮渲染
- 每轮显示角色头像/颜色 + 打字机效果 + 论点/反驳列表

**文件**: `frontend/src/lib/api.ts`
- 新增 `streamDebate(body, onEvent, signal)` 函数（类似 `streamAssistant`）

**工作量**: 6h

#### B4. i18n 补充
```typescript
debate: {
  startDebate: "发起辩论",
  starting: "辩论启动中...",
  roundInProgress: "第{round}轮 · {role}正在陈述",
  debateComplete: "辩论完成",
  liveDebate: "实时辩论",
  // ...existing keys
}
```
**工作量**: 0.5h

---

### 模块 C：建议版本时间线 + 刷新按钮

#### C1. 前端：工作台增加醒目刷新按钮
**文件**: `frontend/src/app/workbench/page.tsx`
- 在会话选择器旁增加刷新按钮（带旋转动画）：
  ```tsx
  <button
    onClick={() => mutate(`decision-workbench-${selectedSessionId}`)}
    className="btn btn-ghost"
  >
    <RefreshCw size={16} className={isRefreshing ? "animate-spin" : ""} />
    刷新
  </button>
  ```
- 使用 SWR 的 `mutate` + `isValidating` 状态

**工作量**: 1h

#### C2. 前端：建议版本时间线组件
**新文件**: `frontend/src/components/AdviceTimeline.tsx`
- 展示从 `prediction_versions` 数据中提取建议演化
- 每个版本节点：日期 + 概率变化 + 触发原因 + 建议摘要
- 用竖线时间轴 + 差异高亮（概率上升=绿色箭头，下降=红色）
- 点击节点展开详情

**文件**: `frontend/src/app/workbench/page.tsx`
- 在 "当前建议" 卡片下方增加 `AdviceTimeline` 组件
- 接收 `workbench.prediction_versions` 数据

**工作量**: 4h

#### C3. 前端：结果页面增加"重新分析"按钮
**文件**: `frontend/src/app/assistant/page.tsx`
- 分析完成后，在结果区域顶部增加"🔄 刷新分析"按钮
- 点击后以相同参数重新调用 `streamAssistant`
- 使用 SWR cache key 触发数据更新

**工作量**: 1.5h

---

### 模块 D：更新通知增强

#### D1. 后端：WebSocket 通知增加 more topics + 优先级
**文件**: `src/planagent/api/routes/ws.py`
- `NOTIFICATION_TOPICS` 增加：
  ```python
  NOTIFICATION_TOPICS = [
      EventTopic.SOURCE_CHANGED.value,
      EventTopic.DEBATE_COMPLETED.value,
      EventTopic.PREDICTION_VERSION_CREATED.value,
      EventTopic.SIMULATION_COMPLETED.value,  # 新增
      "session.updated",                        # 新增
  ]
  ```
- 通知消息增加 `action_url` 字段，前端可直接跳转

**工作量**: 1h

#### D2. 前端：全屏通知横幅组件
**新文件**: `frontend/src/components/UpdateBanner.tsx`
- 接收 WebSocket 通知后显示全屏顶部横幅（固定定位）
- 高严重度=红色 + 脉冲；中=黄色；低=绿色
- 包含：标题 + 摘要 + "查看详情" 按钮 + "忽略" 按钮
- 5 秒后自动淡出（可配置）

**文件**: `frontend/src/components/AppShell.tsx`
- 在 `handleNotificationMessage` 中增加横幅状态管理
- 渲染 `<UpdateBanner>` 组件
- 高严重度通知同时播放提示音（可选）

**工作量**: 3h

#### D3. 前端：工作台实时更新指示器
**文件**: `frontend/src/app/workbench/page.tsx`
- 当 WebSocket 收到该 session 的更新通知时：
  - 页面顶部显示"检测到新数据，点击刷新"横幅
  - 或自动静默刷新（可配置）
- 使用 session_id 匹配过滤

**工作量**: 2h

---

### 模块 E：统一工作流页面（可选高级）

#### E1. 新建 `/workflow` 统一视图
**新文件**: `frontend/src/app/workflow/page.tsx`
- 一个页面展示完整工作流的六个阶段：
  1. 提交问题（输入区）
  2. 多Agent搜索（AgentDashboard）
  3. 辩论中心（DebateStreamView）
  4. 首次结果（结果摘要卡片）
  5. 持续监控（WatchRule状态 + 最新变更）
  6. 更新建议（AdviceTimeline + 刷新按钮）
- 左侧垂直进度条，当前阶段高亮
- 每个阶段完成后有 ✅ 标记

**新文件**: `frontend/src/components/WorkflowStepper.tsx`
- 垂直进度条组件

**文件**: `frontend/src/components/AppShell.tsx`
- 导航增加 "工作流" 入口

**文件**: `frontend/src/i18n/zh.ts`
- 增加 workflow 相关翻译

**工作量**: 8h

---

## 三、实施顺序

| 阶段 | 任务 | 优先级 | 预估工时 | 依赖 |
|------|------|--------|----------|------|
| Phase 1 | A1 后端 agent 元数据 | P0 | 2h | 无 |
| Phase 1 | A2 前端 AgentDashboard | P0 | 4h | A1 |
| Phase 1 | A3 i18n 补充 | P0 | 0.5h | 无 |
| Phase 2 | B1 后端辩论流式 | P0 | 6h | 无 |
| Phase 2 | B2 辩论 SSE endpoint | P0 | 2h | B1 |
| Phase 2 | B3 前端 DebateStreamView | P0 | 6h | B2 |
| Phase 2 | B4 i18n 补充 | P0 | 0.5h | 无 |
| Phase 3 | C1 刷新按钮 | P0 | 1h | 无 |
| Phase 3 | C2 AdviceTimeline | P1 | 4h | 无 |
| Phase 3 | C3 重新分析按钮 | P1 | 1.5h | 无 |
| Phase 4 | D1 后端通知增强 | P1 | 1h | 无 |
| Phase 4 | D2 全屏通知横幅 | P1 | 3h | D1 |
| Phase 4 | D3 工作台实时更新 | P1 | 2h | D1 |
| Phase 5 | E1 统一工作流页面 | P2 | 8h | A2+B3+C2+D2 |

**总计预估工时**: ~41.5h

### 推荐分期交付
- **Week 1 (Phase 1+2)**: Agent 身份 + 辩论流式 = ~15h → 核心体验升级
- **Week 2 (Phase 3)**: 刷新按钮 + 建议时间线 = ~6.5h → 用户操作优化  
- **Week 3 (Phase 4)**: 通知增强 = ~6h → 信息触达优化
- **Week 4 (Phase 5)**: 统一工作流 = ~8h → 可选的综合优化

---

## 四、关键文件修改/创建清单

### 修改的文件
| 文件路径 | 改动内容 |
|---------|---------|
| `src/planagent/services/analysis.py` | SourceAdapter 增加 icon_key；yield 事件增加 agent 元数据 |
| `src/planagent/services/debate.py` | 新增 `stream_debate` 异步生成器 |
| `src/planagent/services/assistant.py` | `stream` 方法使用 `stream_debate` |
| `src/planagent/api/routes/analysis.py` | 新增 `/debate/stream` SSE endpoint |
| `src/planagent/api/routes/ws.py` | 增加 NOTIFICATION_TOPICS + action_url |
| `frontend/src/lib/api.ts` | 新增 `streamDebate` 函数 + 类型定义 |
| `frontend/src/i18n/zh.ts` | 增加 agent/workflow 相关翻译 |
| `frontend/src/i18n/en.ts` | 同步英文翻译 |
| `frontend/src/app/assistant/page.tsx` | 使用 AgentDashboard；增加刷新按钮 |
| `frontend/src/app/workbench/page.tsx` | 增加刷新按钮 + AdviceTimeline + 实时更新 |
| `frontend/src/app/debate/page.tsx` | 增加实时辩论入口 + DebateStreamView |
| `frontend/src/components/AppShell.tsx` | 增加 UpdateBanner + workflow 导航 |

### 新建的文件
| 文件路径 | 用途 |
|---------|------|
| `frontend/src/components/AgentDashboard.tsx` | 多Agent搜索进度可视化 |
| `frontend/src/components/DebateStreamView.tsx` | 实时辩论流式渲染 |
| `frontend/src/components/AdviceTimeline.tsx` | 建议版本演化时间线 |
| `frontend/src/components/UpdateBanner.tsx` | 全屏更新通知横幅 |
| `frontend/src/components/WorkflowStepper.tsx` | 统一工作流进度条（Phase 5） |
| `frontend/src/app/workflow/page.tsx` | 统一工作流页面（Phase 5） |

---

## 五、技术细节备注

### 辩论流式化的关键难点
当前 `debate.py` 的 `_assess_debate` 方法内部调用 `_llm_debate_rounds`，这是一个一次性执行 4 轮 LLM 调用的方法。改造为流式需要：
1. 将 `_llm_debate_rounds` 拆分为 `_llm_single_round`
2. 在每轮之间插入中间结果持久化（可选）
3. 用 `AsyncIterator` 包装整个流程

### WebSocket 与 SSE 的选择
- SSE 适合单向推送（分析流、事件流）
- WebSocket 适合双向交互（通知确认、实时刷新触发）
- 建议保持现有架构：分析用 SSE，通知用 WebSocket

### SWR 缓存刷新策略
- 分析完成后 `globalMutate` 刷新所有相关 cache key
- 收到 WebSocket 通知后按 session_id 精确刷新
- 工作台手动刷新使用 `mutate(key)` + loading spinner

---

## 六、风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 辩论流式化改造可能影响现有 `trigger_debate` 接口 | 高 | 保留旧接口，新增 `stream_debate`，逐步迁移 |
| Agent 身份元数据可能使 SSE 事件体积增大 | 低 | 事件量小（每 source adapter 1-2 个事件），影响可忽略 |
| 全屏通知横幅可能过于打扰 | 中 | 增加"静默模式"开关，仅铃铛提醒 |
| 统一工作流页面可能与现有页面功能重叠 | 低 | 作为 Phase 5 独立页面，不影响现有路由 |
