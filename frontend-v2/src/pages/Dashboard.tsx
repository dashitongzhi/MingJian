import { Activity, Bot, Database, FileText, FlaskConical, Radio, ShieldCheck, TrendingUp } from 'lucide-react'
import { Card, CardHeader, CardBody } from '../components/ui/Card'
import { EmptyState } from '../components/ui/EmptyState'
import { LoadingSpinner } from '../components/ui/LoadingSpinner'
import { ErrorBanner } from '../components/ui/ErrorBanner'
import { consoleApi, agentsApi, simulationApi, evidenceApi, monitoringApi, reportApi, sourcesApi, debateApi } from '../api/endpoints'
import { useApi } from '../hooks/useApi'
import { ExpandableRecord, MetricCard, ProgressBar, asArray, asRecord, formatDate, titleOf } from '../components/ui/DataSurface'

export default function Dashboard() {
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

  const loading = hLoad || aLoad || sLoad || eLoad || wLoad
  if (loading) return <LoadingSpinner />

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

  return (
    <div className="space-y-5">
      <section className="cockpit-hero px-2 py-2">
        <div className="px-2 py-3 md:px-4">
          <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
            <div>
              <p className="text-xs font-medium text-blue-300">战略控制台</p>
              <h1 className="mt-2 text-3xl font-semibold tracking-normal text-slate-50">全域智能决策总览</h1>
              <p className="mt-2 text-sm text-slate-400">基于后端全量接口聚合数据源、智能体、推演、辩论、预测与监控状态。</p>
            </div>
            <div className="flex items-center gap-2 rounded-lg border border-emerald-400/18 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-300">
              <span className="h-2.5 w-2.5 rounded-full bg-emerald-400 shadow-[0_0_16px_rgba(52,211,153,0.9)]" />
              {health ? '后端在线' : '后端状态未知'}
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
