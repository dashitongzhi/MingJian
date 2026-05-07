# PlanAgent 前端优化 — 最优整合方案

> 融合 Hermes/Claude/Codex 三方精华，取共识、弃冗余

---

## 设计原则

1. **不加新页面** — 现有 /assistant + /workbench + /debate 已覆盖全部阶段，增强即可
2. **不加新依赖** — 现有 SWR + lucide-react + sonner 已够用
3. **不改后端架构** — 只在现有服务上增量修改
4. **不改DB schema** — 辩论表结构已满足流式需求
5. **按用户感知价值排序** — 用户最直观感受到的先做

---

## 总览：4个批次 × 全部可并行

| 批次 | 内容 | 核心改动 | 工时 |
|------|------|---------|------|
| A | 辩论流式化 | debate.py + assistant.py + 前端实时展示 | 14h |
| B | Agent身份感知 | analysis.py + ProcessVisualizer 重构 | 6h |
| C | 刷新按钮+建议时间线 | workbench + assistant 页面 | 6h |
| D | 通知增强+工作流进度 | UpdateBanner + ProcessVisualizer升级 | 6h |
| **合计** | | | **32h** |

---

## 批次A：辩论流式化（后端14h 核心体验）

### A1. 后端：debate.py 新增 stream_debate()

**文件**: `src/planagent/services/debate.py`

**改动**:
- 将 `_llm_debate_rounds()` 拆为4次独立 `_llm_single_round()` 调用
- 新增 `stream_debate(session, payload) -> AsyncIterator[DebateEvent]` 异步生成器
- 每轮完成后立即 yield：
  ```python
  yield {"event": "debate_round_start", "data": {"round": 1, "role": "advocate"}}
  # ... LLM调用 ...
  yield {"event": "debate_round_complete", "data": {"round": 1, "role": "advocate", "position": "...", "confidence": 0.8}}
  ```
- 最后 yield `debate_verdict`
- 保留原有 `trigger_debate()` 同步接口（向后兼容）
- DB策略：`session.begin_nested()` 每轮flush，最后统一commit

**工作量**: 6h

### A2. 后端：assistant.py 适配流式辩论

**文件**: `src/planagent/services/assistant.py`

**改动**:
- `stream()` 方法中辩论部分改用 `debate_service.stream_debate()`
- 每收到一轮辩论结果立即 yield SSE事件给前端
- `run()` 方法保持同步接口不变

**工作量**: 2h

### A3. 后端：新增辩论流式SSE端点

**文件**: `src/planagent/api/routes/analysis.py`

**新增端点**:
```python
@router.post("/debate/stream")
async def stream_debate_endpoint(payload, request, session):
    # 独立的辩论流式端点，支持手动发起实时辩论
```

**工作量**: 1h

### A4. 前端：assistant页面辩论实时展示

**文件**: `frontend/src/app/assistant/page.tsx`

**改动**:
- SSE事件处理增加 `debate_round_start`/`debate_round_complete`/`debate_verdict`
- Debate tab 改为实时渲染：
  - "第1/4轮 · 支持方正在陈述..." 状态条
  - 每轮完成时卡片带入场动画
  - 辩论完成时显示最终裁决卡片
- 新增状态：`debateStatus: "idle" | "in_progress" | "complete"` + `currentRound`

**工作量**: 3h

### A5. 前端：debate页面支持实时辩论

**文件**: `frontend/src/app/debate/page.tsx`

**改动**:
- 新增"发起实时辩论"按钮（不仅手动输入ID）
- 进行中的辩论在列表中显示实时进度条
- 辩论完成后自动刷新完整数据
- `api.ts` 新增 `streamDebate()` 函数

**工作量**: 2h

---

## 批次B：Agent身份感知（后端+前端 6h）

### B1. 后端：source_start事件增加Agent元数据

**文件**: `src/planagent/services/analysis.py`

