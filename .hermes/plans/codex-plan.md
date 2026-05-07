# PlanAgent 前端优化实施计划

> 目标：让前端完整反映理想工作流——提交问题 → 多 Agent 分别搜索不同网站 → 辩论中心多模型建议/交叉质询/修正 → 首次结果 → 持续采集+定期/事件驱动更新 → 建议直接展示+刷新按钮

---

## 一、现状分析

### 已有基础（做得好的部分）
- ✅ SSE 流式分析：`/assistant/stream` 支持 `source_start`/`source_complete`/`source_error` 事件
- ✅ SourceSearchProgress 组件：已能显示各来源的搜索进度（provider/label/status/count）
- ✅ WebSocket 通知：`/ws/notifications` 推送高优先级事件
- ✅ 4 轮辩论系统后端完整：support/challenge/arbitrator + verdict
- ✅ 监控看板：SSE 事件流、WatchRule 健康状态

### 关键差距
1. **辩论不实时**：`debate.py` 的 `trigger_debate()` 是同步 4 轮一次性完成，前端只能在全部完成后一次性显示
2. **Agent 缺乏身份**：搜索进度只显示 provider 名称，用户看不到"哪个 Agent 在做什么"
3. **建议没有版本时间线**：Workbench 展示当前版本，但无法查看历史版本变化对比
4. **刷新按钮不醒目**：Workbench 无手动刷新按钮，用户无法主动触发更新
5. **更新通知不突出**：WebSocket 通知只有简单 toast，缺少全站醒目提醒
6. **辩论过程不透明**：用户只能看到辩论结果，无法看到每轮推理过程

---

## 二、具体变更方案

### 任务 1：辩论实时流式化（后端）

**目标**：辩论每完成一轮即通过 SSE 推送给前端

**文件**：`src/planagent/services/debate.py`

**变更**：
- 将 `_assess_debate()` 拆分为 `_assess_debate_streaming()` 异步生成器
- 每完成一轮（support/challenge/arbitrator）立即 `yield` 一个事件
- 在 `_llm_debate_rounds()` 中，每轮 LLM 调用后立即 yield 结果
- 在 `trigger_debate()` 中新增可选 `stream=True` 参数，返回 `AsyncIterator`
- 保留原有同步接口不变（向后兼容）

**新增事件类型**：
```python
yield AssistantEvent("debate_round_start", {"round_number": n, "role": role})
yield AssistantEvent("debate_round_complete", {"round_number": n, "role": role, "position": ..., "confidence": ...})
yield AssistantEvent("debate_verdict", {"verdict": ..., "confidence": ...})
```

**预估工作量**：3-4 小时

---

### 任务 2：辩论实时流式化（assistant.py 适配）

**目标**：`StrategicAssistantService.stream()` 使用流式辩论

**文件**：`src/planagent/services/assistant.py`

**变更**：
- 修改 `stream()` 方法中辩论部分（约 L137-L159）
- 将 `debate = await self.debate_service.trigger_debate(...)` 替换为流式调用
- 每收到一轮辩论结果立即 `yield self._event("debate_round", ...)`
- 辩论完成后 yield 最终 verdict
- 保留 `run()` 方法使用同步接口

**预估工作量**：1-2 小时

---

### 任务 3：Agent 身份标识增强（后端）

**目标**：每个搜索 Agent 有名称、图标、当前任务描述

**文件**：
- `src/planagent/services/analysis.py`（`_fetch_related_sources_with_events` 方法）

**变更**：
- 在 `source_start` 事件中增加 `agent_name`、`agent_icon`、`task_description` 字段
- 在 `source_complete` 事件中增加 `items_preview`（前 3 条标题）
- 在 `source_error` 事件中增加 `retry_suggested` 字段
- 为每个 source adapter 定义人性化元数据映射

