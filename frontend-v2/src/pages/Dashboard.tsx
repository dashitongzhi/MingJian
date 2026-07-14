import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Activity,
  ArrowRight,
  Bot,
  ClipboardList,
  Database,
  FileSearch,
  FileText,
  FlaskConical,
  Landmark,
  Loader2,
  Radio,
  Send,
  ShieldCheck,
  TrendingUp,
} from 'lucide-react'
import { Card, CardHeader, CardBody } from '../components/ui/Card'
import { EmptyState } from '../components/ui/EmptyState'
import { consoleApi, agentsApi, simulationApi, evidenceApi, monitoringApi, reportApi, sourcesApi, debateApi, assistantApi } from '../api/endpoints'
import { useApi, useApiAction } from '../hooks/useApi'
import { ExpandableRecord, MetricCard, ProgressBar } from '../components/ui/DataSurface'
import { asArray, asRecord, formatDate, titleOf } from '../components/ui/dataSurfaceUtils'

const decisionTemplates = [
  {
    label: '进入新市场',
    icon: Landmark,
    domainId: 'corporate',
    prompt: '评估我们是否应该在未来 6 个月进入东南亚企业 AI 决策支持市场，需要给出机会、风险、进入路径和监控指标。',
    outcome: '市场进入建议',
  },
  {
    label: '供应链风险',
    icon: Activity,
    domainId: 'corporate',
    prompt: '分析未来 30 天关键供应链中断风险，识别高影响事件、预警信号、替代方案和需要持续监控的数据源。',
    outcome: '风险矩阵',
  },
  {
    label: '竞品战略',
    icon: FileSearch,
    domainId: 'corporate',
    prompt: '追踪主要竞品最近的产品、招聘、融资、定价和客户动作，判断他们下一步战略意图并给出应对方案。',
    outcome: '竞争情报报告',
  },
  {
    label: '政策影响',
    icon: ClipboardList,
    domainId: 'auto',
    prompt: '评估近期监管政策变化对我们的业务、客户采购和产品路线的影响，区分短期动作与长期结构性变化。',
    outcome: '政策影响判断',
  },
]

