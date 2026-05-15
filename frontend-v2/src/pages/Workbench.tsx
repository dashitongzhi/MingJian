import { BriefcaseBusiness, GitBranch, Layers, MessageSquare, RefreshCw } from 'lucide-react'
import { Card, CardBody, CardHeader } from '../components/ui/Card'
import { EmptyState } from '../components/ui/EmptyState'
import { LoadingSpinner } from '../components/ui/LoadingSpinner'
import { ErrorBanner } from '../components/ui/ErrorBanner'
import { simulationApi, workbenchApi } from '../api/endpoints'
import { useApi } from '../hooks/useApi'
import { ExpandableRecord, JsonBlock, MetricCard, asArray, asRecord, titleOf } from '../components/ui/DataSurface'
import { useState } from 'react'

export default function Workbench() {
  const { data: sessions, loading, error, reload } = useApi(() => workbenchApi.sessions())
  const { data: runs } = useApi(() => simulationApi.listRuns())
  const [selectedRun, setSelectedRun] = useState<string | null>(null)
  const { data: workbench } = useApi(() => selectedRun ? workbenchApi.getRunWorkbench(selectedRun) : Promise.resolve(null), [selectedRun])
  const { data: trace } = useApi(() => selectedRun ? workbenchApi.getDecisionTrace(selectedRun) : Promise.resolve([]), [selectedRun])
  const { data: compare } = useApi(() => selectedRun ? workbenchApi.getScenarioCompare(selectedRun).catch(() => null) : Promise.resolve(null), [selectedRun])
  const { data: replay } = useApi(() => selectedRun ? workbenchApi.getReplayPackage(selectedRun).catch(() => null) : Promise.resolve(null), [selectedRun])

  if (loading) return <LoadingSpinner />
  if (error) return <ErrorBanner message={error} onRetry={reload} />

  const sessionList = asArray(sessions)
  const runList = asArray(runs)
  const wb = asRecord(workbench)
  const traceList = asArray(trace)

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
              <JsonBlock value={{ workbench, trace, compare, replay }} />
            </CardBody>
          ) : sessionList.length === 0 ? (
            <CardBody><EmptyState icon="▤" title="暂无会话" /></CardBody>
          ) : sessionList.slice(0, 8).map((session, index) => <ExpandableRecord key={index} item={session} eyebrow="session" />)}
        </Card>
      </div>
    </div>
  )
}