**改动**:
- `SourceAdapter` dataclass 新增字段：
  ```python
  agent_name: str      # "新闻探员" / "社媒探员" / "数据探员"
  agent_icon: str      # "📰" / "🔍" / "📊" / "🌐" / "🐦"
  task_desc: str       # "正在搜索 Google News 获取最新新闻报道"
  ```
- `_fetch_related_sources_with_events()` 的 `source_start` 事件增加这些字段
- `source_complete` 事件增加 `items_preview`（前3条标题）
- 为12个adapter定义人性化元数据映射表

**工作量**: 2h

### B2. 前端：ProcessVisualizer重构为Agent工作面板

**文件**: `frontend/src/components/ProcessVisualizer.tsx`

**改动**:
- SourceSearchProgress区域重构为Agent卡片网格：
  - 每个Agent：图标 + 名称 + "正在搜索XX..." + 脉冲动画
  - 搜索中：蓝色脉冲 + 进度条
  - 完成：绿色勾 + 收集条数
  - 失败：红色叉 + 错误信息
- 完成的Agent卡片可展开，显示搜集到的前3条标题
- 顶部增加"全部Agent"进度总览条（如 8/12 完成）

**工作量**: 4h

---

## 批次C：刷新按钮+建议时间线（纯前端 6h）

### C1. Workbench醒目刷新按钮

**文件**: `frontend/src/app/workbench/page.tsx`

**改动**:
- 页面顶部右侧增加大号"🔄 刷新建议"按钮
- 点击后：
  - 调用 watch rule trigger（如果该session有关联的watch rule）
  - 或重新运行分析（如果没有watch rule）
- 刷新期间：按钮旋转动画 + "正在刷新..."
- 刷新完成：SWR自动更新 + sonner toast "建议已更新"

**工作量**: 1.5h

### C2. 建议版本时间线

**文件**: `frontend/src/app/workbench/page.tsx`

**改动**:
- 从现有 `prediction_versions` 数据提取建议演化
- 新增 `AdviceTimeline` 组件（内联在workbench页面，不单独建文件）：
  - 竖线时间轴 + 每个版本节点
  - 节点内容：时间 + 概率变化（↑绿色/↓红色）+ 触发原因
  - 与上一版不同的建议用绿色高亮标记
  - 点击节点展开详情
- 放置在"当前建议"卡片下方

**工作量**: 3h

### C3. Assistant页面重新分析按钮

**文件**: `frontend/src/app/assistant/page.tsx`

**改动**:
- 分析完成后，结果区域顶部增加"🔄 重新分析"按钮
- 以相同参数重新触发 streamAssistant

**工作量**: 1.5h

---

## 批次D：通知增强+工作流进度（前端 6h）

### D1. UpdateBanner全站通知横幅

**新文件**: `frontend/src/components/UpdateBanner.tsx`

**改动**:
- 固定在页面顶部的可点击横幅
- 严重度分级：
  - 🔴 重大事件（红色脉冲，不自动消失）
  - 🟡 一般更新（黄色，5秒淡出）
  - 🟢 低优先级（绿色，3秒淡出）
- 包含：类型图标 + 标题 + 摘要 + "查看详情"按钮 + "忽略"按钮
- `action_url` 字段支持点击直达对应页面

**文件**: `frontend/src/components/AppShell.tsx`
- WebSocket消息处理增加横幅状态管理
- 高严重度通知同时播放提示音（可选）

**工作量**: 3h

### D2. ProcessVisualizer升级为工作流进度条

**文件**: `frontend/src/components/ProcessVisualizer.tsx`

**改动**:
- Stage进度条增加时间标注（每阶段耗时）
- 当前阶段高亮 + 脉冲动画
- 已完成阶段显示 ✅ + 耗时
- 辩论阶段特殊展示：3个角色头像 + 对话气泡样式
- Stage可点击跳转到对应tab

**工作量**: 2h

### D3. i18n翻译完善

**文件**: `frontend/src/i18n/zh.ts` + `en.ts`