export default function Dashboard() {
  const navigate = useNavigate()
  const [decisionText, setDecisionText] = useState(decisionTemplates[0].prompt)
  const [selectedTemplate, setSelectedTemplate] = useState(0)
  const [localError, setLocalError] = useState<string | null>(null)
  const { data: health, loading: hLoad } = useApi(() => consoleApi.health())
  const { data: consoleData } = useApi(() => consoleApi.get())
  const { data: agentsResp, loading: aLoad } = useApi(() => agentsApi.list())
  const { data: agentStatus } = useApi(() => agentsApi.status())
  const { data: simRuns, loading: sLoad } = useApi(() => simulationApi.listRuns())
  const { data: evidenceResp, loading: eLoad } = useApi(() => evidenceApi.list())
  const { data: debates } = useApi(() => debateApi.list())
  const { data: watchRules, loading: wLoad } = useApi(() => monitoringApi.listWatchRules())
  const { data: dashboard } = useApi(() => monitoringApi.getDashboard())
  const { data: predictions } = useApi(() => reportApi.listPredictions())
  const { data: sources } = useApi(() => sourcesApi.listStates())
  const { execute: createAssistantSession, loading: creatingSession, error: createSessionError } = useApiAction(
    (data: { topic: string; session_name: string; domain_id: string }) => assistantApi.createSession(data)
  )
  const { execute: createAssistantRun, loading: creatingRun, error: createRunError } = useApiAction(
    (data: { session_id: string; message: string; domain_id: string }) => assistantApi.createRun(data)
  )

  const loading = hLoad || aLoad || sLoad || eLoad || wLoad
  const agents = asArray(asRecord(agentsResp).agents ?? agentsResp)
  const readyAgents = Number(asRecord(agentStatus).ready ?? agents.length)
  const runs = asArray(simRuns)
  const evidence = asArray(asRecord(evidenceResp).items ?? evidenceResp)
  const debateList = asArray(debates)
  const watchList = asArray(watchRules)
  const predList = asArray(predictions)
  const sourceList = asArray(sources)
  const onlineSources = sourceList.filter((s) => {
    const status = String(asRecord(s).status ?? '').toLowerCase()
    return ['active', 'online', 'ok', 'healthy'].includes(status)
  })
  const recentReports = [...predList, ...debateList, ...runs].slice(0, 6)
  const riskItems = [
    ...watchList.map((item, index) => ({ item, score: 9.2 - index * 0.6 })),
    ...predList.map((item, index) => ({ item, score: 7.8 - index * 0.3 })),
  ].slice(0, 5)
  const activeTemplate = decisionTemplates[selectedTemplate]
  const submitting = creatingSession || creatingRun
  const submitError = localError || createSessionError || createRunError

  const applyTemplate = (index: number) => {
    setSelectedTemplate(index)
    setDecisionText(decisionTemplates[index].prompt)
    setLocalError(null)
  }

  const handleStartDecision = async (event: FormEvent) => {
    event.preventDefault()
    const topic = decisionText.trim()
    if (!topic) {
      setLocalError('请输入要分析的决策问题。')
      return
    }
    setLocalError(null)

    const session = await createAssistantSession({
      topic,
      session_name: `${activeTemplate.label} · ${topic.slice(0, 28)}`,
      domain_id: activeTemplate.domainId,
    })
    const sessionId = typeof session?.id === 'string' ? session.id : ''
    if (!sessionId) {
      setLocalError('后端没有返回会话 ID，请检查 assistant sessions 接口。')
      return
    }

    const run = await createAssistantRun({
      session_id: sessionId,
      message: topic,
      domain_id: activeTemplate.domainId,
    })
    if (!run) return
    navigate(`/ai-assistant?session=${encodeURIComponent(sessionId)}`)
  }

  return (
    <div className="space-y-5">
      <section className="cockpit-hero p-4 md:p-5">
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1.15fr)_360px]">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="cockpit-kicker">Decision Workspace</p>
                <h1 className="mt-2 text-2xl font-semibold tracking-normal text-slate-50 sm:text-3xl md:text-4xl">你现在要判断什么？</h1>
                <p className="editorial-copy mt-3 max-w-2xl text-base leading-7">提交一个真实决策问题，明鉴会创建战略会话，调度证据采集、推演、辩论和报告生成，并在助手页沉淀为可追踪的决策工作流。</p>
              </div>
	              <div className="flex items-center gap-2 rounded-full border border-emerald-400/18 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-300">
                <span className="h-2.5 w-2.5 rounded-full bg-emerald-400" />
                {health ? '后端在线' : loading ? '控制面同步中' : '后端状态未知'}
              </div>
            </div>

	            <form onSubmit={handleStartDecision} className="mt-6 rounded-[24px] border border-slate-800/70 bg-slate-950/26 p-2 shadow-[inset_0_1px_0_rgba(255,255,255,0.035)]">
              <textarea
                value={decisionText}
                onChange={(event) => {
                  setDecisionText(event.target.value)
                  setLocalError(null)
                }}
                rows={5}
	                className="editorial-copy min-h-[136px] w-full resize-none rounded-[18px] border-0 bg-transparent px-3 py-3 text-base leading-7 placeholder:text-slate-600 focus:outline-none"
                placeholder="例如：我们是否应该进入某个市场、采购某项技术、调整定价、回应竞品动作？"
              />
              <div className="flex flex-col gap-3 border-t border-slate-800/70 px-2 py-2 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
	                  <span className="rounded-full border border-slate-800/70 bg-slate-950/28 px-2.5 py-1">证据采集</span>
	                  <span className="rounded-full border border-slate-800/70 bg-slate-950/28 px-2.5 py-1">多智能体辩论</span>
	                  <span className="rounded-full border border-slate-800/70 bg-slate-950/28 px-2.5 py-1">版本化建议</span>
                </div>
                <button
                  type="submit"
                  disabled={submitting}
	                  className="primary-ink-button inline-flex h-10 items-center justify-center gap-2 px-4 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                  {submitting ? '正在创建工作流' : '开始决策分析'}
                  {!submitting && <ArrowRight className="h-4 w-4" />}
                </button>
              </div>
            </form>

            {submitError && (
	              <div className="mt-3 rounded-[18px] border border-red-400/20 bg-red-500/10 px-3 py-2 text-sm text-red-300">
                {submitError}
              </div>
            )}

            <div className="mt-4 grid gap-2 md:grid-cols-2 xl:grid-cols-4">
              {decisionTemplates.map((item, index) => {
                const Icon = item.icon
                const selected = selectedTemplate === index
                return (
                  <button
                    key={item.label}
                    type="button"
                    onClick={() => applyTemplate(index)}
	                    className={`rounded-[18px] border p-3 text-left transition ${selected ? 'border-amber-400/32 bg-amber-500/10 text-slate-100' : 'paper-row text-slate-400 hover:bg-amber-500/8 hover:text-slate-200'}`}
                  >
                    <div className="flex items-center gap-2">
                      <Icon className={selected ? 'h-4 w-4 text-amber-300' : 'h-4 w-4 text-slate-500'} />
                      <span className="text-sm font-semibold">{item.label}</span>
                    </div>
                    <p className="mt-2 text-xs leading-5 text-slate-500">{item.outcome}</p>
                  </button>
                )
              })}
            </div>
          </div>

	          <div className="rounded-[22px] border border-slate-800/70 bg-slate-950/24 p-4">
            <div className="flex items-center justify-between">
              <p className="cockpit-kicker">Artifact Preview</p>
              <FileText className="h-4 w-4 text-slate-500" />
            </div>
            <div className="mt-5 space-y-4">
              {[
                ['1', 'Evidence Map', '来源新鲜度、可信度、争议点与引用链'],
                ['2', 'Debate Trace', '支持方、反方、仲裁方的论证与修正'],
                ['3', 'Decision Brief', '推荐动作、置信度、风险和监控规则'],
              ].map(([step, title, body]) => (
                <div key={title} className="grid grid-cols-[28px_minmax(0,1fr)] gap-3">
	                  <span className="mono-data grid h-7 w-7 place-items-center rounded-full border border-amber-400/18 bg-amber-500/10 text-xs font-semibold text-amber-300">{step}</span>
                  <div>
                    <p className="text-sm font-semibold text-slate-200">{title}</p>
                    <p className="editorial-copy mt-1 text-xs leading-5">{body}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="计划智能体" value={agents.length} hint={`${readyAgents} ready`} icon={<Bot className="h-5 w-5" />} tone="blue" />
        <MetricCard label="执行/推演任务" value={runs.length} hint="simulation runs" icon={<FlaskConical className="h-5 w-5" />} tone="violet" />
        <MetricCard label="验证证据" value={evidence.length} hint={`${debateList.length} debates`} icon={<ShieldCheck className="h-5 w-5" />} tone="emerald" />
        <MetricCard label="数据源状态" value={`${onlineSources.length}/${sourceList.length}`} hint={`${watchList.length} watch rules`} icon={<Database className="h-5 w-5" />} tone="amber" />
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_1fr_1.1fr]">
        <Card>
          <CardHeader title="数据源状态" action={<span className="text-xs text-blue-300">查看全部</span>} />
          <CardBody className="space-y-3">
            {sourceList.length === 0 ? <EmptyState icon="📡" title="暂无数据源状态" /> : sourceList.slice(0, 7).map((source, index) => {
              const record = asRecord(source)
              const status = String(record.status ?? 'unknown')
              const ok = ['active', 'online', 'ok', 'healthy'].includes(status.toLowerCase())
              return (
                <div key={String(record.key ?? record.id ?? index)} className="flex items-center justify-between gap-3 rounded-lg border border-slate-800/60 bg-slate-950/20 px-3 py-2.5">
                  <div className="flex min-w-0 items-center gap-3">
                    <Radio className={`h-4 w-4 shrink-0 ${ok ? 'text-emerald-300' : 'text-amber-300'}`} />
                    <div className="min-w-0">
                      <p className="truncate text-sm text-slate-200">{String(record.name ?? record.key ?? '数据源')}</p>
                      <p className="truncate text-xs text-slate-600">{formatDate(record.last_check ?? record.last_success)}</p>
                    </div>
                  </div>
                  <span className={ok ? 'text-xs text-emerald-300' : 'text-xs text-amber-300'}>{status}</span>
                </div>
              )
            })}
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="关键风险与机会" action={<span className="text-xs text-blue-300">风险评分说明</span>} />
          <CardBody className="space-y-3">
            {riskItems.length === 0 ? <EmptyState icon="⚑" title="暂无风险项" /> : riskItems.map(({ item, score }, index) => (
              <div key={index} className="grid grid-cols-[28px_minmax(0,1fr)_46px] items-center gap-3">
                <span className="grid h-7 w-7 place-items-center rounded-full bg-amber-500/15 text-sm font-semibold text-amber-300">{index + 1}</span>
                <p className="truncate text-sm text-slate-300">{titleOf(item)}</p>
                <span className="text-right font-mono text-sm text-slate-200">{score.toFixed(1)}</span>
              </div>
            ))}
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="进行中的任务" action={<span className="text-xs text-blue-300">前往任务</span>} />
          <CardBody className="space-y-4">
            {runs.length === 0 ? <EmptyState icon="▣" title="暂无任务" /> : runs.slice(0, 6).map((run, index) => {
              const record = asRecord(run)
              const pct = Number(record.progress ?? record.confidence ?? (0.36 + index * 0.09))
              return (
                <div key={String(record.id ?? index)} className="grid grid-cols-[minmax(0,1fr)_88px] items-center gap-4">
                  <div className="min-w-0">
                    <p className="truncate text-sm text-slate-300">{titleOf(run, `任务 ${index + 1}`)}</p>
                    <p className="text-xs text-slate-600">{String(record.domain_id ?? record.status ?? 'running')}</p>
                  </div>
                  <div className="space-y-1">
                    <ProgressBar value={pct} />
                    <p className="text-right text-[11px] text-slate-500">{Math.round((pct <= 1 ? pct * 100 : pct))}%</p>
                  </div>
                </div>
              )
            })}
          </CardBody>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader title="最近生成的报告/预测/辩论" />
          {recentReports.length === 0 ? <CardBody><EmptyState icon="📄" title="暂无生成内容" /></CardBody> : recentReports.map((item, index) => (
            <ExpandableRecord key={index} item={item} eyebrow="recent" />
          ))}
        </Card>
        <Card>
          <CardHeader title="后端控制面快照" />
          <CardBody className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {[
              { label: '监控项', value: watchList.length, icon: <Activity className="h-4 w-4 text-emerald-300" /> },
              { label: '预测序列', value: predList.length, icon: <TrendingUp className="h-4 w-4 text-blue-300" /> },
              { label: '控制台字段', value: Object.keys(asRecord(consoleData)).length, icon: <FileText className="h-4 w-4 text-slate-300" /> },
              { label: '监控看板字段', value: Object.keys(asRecord(dashboard)).length, icon: <Activity className="h-4 w-4 text-violet-300" /> },
            ].map((item) => (
              <div key={item.label} className="rounded-lg border border-slate-800/60 bg-slate-950/24 p-4">
                <div className="flex items-center justify-between">
                  <p className="text-xs text-slate-500">{item.label}</p>
                  {item.icon}
                </div>
                <p className="mt-2 text-2xl font-semibold text-slate-100">{item.value}</p>
              </div>
            ))}
          </CardBody>
        </Card>
      </div>
    </div>
  )
}
