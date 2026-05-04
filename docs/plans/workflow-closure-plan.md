# 明鉴决策工作流闭环改造 — 实施计划

> **目标**：打通"提问题→采集→辩论→监控→更新→决策"完整闭环
> **架构**：FastAPI + SQLAlchemy async + Redis Streams + pgvector
> **路径**：`/Users/kral/project/agents/src/planagent/`

---

## P0 — 打通核心闭环（阻塞性）

### P0-1: 来源并发采集 `asyncio.gather()`

**目标**：12个数据源从顺序执行改为并发执行，延迟从线性降为常数

**文件**：
- 修改: `services/analysis.py:208-281` (`_fetch_related_sources`)

**方案**：
```python
# 当前：顺序 for 循环
for source_config in sources:
    items = await self._fetch_source(source_config)
    all_items.extend(items)

# 改为：并发 gather，带超时和错误隔离
tasks = [self._fetch_source(sc) for sc in sources]
results = await asyncio.gather(*tasks, return_exceptions=True)
for result in results:
    if isinstance(result, Exception):
        logger.warning("Source fetch failed: %s", result)
    else:
        all_items.extend(result)
```

**关键**：每个 source fetch 加 `asyncio.timeout(30)` 单源超时，一个源失败不影响其他

---

### P0-2: 分析完成后自动创建 WatchRule

**目标**：assistant 完成后自动创建持续监控规则，打通 assistant→monitoring

**文件**：
- 修改: `services/assistant.py` (run/stream 方法末尾)
- 修改: `services/analysis.py` (add auto-watch logic)

**方案**：
```python
# 在 assistant.py run() 和 stream() 完成后：
async def _auto_create_watch(self, session, topic, domain_id):
    """分析完成后自动创建 WatchRule"""
    existing = await session.execute(
        select(WatchRule).where(WatchRule.topic == topic)
    )
    if existing.scalar_one_or_none():
        return  # 已存在，不重复创建
    
    rule = WatchRule(
        topic=topic,
        domain_id=domain_id,
        poll_interval_minutes=60,
        auto_trigger_simulation=True,
        auto_trigger_debate=True,
        change_significance_threshold="medium",
    )
    session.add(rule)
    await session.commit()
```

---

### P0-3: 重大变更自动触发重新辩论

**目标**：当监控检测到高显著性变更时，自动触发重新辩论

**文件**：
- 修改: `workers/watch_ingest.py` (变更检测后的处理逻辑)
- 修改: `services/debate.py` (添加 re-debate 入口)

**方案**：
```python
# watch_ingest.py 中，当 significance == "high" 时：
if significance == "high" and rule.auto_trigger_debate:
    await self.debate_service.trigger_debate(
        topic=rule.topic,
        domain_id=rule.domain_id,
        context=f"重大变更检测：{change_summary}",
        session_id=latest_session_id,
    )
```

---

### P0-4: 辩论增加迭代修订循环

**目标**：从"各说一次→仲裁"改为"立论→挑战→修订→再挑战→仲裁"真正的迭代共识

**文件**：
- 修改: `services/debate.py` (`trigger_debate` 方法)

**方案**：
```
Round 1: 立论 (advocate 立论, challenger 立论)
Round 2: 交叉质询 (advocate 质询 challenger, challenger 质询 advocate)
Round 3: 修订 (各方根据质询修订自己的立场)
Round 4: 仲裁 (arbitrator 基于所有轮次做出裁决)
```

每轮将前一轮的质询点注入下一轮的 prompt，实现真正的"修订"而非"各说各话"

---

## P1 — 提升决策质量

### P1-5: 完整证据注入辩论 prompt

**目标**：辩论时携带完整 evidence items/claims，而非仅 topic+summary

**文件**：
- 修改: `services/assistant.py:116-128` (context_lines 构建)
- 修改: `services/debate.py` (context 注入)

---

### P1-6: 多 provider 模型同时参与辩论

**目标**：advocate 用 OpenAI, challenger 用 Anthropic, 实现真正的认知多样性

**文件**：
- 修改: `services/debate.py` (per-role LLM 调用)
- 修改: `services/providers/` (支持按角色选择 provider)

---

### P1-7: 统一决策工作台页面

**目标**：一个页面综合：当前建议 + 置信度 + 证据 + 预测 + 风险

**文件**：
- 新建: `frontend/src/app/workbench/page.tsx`
- 新建: `frontend/src/i18n/` (workbench 相关翻译)
- 修改: `frontend/src/components/AppShell.tsx` (导航添加)

---

### P1-8: WebSocket 推送 + 用户通知

**目标**：重大变更时主动推送给用户，而非用户轮询

**文件**：
- 新建: `api/routes/ws.py` (WebSocket endpoint)
- 修改: `main.py` (注册 WebSocket 路由)
- 修改: `frontend/src/lib/api.ts` (WebSocket 客户端)
- 修改: `frontend/src/components/AppShell.tsx` (通知 toast/badge)

---

## P2 — 体验优化

### P2-9: 用户决策记录 + 结果闭环

**目标**：用户可以在系统中记录决策，追踪执行效果

**文件**：
- 修改: `domain/models.py` (新增 UserDecision 模型)
- 新建: `api/routes/decisions.py`
- 新建: `frontend/src/app/decisions/page.tsx`

---

### P2-10: Agent 级并行搜索可视化

**目标**：前端展示各 Agent 分别在搜索什么数据源

**文件**：
- 修改: `services/analysis.py` (SSE 事件增加 agent_id)
- 修改: `frontend/src/app/assistant/page.tsx` (并行搜索进度)

---

### P2-11: 用户参与辩论（投票/评论）

**目标**：用户可以对辩论论点投票、评论、介入

**文件**：
- 修改: `domain/models.py` (新增 DebateVote/DebateComment)
- 新建: `api/routes/debate_interactions.py`
- 修改: `frontend/src/app/debate/page.tsx` (投票/评论 UI)

---

### P2-12: 语义变更检测（LLM 辅助）

**目标**：用 LLM 判断变更的语义重要性，而非仅基于内容长度

**文件**：
- 修改: `services/change_detection.py`
- 修改: `services/providers/` (调用 LLM 评估)