**新增事件 payload 示例**：
```python
{
  "provider": "google_news",
  "label": "Google News",
  "agent_name": "新闻 Agent",
  "agent_icon": "📰",
  "task_description": "正在搜索 Google News 获取最新新闻报道",
  "items_preview": ["标题1", "标题2", "标题3"]  # source_complete 时
}
```

**预估工作量**：2-3 小时

---

### 任务 4：Agent 搜索面板重构（前端）

**目标**：将 SourceSearchProgress 升级为"多 Agent 工作面板"

**文件**：`frontend/src/app/assistant/page.tsx`

**变更**：
- 重构 `SourceSearchProgress` → `AgentWorkPanel` 组件
- 每个 Agent 显示：图标 + 名称 + 当前任务 + 进度条 + 结果数量
- 增加 Agent 状态动画：搜索中脉冲、完成打勾、失败叉号
- 新增"全部 Agent"进度总览条
- 在 `SourceSearchState` 类型中增加 `agent_name`、`agent_icon`、`task_description`、`items_preview` 字段
- 修改 SSE 事件处理（L596-L639），解析新字段

**新增组件**：`frontend/src/components/AgentWorkPanel.tsx`

**预估工作量**：3-4 小时

---

### 任务 5：辩论实时显示增强（前端 - assistant 页面）

**目标**：辩论过程每轮实时流入，带角色动画

**文件**：`frontend/src/app/assistant/page.tsx`

**变更**：
- 在 SSE 事件处理中增加 `debate_round_start` 事件（L670-L681 区域）
- 新增"辩论进行中"状态指示器
- 辩论轮次卡片增加入场动画（已有的 `animate-slideIn`）
- 增加辩论进度指示：`第 1/4 轮 - 支持方发言中...`
- 新增 `debate_verdict` 事件处理，显示最终裁决卡片

**新增状态**：
```typescript
const [debateStatus, setDebateStatus] = useState<"idle" | "in_progress" | "complete">("idle");
const [currentDebateRound, setCurrentDebateRound] = useState<{round: number, role: string} | null>(null);
```

**预估工作量**：2-3 小时

---

### 任务 6：辩论实时显示增强（前端 - debate 页面）

**目标**：辩论页面支持实时观看进行中的辩论

**文件**：`frontend/src/app/debate/page.tsx`

**变更**：
- 新增 WebSocket/SSE 连接，监听 `debate.round.*` 事件
- 在 `debateList` 中区分 `status: "IN_PROGRESS"` vs `"COMPLETED"`
- 进行中的辩论显示实时进度条
- 辩论完成后自动刷新完整数据
- 新增"实时辩论"标签页

**新增 API**：`api.ts` 中增加 `streamDebate(debateId, onEvent)` 函数

**预估工作量**：3-4 小时

---

### 任务 7：建议版本时间线（前端 - Workbench）

**目标**：在 Workbench 中展示建议的历史版本变化

**文件**：
- `frontend/src/app/workbench/page.tsx`
- `frontend/src/lib/api.ts`

**变更**：
- `PredictionTimeline` 组件已存在且功能完善，但需要增强：
  - 增加版本间 diff 高亮（哪些发现变了、置信度变化原因）
  - 增加"触发原因"标签（manual_review / new_evidence / debate_verdict）
- 新增 `SuggestionTimeline` 组件，专门展示建议（recommendations）的版本演化
- API 端：`GET /sessions/{id}/recommendation-history` 返回建议变更记录

**新增 API**：
```typescript
export interface RecommendationVersion {
  id: string;
  version_number: number;
  recommendations: WorkbenchRecommendation[];
  trigger_type: string;
  trigger_summary: string;
  confidence: number;
  created_at: string;
}
export const fetchRecommendationHistory = (sessionId: string) =>
  fetch_<RecommendationVersion[]>(`/assistant/sessions/${sessionId}/recommendation-history`);
```

**新增组件**：`frontend/src/components/SuggestionTimeline.tsx`

