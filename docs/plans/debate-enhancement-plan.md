# 辩论系统增强方案 — 基于外部调研的改进计划

> 来源：Vibe-Trading (HKUDS)、Thariq HTML文章、nature-skills 可视化工具
> 日期：2026-05-10
> 状态：待审批

---

## 一、调研来源与核心发现

### 1.1 Vibe-Trading (HKUDS) — DAG多智能体辩论

**项目**: github.com/HKUDS/Vibe-Trading
**核心架构**: 29个预设DAG配置，每个配置3-6个专业Agent

**关键设计模式**:

| 模式 | Vibe-Trading做法 | 明鉴现状 | 差距 |
|------|-----------------|---------|------|
| 执行拓扑 | DAG拓扑排序(Kahn算法)并行执行 | 顺序轮次制(立论→质询→修订→仲裁) | 明鉴更适合深度交叉质询，但可借鉴并行层 |
| 上下文传递 | `{upstream_context}`占位符注入 | 消息列表传递 | 可借鉴更结构化的注入方式 |
| 交叉审查 | CRO独立审计双方论点(1-5分可靠性) | arbitrator做最终裁决 | 可增加独立审计维度 |
| Token管理 | 80%时wrap-up nudge + 工具结果清理 | 无token预算管理 | 需要增加 |
| 共识机制 | Regime加权投票(趋势/震荡/流动性) | 阈值判断(confidence差值) | 可借鉴加权机制 |
| 减少幻觉 | 真实工具调用 + 对抗性角色分离 | LLM直接输出 | 可借鉴工具约束 |

### 1.2 Thariq — HTML作为Agent输出格式

**文章**: thariqs.github.io/html-effectiveness
**核心论点**: HTML比Markdown更适合Agent输出，因为：
- 信息密度更高（表格、SVG、交互控件）
- 可视化更强（内联图表、流程图）
- 支持交互（折叠/Tab/滑块/拖拽）
- 分享便捷（单文件，零依赖）
- 适合长文档（导航、锚点、搜索）

**20个Demo覆盖9大场景**: 探索规划、代码审查、设计系统、原型、图表、幻灯片、研究报告、状态报告、自定义编辑器

### 1.3 nature-skills — Nature级科研绘图

**项目**: github.com/Yuan1z0825/nature-skills (3.7k⭐)
**核心能力**:
- 10种图表族：柱状图、折线图、热力图、散点图/气泡图、雷达图/极坐标图、分布图、森林图、面积图、图像板、网络/矩阵图
- SVG优先输出：`svg.fonttype='none'`，文字保持可编辑`<text>`节点
- 5套域配色：PALETTE(语义色)、PASTEL(冷色系)、IMAGING(黑底荧光)、CLINICAL(时间序列)、GENOMICS(中性+波浪强调)
- 图表契约工作流：核心结论→证据层级→图表原型→面板映射→审稿人风险检查
- 三级递进：概览→偏差→关系

---

## 二、改进方案（3大方向，9个具体任务）

### 方向A：辩论系统增强（借鉴Vibe-Trading）

#### A1. 增加独立审计维度 — Cross-Examination Enhancement
**现状**: arbitrator做最终裁决，但无结构化的论点可靠性评分
**改进**: 
- 在challenger轮次中增加论点可靠性评分(1-5分)
- 增加确认偏误检测（cherry-picking检查）
- 增加盲区检测（双方都未覆盖的风险）
**改动文件**: `services/debate/adjudication.py`, `services/debate/rounds.py`
**工作量**: 中（约2天）

#### A2. Token预算管理与Wrap-up机制
**现状**: 无token预算管理，LLM可能无限生成
**改进**:
- 增加per-round token预算（默认60K tokens）
- 80%预算时注入wrap-up提示
- 保留最近3轮工具结果，清理更早的（如果未来辩论接入工具调用）
**改动文件**: `services/debate/rounds.py`, `services/debate/llm.py`
**工作量**: 小（约1天）

#### A3. 结构化少数意见（Structured Dissent）
**现状**: 少数意见仅存单个字符串 `minority_opinion: str`
**改进**:
```python
class MinorityDissent(BaseModel):
    claims: list[DissentClaim]           # 每个异议论点
    evidence_gaps: list[str]              # 证据缺口
    confidence_trajectory: list[float]    # 各轮置信度轨迹
    recommended_monitoring: list[str]     # 建议监控的指标
```
**改动文件**: `domain/models.py`, `services/debate/adjudication.py`
**工作量**: 中（约2天）

