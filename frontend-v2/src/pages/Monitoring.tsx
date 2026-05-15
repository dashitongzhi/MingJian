import { Activity, Cpu, Gauge, RefreshCw, ShieldAlert } from 'lucide-react'
import { Card, CardBody, CardHeader } from '../components/ui/Card'
import { EmptyState } from '../components/ui/EmptyState'
import { LoadingSpinner } from '../components/ui/LoadingSpinner'
import { ErrorBanner } from '../components/ui/ErrorBanner'
import { monitoringApi, reportApi, sourcesApi } from '../api/endpoints'
import { useApi, useApiAction } from '../hooks/useApi'
import { ExpandableRecord, JsonBlock, MetricCard, asArray, asRecord, titleOf } from '../components/ui/DataSurface'

export default function Monitoring() {
  const { data: rules, loading, error, reload } = useApi(() => monitoringApi.listWatchRules())
  const { data: dashboard } = useApi(() => monitoringApi.getDashboard())
  const { data: queues } = useApi(() => monitoringApi.getQueueHealth())
  const { data: calibration } = useApi(() => reportApi.getCalibration())
  const { data: calibrationHistory } = useApi(() => reportApi.getCalibrationHistory())
  const { data: sourceChanges } = useApi(() => sourcesApi.listChanges())
  const { data: graph } = useApi(() => monitoringApi.getKnowledgeGraph())
  const { data: scoreboard } = useApi(() => monitoringApi.getScoreboard())
  const { execute: doTrigger, loading: triggering } = useApiAction((id: string) => monitoringApi.triggerWatchRule(id))

  if (loading) return <LoadingSpinner />
  if (error) return <ErrorBanner message={error} onRetry={reload} />

  const ruleList = asArray(rules)
  const queueList = asArray(asRecord(queues).queues ?? queues)
  const changeList = asArray(sourceChanges)
  const graphRecord = asRecord(graph)
  const nodeCount = asArray(graphRecord.nodes).length
  const edgeCount = asArray(graphRecord.edges).length

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="text-xs text-blue-300">Monitoring</p>
          <h1 className="mt-1 text-3xl font-semibold text-slate-50">监控中心</h1>
          <p className="mt-2 text-sm text-slate-500">覆盖 watch rules、队列健康、校准、知识图谱和数据源变更。</p>
        </div>
        <button onClick={reload} className="glass-button inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm text-slate-200"><RefreshCw className="h-4 w-4" />刷新</button>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
        <MetricCard label="监控规则" value={ruleList.length} icon={<ShieldAlert className="h-5 w-5" />} tone="blue" />
        <MetricCard label="队列" value={queueList.length} icon={<Cpu className="h-5 w-5" />} tone="violet" />
        <MetricCard label="源变更" value={changeList.length} icon={<Activity className="h-5 w-5" />} tone="amber" />
        <MetricCard label="知识图谱" value={`${nodeCount}/${edgeCount}`} hint="nodes / edges" icon={<Gauge className="h-5 w-5" />} tone="emerald" />
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1.2fr_0.8fr]">
        <Card>
          <CardHeader title="监控规则" />
          {ruleList.length === 0 ? <CardBody><EmptyState icon="▤" title="暂无监控规则" /></CardBody> : ruleList.map((rule, index) => {
            const record = asRecord(rule)
            const id = String(record.id ?? '')
            return (
              <div key={id || index} className="border-b border-slate-800/50 px-5 py-4 last:border-b-0">
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-slate-100">{titleOf(rule, `监控规则 ${index + 1}`)}</p>
                    <p className="mt-1 line-clamp-2 text-xs text-slate-500">{String(record.query ?? record.domain_id ?? '')}</p>
                  </div>
                  <button
                    disabled={triggering || !id}
                    onClick={() => doTrigger(id).then(reload)}
                    className="rounded-md border border-blue-400/20 bg-blue-500/10 px-3 py-1.5 text-xs text-blue-300 disabled:opacity-50"
                  >
                    触发
                  </button>
                </div>
              </div>
            )
          })}
        </Card>
        <Card>
          <CardHeader title="监控快照" />
          <CardBody className="space-y-3">
            <JsonBlock value={{ dashboard, queues, calibration, calibrationHistory, scoreboard }} />
          </CardBody>
        </Card>
      </div>

      <Card>
        <CardHeader title="最近源变更" />
        {changeList.length === 0 ? <CardBody><EmptyState icon="▦" title="暂无源变更" /></CardBody> : changeList.slice(0, 10).map((item, index) => <ExpandableRecord key={index} item={item} eyebrow="change" />)}
      </Card>
    </div>
  )
}