**新增翻译**:
```typescript
agent: {
  title: "Agent 工作面板",
  scout: "情报侦察",
  newsAgent: "新闻探员",
  socialAgent: "社媒探员",
  dataAgent: "数据探员",
  webAgent: "网页探员",
  searching: "搜索中",
  completed: "已完成",
  failed: "失败",
  collectedItems: "条情报",
  clickToExpand: "点击查看详情",
},
debate: {
  inProgress: "辩论进行中",
  roundProgress: "第 {round}/4 轮",
  roleAdvocate: "支持方",
  roleChallenger: "挑战方",
  roleArbitrator: "仲裁方",
  speaking: "{role}发言中...",
  verdictPending: "等待裁决...",
  startLiveDebate: "发起实时辩论",
},
workbench: {
  refreshAdvice: "刷新建议",
  refreshInProgress: "正在刷新...",
  refreshComplete: "建议已更新",
  lastRefresh: "上次刷新",
  reAnalyze: "重新分析",
},
update: {
  newResults: "有新的分析结果",
  predictionUpdated: "预测已更新",
  debateCompleted: "新辩论已完成",
  viewNow: "立即查看",
  dismiss: "忽略",
},
```

**工作量**: 1h

---

## 文件清单

### 修改的文件（13个）
| 文件 | 批次 | 改动量 |
|------|------|--------|
| `src/planagent/services/debate.py` | A | ⭐大 |
| `src/planagent/services/assistant.py` | A | 中 |
| `src/planagent/services/analysis.py` | B | 小 |
| `src/planagent/api/routes/analysis.py` | A | 小 |
| `frontend/src/components/ProcessVisualizer.tsx` | B,D | ⭐大 |
| `frontend/src/components/AppShell.tsx` | D | 小 |
| `frontend/src/app/assistant/page.tsx` | A,C | ⭐大 |
| `frontend/src/app/debate/page.tsx` | A | 中 |
| `frontend/src/app/workbench/page.tsx` | C | ⭐大 |
| `frontend/src/lib/api.ts` | A | 小 |
| `frontend/src/i18n/zh.ts` | D | 小 |
| `frontend/src/i18n/en.ts` | D | 小 |

### 新建的文件（1个）
| 文件 | 用途 |
|------|------|
| `frontend/src/components/UpdateBanner.tsx` | 全站更新通知横幅 |

---

## 实施方式

4个批次全部可并行，适合4个Codex同时跑：

| Codex | 批次 | 预计耗时 |
|-------|------|---------|
| Codex-1 | A（辩论流式化） | 8-10min |
| Codex-2 | B（Agent身份） | 5-6min |
| Codex-3 | C（刷新+时间线） | 5-6min |
| Codex-4 | D（通知+进度） | 5-6min |

---

## 技术风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 辩论流式化DB事务 | 高 | `session.begin_nested()` 每轮flush，最后统一commit |
| SSE长连接超时 | 中 | 15秒keepalive心跳，前端自动重连 |
| assistant页面state膨胀 | 中 | 辩论状态用独立useState，不与现有state混合 |
| 刷新按钮触发后端负载 | 低 | 防抖：刷新按钮点击后3秒内不可重复点击 |

---

## 三方方案取舍说明

| 决策点 | 最优选择 | 理由 |
|--------|---------|------|
| 是否新建/workflow页面 | ❌ 不建 | Hermes+Codex共识，现有页面已覆盖，避免维护负担 |
| 建议版本历史用新API还是现有数据 | 现有数据 | Hermes+Claude共识，prediction_versions已够用 |
| 优先级：辩论流式 vs Agent面板 | 辩论流式优先 | 用户核心诉求是"看到质询过程"，辩论是最关键的透明度缺失 |
| ProcessVisualizer是否单独升级 | 融入批次B+D | Codex的好想法，与Agent身份感知合并实施更高效 |
| 新建几个组件文件 | 只建1个UpdateBanner | 其余组件内联在现有页面中，减少文件碎片化 |