**后端文件**：`src/planagent/api/routes/analysis.py`（新增端点）
**后端文件**：`src/planagent/services/assistant.py`（新增方法）

**预估工作量**：4-5 小时

---

### 任务 8：醒目刷新按钮（前端 - Workbench + Assistant）

**目标**：在关键位置增加醒目的手动刷新/重新分析按钮

**文件**：
- `frontend/src/app/workbench/page.tsx`
- `frontend/src/app/assistant/page.tsx`

**变更 - Workbench**：
- 在页面顶部右侧增加"🔄 刷新建议"按钮（大号、醒目）
- 点击后调用 `POST /assistant/sessions/{id}/refresh` 触发后台重新分析
- 刷新期间显示进度条 + 预计时间
- 刷新完成后自动更新 Workbench 数据

**变更 - Assistant**：
- 在会话详情面板增加"🔄 重新分析"按钮
- 点击后以相同 topic 重新触发 `streamAssistant`
- 完成后自动更新会话列表和详情

**新增 API**：
```typescript
export const refreshSession = (sessionId: string) =>
  fetch_<StrategicSession>(`/assistant/sessions/${sessionId}/refresh`, { method: "POST" });
```

**新增 i18n 键**（zh.ts）：
```typescript
workbench: {
  refreshAdvice: "刷新建议",
  refreshInProgress: "正在刷新...",
  refreshComplete: "刷新完成",
  lastRefresh: "上次刷新",
}
assistant: {
  reAnalyze: "重新分析",
  reAnalyzeInProgress: "正在重新分析...",
}
```

**预估工作量**：3-4 小时

---

### 任务 9：全站更新通知横幅（前端）

**目标**：当后台有新数据时，在前端显示醒目通知横幅

**文件**：
- `frontend/src/components/UpdateBanner.tsx`（新建）
- `frontend/src/components/AppShell.tsx`
- `frontend/src/app/assistant/page.tsx`
- `frontend/src/app/workbench/page.tsx`

**变更**：
- 新建 `UpdateBanner` 组件：固定在页面顶部的可点击横幅
- 横幅内容："🔄 有新的分析结果" / "📊 预测已更新" / "⚖️ 新辩论已完成"
- 点击横幅跳转到对应页面并自动加载最新数据
- 在 AppShell 中集成 WebSocket 消息处理
- 优先级：新辩论结果 > 预测更新 > 来源变更

**UpdateBanner 组件规格**：
```tsx
interface UpdateBannerProps {
  type: "debate" | "prediction" | "source_change";
  title: string;
  body: string;
  sessionId?: string;
  onDismiss: () => void;
  onAction: () => void;
}
```

**WebSocket 消息扩展**（后端 ws.py）：
- 增加 `session_id` 和 `action_url` 字段（已有 session_id）
- 增加 `banner_type` 字段区分横幅样式

**预估工作量**：3-4 小时

---

### 任务 10：持续监控入口优化（前端 - Workbench）

**目标**：在 Workbench 中直接显示监控状态和最新更新

**文件**：`frontend/src/app/workbench/page.tsx`

**变更**：
- 在 Workbench 侧边栏底部增加"监控状态"卡片
- 显示：WatchRule 健康状态、下次轮询时间、最近变更数
- 增加"查看监控详情"链接跳转到 /monitoring
- 增加"暂停/恢复监控"快捷按钮

**新增 API**：
```typescript
export const fetchSessionWatchStatus = (sessionId: string) =>
  fetch_<{ watch_rule: WatchRule | null; recent_changes: number; next_poll_at: string | null }>(
    `/assistant/sessions/${sessionId}/watch-status`
  );
```

**预估工作量**：2-3 小时

---

### 任务 11：ProcessVisualizer 升级（前端组件）

**目标**：将 ProcessVisualizer 改为完整的"工作流可视化"组件

**文件**：`frontend/src/components/ProcessVisualizer.tsx`

