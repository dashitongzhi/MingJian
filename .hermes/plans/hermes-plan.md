# PlanAgent 前端优化实施计划（Hermes/mimo 方案）

> 目标工作流：提交问题 → 多Agent分头搜索 → 辩论中心多模型交锋 → 首次结果 → 持续采集+定时/突发更新 → 前端直接展示建议+刷新按钮

---

## 核心设计理念

**不加新页面，不加新依赖，只增强现有页面的"工作流感知"。**

用户理想工作流的6个阶段，对应现有页面的增强：

| 阶段 | 现有页面 | 增强点 |
|------|---------|--------|
| ① 提交问题 | /assistant | ✅ 已满足 |
| ② 多Agent搜索 | /assistant → Process tab | 增加Agent身份卡片 |
| ③ 辩论交锋 | /assistant → Debate tab + /debate | 流式逐轮展示 |
| ④ 首次结果 | /assistant + /workbench | ✅ 已满足 |
| ⑤ 持续更新 | /workbench + /monitoring | 增加刷新按钮+版本时间线 |
| ⑥ 建议展示 | /workbench | 增加变更高亮+刷新按钮 |

---

## 实施方案（4个批次，可并行）

### 批次1：Agent身份感知（纯前端，1天）

**改动文件**：
- `frontend/src/components/ProcessVisualizer.tsx` — 重构SourceSearchProgress部分
- `frontend/src/app/assistant/page.tsx` — 处理新的SSE事件字段
- `frontend/src/i18n/zh.ts` + `en.ts` — 新增翻译

**具体改动**：
1. 后端 `analysis.py` 的 `source_start` 事件增加 `agent_name`、`agent_icon`、`task_desc` 字段
2. ProcessVisualizer 中每个搜索源改为"智能体卡片"样式：
   - 左侧图标（📰新闻探员、🔍社媒探员、📊数据探员等）
   - 中间：名称 + "正在搜索XX..." + 进度动画
   - 右侧：状态（搜索中🔵 / 完成✅ / 失败❌）+ 收集条数
3. 搜索完成的Agent卡片可展开，显示搜集到的前3条标题

**工作量**：后端2h + 前端4h = **6h**

---

### 批次2：辩论流式化（后端+前端，2天）

**后端改动**：
- `src/planagent/services/debate.py` — 新增 `stream_debate()` 异步生成器
  - 将 `_llm_debate_rounds()` 拆为4次独立调用
  - 每轮完成后 yield 事件：`debate_round_start` → `debate_round_complete`
  - 最后 yield `debate_verdict`
  - 保留原有 `trigger_debate()` 同步接口（向后兼容）
- `src/planagent/services/assistant.py` — `stream()` 方法中辩论部分改用流式调用
- `src/planagent/api/routes/analysis.py` — 新增 `POST /debate/stream` SSE端点

**前端改动**：
- `frontend/src/app/assistant/page.tsx` Debate tab：
  - 新增 `debate_round_start`/`debate_round_complete` 事件处理
  - 辩论进行中显示"第1/4轮 · 支持方正在陈述..."的状态条
  - 每轮完成时卡片带入场动画
- `frontend/src/app/debate/page.tsx`：
  - 新增"发起实时辩论"按钮（不仅手动输入ID）
  - 进行中的辩论在列表中显示实时进度条
- `frontend/src/lib/api.ts` — 新增 `streamDebate()` 函数

**工作量**：后端8h + 前端6h = **14h**

---

### 批次3：刷新按钮+建议时间线（纯前端，1天）

**改动文件**：
- `frontend/src/app/workbench/page.tsx` — 增加刷新按钮和时间线
- `frontend/src/app/assistant/page.tsx` — 增加重新分析按钮

**具体改动**：
1. **刷新按钮**（workbench页面顶部）：
   - 大号醒目的"🔄 刷新建议"按钮
   - 点击后调用 watch rule trigger 或重新运行分析
   - 刷新期间显示旋转动画 + "正在刷新..."
   - 刷新完成后SWR自动更新数据

