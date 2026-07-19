import { CheckCircle2, Cpu, Database, Gauge, Layers3, RefreshCw, ShieldAlert, Signal } from 'lucide-react'
import { Card, CardBody, CardHeader } from '../components/ui/Card'
import { EmptyState } from '../components/ui/EmptyState'
import { LoadingSpinner } from '../components/ui/LoadingSpinner'
import { ErrorBanner } from '../components/ui/ErrorBanner'
import { monitoringApi, sourcesApi } from '../api/endpoints'
import { useApi, useApiAction } from '../hooks/useApi'
import { ExpandableRecord, JsonBlock, MetricCard } from '../components/ui/DataSurface'
import { asArray, asRecord, titleOf } from '../components/ui/dataSurfaceUtils'

function compact(value: unknown, fallback = '0') {
  if (typeof value === 'number') return value.toLocaleString()
  if (typeof value === 'string' && value.trim()) return value
  return fallback
}

function DetailStat({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="rounded-md border border-slate-800/70 bg-slate-950/35 px-3 py-2">
      <div className="text-[11px] text-slate-500">{label}</div>
      <div className="mt-1 text-sm font-medium text-slate-100">{compact(value)}</div>
    </div>
  )
}

export default function Monitoring() {
  const { data: rules, loading, error, reload } = useApi(() => monitoringApi.listWatchRules())
  const { data: dashboard } = useApi(() => monitoringApi.getDashboard())
  const { data: queues } = useApi(() => monitoringApi.getQueueHealth())
  const { data: platformTopology } = useApi(() => monitoringApi.getPlatformTopology())
  const { data: sourceChanges } = useApi(() => sourcesApi.listChanges())
  const { data: graph } = useApi(() => monitoringApi.getKnowledgeGraph())
  const { execute: doTrigger, loading: triggering, error: triggerError } = useApiAction((id: string) => monitoringApi.triggerWatchRule(id))

  if (loading) return <LoadingSpinner />
  if (error) return <ErrorBanner message={error} onRetry={reload} />

  const ruleList = asArray(rules)
  const queueList = asArray(asRecord(queues).queues ?? queues)
  const changeList = asArray(sourceChanges)
  const graphRecord = asRecord(graph)
  const dashboardRecord = asRecord(dashboard)
  const topology = asRecord(platformTopology)
  const topologyIssues = asArray(topology.issues)
  const database = asRecord(topology.database)
  const storage = asRecord(topology.object_storage)
  const eventBus = asRecord(topology.event_bus)
  const workflow = asRecord(topology.workflow)
  const nodeCount = asArray(graphRecord.nodes).length
  const edgeCount = asArray(graphRecord.edges).length
  const activeRules = ruleList.filter((rule) => asRecord(rule).enabled !== false).length
  const highChanges = changeList.filter((item) => String(asRecord(item).significance ?? '').toLowerCase() === 'high').length

  return (
    <div className="space-y-5">
      <section className="cockpit-hero px-5 py-5 md:px-6">
        <div className="flex flex-col gap-5 xl:flex-row xl:items-end xl:justify-between">
          <div className="max-w-3xl">
            <p className="cockpit-kicker">Community Monitoring Cockpit</p>
            <h1 className="mt-2 text-3xl font-semibold text-slate-50 md:text-4xl">监控中心</h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-400">
              面向本地自托管的 24 小时监控窗口，聚合 watch rules、队列健康、知识图谱和数据源变更。
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <span className="cockpit-pill cockpit-pill-success"><CheckCircle2 className="h-3.5 w-3.5" />24 小时窗口</span>
            <span className="cockpit-pill"><Layers3 className="h-3.5 w-3.5" />{queueList.length} queue lanes</span>
            <button onClick={reload} className="glass-button inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm text-slate-200">
              <RefreshCw className="h-4 w-4" />刷新
            </button>
          </div>
        </div>
      </section>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
        <MetricCard label="运行规则" value={`${activeRules}/${ruleList.length}`} icon={<ShieldAlert className="h-5 w-5" />} tone="blue" />
        <MetricCard label="队列通道" value={queueList.length} icon={<Cpu className="h-5 w-5" />} tone="violet" />
        <MetricCard label="源变更" value={changeList.length} hint={`${highChanges} high priority`} icon={<Signal className="h-5 w-5" />} tone={highChanges > 0 ? 'red' : 'amber'} />
        <MetricCard label="知识图谱" value={`${nodeCount}/${edgeCount}`} hint="nodes / edges" icon={<Gauge className="h-5 w-5" />} tone="emerald" />
      </div>

      {triggerError && <ErrorBanner message={triggerError} />}

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1.35fr_0.65fr]">
        <Card>
          <CardHeader title="监控规则" action={<span className="text-xs text-slate-500">{ruleList.length} rules</span>} />
          {ruleList.length === 0 ? (
            <CardBody><EmptyState icon="▤" title="暂无监控规则" /></CardBody>
          ) : ruleList.map((rule, index) => {
            const record = asRecord(rule)
            const id = String(record.id ?? '')
            const enabled = record.enabled !== false
            return (
              <div key={id || index} className="cockpit-row">
                <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className={`cockpit-pill ${enabled ? 'cockpit-pill-success' : 'cockpit-pill-warn'}`}>
                        {enabled ? 'active' : 'paused'}
                      </span>
                      <p className="truncate text-sm font-semibold text-slate-100">{titleOf(rule, `监控规则 ${index + 1}`)}</p>
                    </div>
                    <p className="mt-2 line-clamp-2 text-xs leading-5 text-slate-500">{String(record.query ?? record.domain_id ?? '')}</p>
                  </div>
                  <button
                    disabled={triggering || !id}
                    onClick={() => {
                      void doTrigger(id).then((result) => {
                        if (result !== null) reload()
                      })
                    }}
                    className="glass-button rounded-md px-3 py-1.5 text-xs disabled:opacity-50"
                  >
                    立即触发
                  </button>
                </div>
              </div>
            )
          })}
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader title="平台拓扑" action={<span className={`cockpit-pill ${topology.ready === false ? 'cockpit-pill-warn' : 'cockpit-pill-success'}`}>{topology.ready === false ? 'attention' : 'ready'}</span>} />
            <CardBody className="space-y-3">
              <div className="grid grid-cols-2 gap-2">
                <DetailStat label="版本" value={topology.edition ?? 'community'} />
                <DetailStat label="问题" value={topologyIssues.length} />
                <DetailStat label="数据库" value={database.status} />
                <DetailStat label="对象存储" value={storage.status} />
              </div>
              <div className="flex items-center gap-2 rounded-md border border-slate-800/70 bg-slate-950/35 px-3 py-2 text-xs text-slate-400">
                <Database className="h-4 w-4 text-emerald-300" />
                <span>{String(eventBus.detail ?? 'Redis Streams / DLQ / backpressure')}</span>
              </div>
              <div className="text-xs leading-5 text-slate-500">{String(workflow.detail ?? 'decision workflow wired')}</div>
            </CardBody>
          </Card>
          <Card>
            <CardHeader title="控制面摘要" />
            <CardBody className="grid grid-cols-2 gap-2">
              <DetailStat label="近期变更" value={changeList.length} />
              <DetailStat label="队列" value={queueList.length} />
              <DetailStat label="规则" value={ruleList.length} />
              <DetailStat label="Dashboard keys" value={Object.keys(dashboardRecord).length} />
            </CardBody>
          </Card>
          <Card>
            <CardHeader title="图谱快照" />
            <CardBody className="grid grid-cols-2 gap-2">
              <DetailStat label="节点" value={nodeCount} />
              <DetailStat label="关系" value={edgeCount} />
            </CardBody>
          </Card>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[0.85fr_1.15fr]">
        <Card>
          <CardHeader title="最近源变更" action={<span className="text-xs text-slate-500">{changeList.length} events</span>} />
          {changeList.length === 0 ? (
            <CardBody><EmptyState icon="▦" title="暂无源变更" /></CardBody>
          ) : (
            <CardBody className="space-y-4">
              {changeList.slice(0, 6).map((item, index) => {
                const record = asRecord(item)
                return (
                  <div key={index} className="cockpit-timeline-item">
                    <p className="text-sm font-medium text-slate-100">{titleOf(item, `源变更 ${index + 1}`)}</p>
                    <p className="mt-1 line-clamp-2 text-xs leading-5 text-slate-500">{String(record.summary ?? record.description ?? record.source_type ?? '')}</p>
                  </div>
                )
              })}
            </CardBody>
          )}
        </Card>
        <Card>
          <CardHeader title="原始监控快照" action={<span className="text-xs text-slate-500">debug payload</span>} />
          <CardBody className="space-y-3">
            <JsonBlock value={{ dashboard, queues }} />
            {changeList.slice(0, 3).map((item, index) => <ExpandableRecord key={index} item={item} eyebrow="source change" />)}
          </CardBody>
        </Card>
      </div>
    </div>
  )
}
