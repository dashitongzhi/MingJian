# PlanAgent 发布影响测试报告

生成时间：2026-04-28

## 测试目标

评估 PlanAgent 作为“可选择领域的预测型战略推演 Agent”发布后，可能对产品、融资叙事、竞品反应和早期客户转化产生什么影响。

本次测试使用 `corporate` 领域，主题为：

> PlanAgent 正式发布：一个可选择 corporate 或 military 领域的预测型战略推演 Agent。发布后产品获得早期用户关注，投资人询问预测准确率、信源声誉网络、双领域 domain pack、对抗性红队推演能力。与此同时，竞品可能复制通用 agent 工作流，客户担心军事 OSINT 边界和企业数据安全。

## 测试环境

- 数据库：临时 SQLite `/tmp/planagent-release-impact.db`
- 外部抓取：关闭
- OpenAI 模型调用：关闭
- 执行模式：inline ingest + inline simulation
- 领域：`corporate`
- 模拟 tick 数：`4`
- 对抗推演对手：`Fast-follow Agent Platform`

## 核心结论

当前测试结果显示，PlanAgent 发布后的基础影响偏正面，但系统给出的策略倾向是稳健验证，而不是立即激进扩张。

主要原因是：本次没有接入实时外部信源，系统只能基于输入描述进行内部推演。因此，它将“投资人关注、预测准确率、信源声誉、双领域能力、红队推演”识别为潜在增长信号，但仍建议继续监控这些信号是否被多来源确认。

## 模拟结果

- Simulation Run ID：`0bcd92ab-d241-41e1-ac59-1e41c5f27bc9`
- 完成 tick：`4`
- 记录决策：`4`
- 最终 runway：`78.0 weeks`
- pipeline coverage：`0.96`
- support load：`0.33`

报告摘要：

> PlanAgent completed 4 corporate ticks with 4 recorded decisions. Final runway is 78.0 weeks, pipeline coverage is 0.96, and support load is 0.33.

## 预测卡片

系统自动生成了 3 张预测卡片：

| 时间窗口 | 概率 | 预测 |
| --- | ---: | --- |
| 7 天 | 0.58 | 如果 `monitor` 持续 7 天，`brand_index` 和 `pipeline` 将小幅正向移动。 |
| 30 天 | 0.62 | 如果 `monitor` 持续 30 天，`brand_index` 和 `pipeline` 将小幅正向移动。 |
| 90 天 | 0.64 | 如果 `monitor` 持续 90 天，`brand_index` 和 `pipeline` 将小幅正向移动。 |

当前这些预测仍处于 `PENDING` 状态，还没有到期校验。

## 对抗性竞品推演

对手设定：`Fast-follow Agent Platform`

结果：

- 对抗模式：`competitor`
- adversarial run id：`e5103816-976f-4b56-aff8-03d8f9a64554`
- surprise index：`0.216`
- plan fragility：`0.316`

解释：

竞品快速跟进会带来一定压力，但当前推演认为冲击处于中低水平。PlanAgent 的差异化不应放在“通用 agent 工作流”，而应继续强化预测卡片、信源声誉、双领域 domain pack 和可校验推演链路。

系统建议的稳健动作：

- 定价和路线图要能扛住竞品降价或快速复制。
- 优先保护 runway 和可靠性，再扩大需求捕获。

## 风险与限制

本次测试关闭了外部信源，因此结论还不能代表真实发布后的市场反馈。

下一轮建议打开以下来源：

- Google News / RSS：验证是否有真实媒体或行业讨论。
- GitHub / Hacker News：验证开发者侧是否有兴趣。
- Reddit / X：验证社交讨论和早期用户反馈。
- 官方公告和竞品页面：验证竞品是否跟进类似叙事。

## 建议下一步

1. 使用真实公开信源重跑同一主题。
2. 为发布后 7/30/90 天建立正式预测卡片。
3. 每周运行 calibration worker，累计可展示的预测准确率。
4. 准备投资人 demo 时，重点展示：
   - 预测卡片
   - 信源声誉解释
   - 对抗性竞品推演
   - demo workbench 聚合视图