2. **建议版本时间线**（workbench当前建议下方）：
   - 从 `prediction_versions` 提取建议演化
   - 竖线时间轴 + 每个版本节点：时间 + 概率变化 + 触发原因
   - 与上一版不同的部分用绿色/红色高亮
   - 点击节点展开详情

3. **重新分析按钮**（assistant会话详情）：
   - 分析完成后显示"🔄 重新分析"按钮
   - 以相同参数重新触发streamAssistant

**工作量**：**6h**

---

### 批次4：更新通知增强（前端，1天）

**改动文件**：
- `frontend/src/components/UpdateBanner.tsx`（新建）
- `frontend/src/components/AppShell.tsx` — 集成横幅
- `frontend/src/app/workbench/page.tsx` — 实时更新指示器

**具体改动**：
1. **UpdateBanner组件**：
   - 固定在页面顶部的可点击横幅
   - 类型：🔴重大事件（红色脉冲）/ 🟡一般更新（黄色）/ 🟢低优先级（绿色）
   - 包含：图标 + 标题 + "查看详情"按钮 + "忽略"按钮
   - 5秒后自动淡出（高严重度不自动消失）

2. **工作台实时更新指示器**：
   - 当WebSocket收到该session的更新通知时
   - 页面顶部显示"检测到新数据，点击刷新"横幅
   - 显示"上次更新：3分钟前"

3. **后端ws.py增加action_url字段**，前端可直接跳转

**工作量**：**6h**

---

## 文件清单汇总

### 修改的文件（13个）
| 文件 | 批次 | 改动量 |
|------|------|--------|
| `src/planagent/services/analysis.py` | 1 | 小 |
| `src/planagent/services/debate.py` | 2 | 大 |
| `src/planagent/services/assistant.py` | 2 | 中 |
| `src/planagent/api/routes/analysis.py` | 2 | 小 |
| `src/planagent/api/routes/ws.py` | 4 | 小 |
| `frontend/src/components/ProcessVisualizer.tsx` | 1 | 中 |
| `frontend/src/components/AppShell.tsx` | 4 | 小 |
| `frontend/src/app/assistant/page.tsx` | 1,2,3 | 大 |
| `frontend/src/app/debate/page.tsx` | 2 | 中 |
| `frontend/src/app/workbench/page.tsx` | 3,4 | 大 |
| `frontend/src/lib/api.ts` | 2 | 小 |
| `frontend/src/i18n/zh.ts` | 1 | 小 |
| `frontend/src/i18n/en.ts` | 1 | 小 |

### 新建的文件（1个）
| 文件 | 用途 |
|------|------|
| `frontend/src/components/UpdateBanner.tsx` | 全站更新通知横幅 |

**不新建页面，不新建路由，不加新依赖。**

---

## 总工作量

| 批次 | 内容 | 工时 | 可并行 |
|------|------|------|--------|
| 批次1 | Agent身份感知 | 6h | ✅ |
| 批次2 | 辩论流式化 | 14h | ✅ |
| 批次3 | 刷新+时间线 | 6h | ✅ |
| 批次4 | 通知增强 | 6h | ✅ |
| **合计** | | **32h** | 4个Codex并行≈2天 |

---

## 技术风险

| 风险 | 影响 | 缓解 |
|------|------|------|
| 辩论流式化DB事务 | 高 | 用session.begin_nested()每轮flush |
| SSE长连接超时 | 中 | 15秒keepalive心跳 |
| assistant页面state膨胀 | 中 | 考虑useReducer |

---

## 不做的事（明确排除）

- ❌ 不加新页面路由（/workflow等）
- ❌ 不改后端架构
- ❌ 不改数据库schema
- ❌ 不加新npm依赖
- ❌ 不动simulation/evidence/predictions页面