#### A4. Regime加权共识机制
**现状**: 简单阈值判断 `support_confidence >= challenge_confidence + 0.1`
**改进**:
- 增加领域权重配置（企业场景→加权经济分析；军事场景→加权地缘分析）
- 增加证据强度加权（一手证据 > 二手报道 > 推测）
- 共识结果增加权重分解说明
**改动文件**: `services/debate/adjudication.py`, `domain/models.py`
**工作量**: 中（约2天）

### 方向B：HTML报告系统（借鉴Thariq + nature-skills）

#### B1. 自包含HTML辩论报告模板
**现状**: Markdown导出 → markdown2 → weasyprint → PDF，无辩论专用模板
**改进**:
- 创建Jinja2 HTML模板：`templates/debate_report.html`
- 自包含单文件（内联CSS + SVG，零外部依赖）
- 包含：论点地图、可信度轨迹图、角色对比、证据链、少数意见高亮
- CSS变量主题系统（`--primary`, `--surface`, `--text` 等）
**改动文件**: 新增 `templates/debate_report.html`, 修改 `services/export.py`
**工作量**: 大（约3天）

#### B2. SVG图表生成服务
**现状**: 无可视化图表
**改进**:
- 基于matplotlib生成SVG图表（借鉴nature-skills的配色和布局）
- 4种核心图表：
  1. **可信度轨迹图**（折线图）：各角色各轮的confidence变化
  2. **论点对比图**（水平柱状图）：支持vs反对的论点权重
  3. **证据强度热力图**：各论点的证据质量矩阵
  4. **角色立场雷达图**：各领域专家的多维度评估
- SVG输出嵌入HTML报告
**改动文件**: 新增 `services/chart_generation.py`, 修改 `services/export.py`
**工作量**: 大（约3天）

#### B3. 交互式HTML元素
**现状**: 静态Markdown输出
**改进**:
- `<details>` 折叠：展开/收起各轮详细论证
- Tab切换：不同角色视角的快速切换
- 锚点导航：快速跳转到特定论点
- 打印友好：`@media print` 样式适配
**改动文件**: `templates/debate_report.html`
**工作量**: 小（约1天，与B1合并）

### 方向C：系统集成与报告联动

#### C1. 辩论结果嵌入仿真报告
**现状**: `DebateVerdictRecord` 与 `GeneratedReport` 分离存储
**改进**:
- 仿真报告增加"辩论分析"章节
- 自动嵌入辩论裁决、关键论点、少数意见
- 增加辩论与仿真结果的交叉引用
**改动文件**: `services/reporting.py`, `services/export.py`
**工作量**: 中（约2天）

#### C2. 辩论对比导出
**现状**: `DebateReplayService` 支持对比，但无导出端点
**改进**:
- 增加 `GET /export/debate/compare?ids=a,b` 端点
- 并排HTML报告：两个辩论的论点、裁决、证据对比
- 差异高亮
**改动文件**: `api/routes/export.py`, `services/export.py`
**工作量**: 中（约2天）

---

## 三、实施路径

### Phase 1：辩论核心增强（A1-A4）— 预计7天
优先级最高，直接提升辩论质量。

### Phase 2：HTML报告系统（B1-B3）— 预计5天
视觉化呈现，提升用户体验和分享能力。

### Phase 3：系统集成（C1-C2）— 预计3天
打通辩论与仿真的数据流。

**总计预估**: 15天（可根据优先级裁剪）

---

## 四、技术依赖

| 依赖 | 用途 | 是否已有 |
|------|------|---------|
| matplotlib | SVG图表生成 | ✅ 已有 |
| Jinja2 | HTML模板渲染 | 需确认 |
| weasyprint | PDF导出 | ✅ 已有(export.py中) |
| nature-skills配色 | 图表美观度 | 可直接借鉴(复制配色常量) |

---

## 五、风险点

1. **HTML模板维护成本**：比Markdown复杂，需要前端技能维护
2. **matplotlib SVG体积**：复杂图表SVG可能很大，需要压缩优化
3. **辩论数据模型变更**：A3需要修改Domain模型，需要数据库迁移
4. **向后兼容**：新报告格式需要同时支持旧API返回格式