**变更**：
- 阶段进度条增加时间标注（每阶段耗时）
- 增加"辩论阶段"特殊展示：3 个角色头像 + 对话气泡样式
- 增加"当前 Agent"聚焦指示器
- Stage 进度条改为可点击跳转到对应阶段内容
- 增加"全流程时间线"模式：水平滚动时间线视图

**预估工作量**：3-4 小时

---

### 任务 12：i18n 中文翻译完善

**文件**：`frontend/src/i18n/zh.ts`、`frontend/src/i18n/en.ts`

**新增翻译键**（已在各任务中列出，汇总如下）：

```typescript
// Agent 工作面板
agentWork: {
  title: "Agent 工作面板",
  allAgents: "全部 Agent",
  searching: "搜索中",
  completed: "已完成",
  failed: "失败",
  itemsFound: "条结果",
  noAgents: "暂无活跃 Agent",
},

// 辩论实时
debate: {
  inProgress: "辩论进行中",
  roundProgress: "第 {round}/4 轮",
  roleSpeaking: "{role} 发言中...",
  verdictPending: "等待裁决...",
  liveDebate: "实时辩论",
},

// 刷新
workbench: {
  refreshAdvice: "刷新建议",
  refreshInProgress: "正在刷新...",
  refreshComplete: "刷新完成",
  lastRefresh: "上次刷新",
},

// 更新通知
updateBanner: {
  newResults: "有新的分析结果",
  predictionUpdated: "预测已更新",
  debateCompleted: "新辩论已完成",
  viewNow: "立即查看",
  dismiss: "忽略",
},

// 监控状态
monitoring: {
  watchStatus: "监控状态",
  nextPoll: "下次轮询",
  pauseMonitoring: "暂停监控",
  resumeMonitoring: "恢复监控",
},
```

**预估工作量**：1 小时

---

## 三、文件清单

### 需修改的文件
| 文件 | 变更类型 | 关联任务 |
|------|---------|---------|
| `src/planagent/services/debate.py` | 重大修改 | 任务 1 |
| `src/planagent/services/assistant.py` | 修改 | 任务 2, 7, 8, 10 |
| `src/planagent/services/analysis.py` | 修改 | 任务 3 |
| `src/planagent/api/routes/analysis.py` | 修改 | 任务 7, 8, 10 |
| `src/planagent/api/routes/ws.py` | 修改 | 任务 9 |
| `frontend/src/app/assistant/page.tsx` | 重大修改 | 任务 4, 5, 8 |
| `frontend/src/app/debate/page.tsx` | 重大修改 | 任务 6 |
| `frontend/src/app/workbench/page.tsx` | 重大修改 | 任务 7, 8, 10 |
| `frontend/src/lib/api.ts` | 修改 | 任务 6, 7, 8, 10 |
| `frontend/src/components/AppShell.tsx` | 修改 | 任务 9 |
| `frontend/src/components/ProcessVisualizer.tsx` | 修改 | 任务 11 |
| `frontend/src/i18n/zh.ts` | 修改 | 任务 12 |
| `frontend/src/i18n/en.ts` | 修改 | 任务 12 |

### 需新建的文件
| 文件 | 用途 | 关联任务 |
|------|------|---------|
| `frontend/src/components/AgentWorkPanel.tsx` | Agent 工作面板组件 | 任务 4 |
| `frontend/src/components/SuggestionTimeline.tsx` | 建议版本时间线 | 任务 7 |
| `frontend/src/components/UpdateBanner.tsx` | 全站更新通知横幅 | 任务 9 |

---

## 四、实施顺序

