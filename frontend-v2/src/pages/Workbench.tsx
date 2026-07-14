import { BriefcaseBusiness, GitBranch, Layers, MessageSquare, Network, RefreshCw, ShieldCheck, Sparkles } from 'lucide-react'
import { Card, CardBody, CardHeader } from '../components/ui/Card'
import { EmptyState } from '../components/ui/EmptyState'
import { LoadingSpinner } from '../components/ui/LoadingSpinner'
import { ErrorBanner } from '../components/ui/ErrorBanner'
import { simulationApi, workbenchApi } from '../api/endpoints'
import { useApi, useApiAction } from '../hooks/useApi'
import { ExpandableRecord, JsonBlock, MetricCard } from '../components/ui/DataSurface'
import { asArray, asRecord, titleOf } from '../components/ui/dataSurfaceUtils'
import { useState } from 'react'

export default function Workbench() {
  const { data: sessions, loading, error, reload } = useApi(() => workbenchApi.sessions())
  const { data: runs } = useApi(() => simulationApi.listRuns())
  const [selectedRunOverride, setSelectedRun] = useState<string | null>(null)
  const runList = asArray(runs)
  const firstRun = asRecord(runList[0])
  const defaultRunId = firstRun.id ? String(firstRun.id) : null
  const selectedRun = selectedRunOverride ?? defaultRunId
  const { data: workbench } = useApi(() => selectedRun ? workbenchApi.getRunWorkbench(selectedRun) : Promise.resolve(null), selectedRun)
  const { data: trace } = useApi(() => selectedRun ? workbenchApi.getDecisionTrace(selectedRun) : Promise.resolve([]), selectedRun)
  const { data: compare } = useApi(() => selectedRun ? workbenchApi.getScenarioCompare(selectedRun).catch(() => null) : Promise.resolve(null), selectedRun)
  const { data: replay } = useApi(() => selectedRun ? workbenchApi.getReplayPackage(selectedRun).catch(() => null) : Promise.resolve(null), selectedRun)
  const { data: jarvisRuns, reload: reloadJarvis } = useApi(() => selectedRun ? workbenchApi.listJarvisRuns(selectedRun).catch(() => []) : Promise.resolve([]), selectedRun)
  const { execute: runJarvis, loading: jarvisRunning } = useApiAction((data: unknown) => workbenchApi.createJarvisRun(data))

  if (loading) return <LoadingSpinner />
  if (error) return <ErrorBanner message={error} onRetry={reload} />

  const sessionList = asArray(sessions)
  const wb = asRecord(workbench)
  const traceList = asArray(trace)
  const evidenceGraph = asRecord(wb.evidence_graph)
  const graphNodes = asArray(evidenceGraph.nodes)
  const graphEdges = asArray(evidenceGraph.edges)
  const timeline = asArray(wb.timeline)
  const predictions = asArray(wb.prediction_versions)
  const debates = asArray(wb.debate_records)
  const jarvisList = asArray(jarvisRuns)

  const handleJarvis = async () => {
    if (!selectedRun) return
    const result = await runJarvis({ run_id: selectedRun, target_type: 'run' })
    if (result) reloadJarvis()
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="text-xs text-blue-300">Workbench</p>
          <h1 className="mt-1 text-3xl font-semibold text-slate-50">战略工作台</h1>
          <p className="mt-2 text-sm text-slate-500">汇总会话、推演工作台、决策轨迹、场景对比和回放包。</p>
        </div>
        <button onClick={reload} className="glass-button inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm text-slate-200"><RefreshCw className="h-4 w-4" />刷新</button>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
        <MetricCard label="战略会话" value={sessionList.length} icon={<BriefcaseBusiness className="h-5 w-5" />} tone="blue" />
        <MetricCard label="推演运行" value={runList.length} icon={<GitBranch className="h-5 w-5" />} tone="violet" />
        <MetricCard label="决策轨迹" value={traceList.length} icon={<Layers className="h-5 w-5" />} tone="emerald" />
        <MetricCard label="工作台字段" value={Object.keys(wb).length} icon={<MessageSquare className="h-5 w-5" />} tone="amber" />
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[0.9fr_1.4fr]">
        <Card>
          <CardHeader title="选择推演运行" />
          <CardBody className="space-y-2">
            {runList.length === 0 ? <EmptyState icon="▣" title="暂无推演运行" /> : runList.map((run, index) => {
              const record = asRecord(run)
              const id = String(record.id ?? '')
              return (
                <button
                  key={id || index}
                  onClick={() => setSelectedRun(id)}
                  className={`w-full rounded-lg border px-3 py-3 text-left transition ${selectedRun === id ? 'border-blue-400/40 bg-blue-500/12 text-blue-100' : 'border-slate-800/70 bg-slate-950/20 text-slate-300 hover:bg-blue-500/6'}`}
                >
                  <p className="truncate text-sm font-medium">{titleOf(run, `推演 ${index + 1}`)}</p>
                  <p className="mt-1 truncate text-xs text-slate-600">{String(record.domain_id ?? record.status ?? id)}</p>
                </button>
              )
            })}
          </CardBody>
        </Card>

        <Card>
          <CardHeader title={selectedRun ? '运行工作台详情' : '战略会话'} />
          {selectedRun ? (
            <CardBody className="space-y-4">
              <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
                <AuditStat label="证据节点" value={graphNodes.length} icon={<Network className="h-4 w-4" />} />
                <AuditStat label="证据关系" value={graphEdges.length} icon={<Layers className="h-4 w-4" />} />
                <AuditStat label="辩论记录" value={debates.length} icon={<MessageSquare className="h-4 w-4" />} />
                <AuditStat label="Jarvis 复核" value={jarvisList.length} icon={<ShieldCheck className="h-4 w-4" />} />
              </div>

              <div className="flex justify-end">
                <button
                  type="button"
                  onClick={handleJarvis}
                  disabled={jarvisRunning}
                  className="glass-button inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm text-slate-200 disabled:opacity-50"
                >
                  <Sparkles className="h-4 w-4" />{jarvisRunning ? '复核中...' : '运行 Jarvis 复核'}
                </button>
              </div>

              <AuditSection title="证据链节点" items={graphNodes.slice(0, 8)} eyebrow="node" empty="暂无证据节点" />
              <AuditSection title="决策时间线" items={timeline.slice(0, 8)} eyebrow="event" empty="暂无时间线事件" />
              <AuditSection title="决策轨迹" items={traceList.slice(0, 8)} eyebrow="trace" empty="暂无决策轨迹" />
              <AuditSection title="预测与辩论" items={[...predictions.slice(0, 4), ...debates.slice(0, 4)]} eyebrow="audit" empty="暂无预测或辩论记录" />
              <AuditSection title="Jarvis 自愈复核" items={jarvisList.slice(0, 5)} eyebrow="jarvis" empty="暂无 Jarvis 复核" />

              <JsonBlock value={{ compare, replay }} />
            </CardBody>
          ) : sessionList.length === 0 ? (
            <CardBody><EmptyState icon="▤" title="暂无会话" /></CardBody>
          ) : sessionList.slice(0, 8).map((session, index) => <ExpandableRecord key={index} item={session} eyebrow="session" />)}
        </Card>
      </div>
    </div>
  )
}

function AuditStat({ label, value, icon }: { label: string; value: number; icon: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-slate-800/70 bg-slate-950/25 px-4 py-3">
      <div className="flex items-center justify-between gap-3">
        <span className="text-xs text-slate-500">{label}</span>
        <span className="text-blue-300">{icon}</span>
      </div>
      <p className="mt-2 text-2xl font-semibold text-slate-100">{value}</p>
    </div>
  )
}

function AuditSection({
  title,
  items,
  eyebrow,
  empty,
}: {
  title: string
  items: unknown[]
  eyebrow: string
  empty: string
}) {
  return (
    <section className="rounded-lg border border-slate-800/70 bg-slate-950/20">
      <div className="flex items-center justify-between border-b border-slate-800/60 px-5 py-3">
        <h3 className="text-sm font-medium text-slate-200">{title}</h3>
        <span className="text-xs text-slate-600">{items.length}</span>
      </div>
      {items.length === 0 ? (
        <div className="p-5"><EmptyState icon="▤" title={empty} /></div>
      ) : (
        items.map((item, index) => <ExpandableRecord key={`${eyebrow}-${index}`} item={item} eyebrow={eyebrow} />)
      )}
    </section>
  )
}