```
Phase 1（基础 - 后端流式化）     预估：6-9 小时
├── 任务 1：辩论流式化（debate.py）
├── 任务 2：assistant.py 适配
└── 任务 3：Agent 身份标识（analysis.py）

Phase 2（核心体验 - 前端实时化）  预估：10-14 小时
├── 任务 4：Agent 工作面板（最高优先级 - 视觉冲击最大）
├── 任务 5：辩论实时显示（assistant 页）
└── 任务 6：辩论实时显示（debate 页）

Phase 3（交互增强）              预估：9-12 小时
├── 任务 7：建议版本时间线
├── 任务 8：醒目刷新按钮
└── 任务 10：监控状态入口

Phase 4（通知与可视化）           预估：6-8 小时
├── 任务 9：全站更新通知横幅
├── 任务 11：ProcessVisualizer 升级
└── 任务 12：i18n 翻译完善

总计预估：31-43 小时（约 5-7 个工作日）
```

---

## 五、优先级排序（按用户感知价值）

1. 🔴 **任务 4：Agent 工作面板** - 用户最直观感受到"多 Agent 并行工作"
2. 🔴 **任务 1+2：辩论流式化** - 让辩论过程从黑盒变为透明
3. 🔴 **任务 8：醒目刷新按钮** - 用户最常交互的功能
4. 🟡 **任务 5：辩论实时显示** - 与任务 1 配合的前端体验
5. 🟡 **任务 9：全站更新通知** - 提升被动更新感知
6. 🟡 **任务 3：Agent 身份标识** - 增强 Agent 工作面板的细节
7. 🟢 **任务 7：建议版本时间线** - 高级用户的核心需求
8. 🟢 **任务 6：辩论页面实时化** - 独立辩论查看场景
9. 🟢 **任务 10：监控状态入口** - 便利性改进
10. 🟢 **任务 11：ProcessVisualizer 升级** - 视觉增强
11. ⚪ **任务 12：i18n** - 贯穿所有任务

---

## 六、技术风险与注意事项

### 风险 1：辩论流式化的 DB 事务管理
- 当前 `trigger_debate()` 一次性 commit 所有轮次
- 流式化需要每轮 commit 或使用 savepoint
- **建议**：使用 `session.begin_nested()` + 每轮 flush，最后统一 commit

### 风险 2：SSE 连接稳定性
- 长时间 SSE 连接（辩论可能需要 2-5 分钟）可能被代理超时断开
- **建议**：增加 keepalive 心跳（每 15 秒），前端增加自动重连逻辑

### 风险 3：WebSocket + SSE 双通道同步
- 辩论实时数据走 SSE（与 assistant 流同通道），通知走 WebSocket
- **建议**：辩论相关事件统一走 SSE，WebSocket 只用于跨页面通知

### 风险 4：前端状态管理复杂度
- assistant 页面已有大量 state，增加实时辩论会更复杂
- **建议**：考虑使用 `useReducer` 或引入轻量状态管理（Zustand）

---

## 七、验证方案

### 单元测试
- 辩论流式化：验证每轮事件正确 yield
- Agent 身份：验证事件 payload 包含新字段

### 集成测试
- 完整工作流：提交问题 → 观察 Agent 搜索 → 辩论实时流入 → 结果展示
- 刷新功能：刷新按钮 → 后台重新分析 → 前端自动更新

### E2E 测试
- 在浏览器中打开 assistant 页面
- 输入主题并执行分析
- 验证 Agent 面板实时显示搜索进度
- 验证辩论轮次逐个出现
- 验证完成后跳转 Workbench 有刷新按钮
- 验证监控通知横幅出现

---

## 八、不改动的部分（明确排除）

- ❌ 后端整体架构不变（FastAPI + SQLAlchemy + EventBus）
- ❌ 前端框架不变（Next.js 15 + SWR）
- ❌ 数据库 schema 不变（辩论相关表结构已满足需求）
- ❌ 不增加新的页面路由
- ❌ 不修改 simulation/evidence/predictions 页面
- ❌ 不引入新的前端依赖（现有的 SWR/lucide-react/sonner 已够用）

---

*计划创建时间：2026-05-04*
*预计完成时间：5-7 个工作日*
