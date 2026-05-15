import { BarChart3, Clock, RefreshCw, Target, TrendingUp } from 'lucide-react'
import { Card, CardBody, CardHeader } from '../components/ui/Card'
import { EmptyState } from '../components/ui/EmptyState'
import { LoadingSpinner } from '../components/ui/LoadingSpinner'
import { ErrorBanner } from '../components/ui/ErrorBanner'
import { reportApi } from '../api/endpoints'
import { useApi } from '../hooks/useApi'
import { ExpandableRecord, JsonBlock, MetricCard, ProgressBar, asArray, asRecord, titleOf } from '../components/ui/DataSurface'
import { useState } from 'react'

export default function Predictions() {
  const { data: predictions, loading, error, reload } = useApi(() => reportApi.listPredictions())
  const { data: jobs } = useApi(() => reportApi.listRevisionJobs())
  const { data: backtests } = useApi(() => reportApi.listBacktests())
  const [selected, setSelected] = useState<string | null>(null)
  const { data: detail } = useApi(() => selected ? reportApi.getPrediction(selected) : Promise.resolve(null), [selected])
  const { data: versions } = useApi(() => selected ? reportApi.listVersions(selected) : Promise.resolve([]), [selected])
  const { data: impact } = useApi(() => selected ? reportApi.getImpact(selected).catch(() => null) : Promise.resolve(null), [selected])
  const { data: timeline } = useApi(() => selected ? reportApi.getPredictionTimeline(selected).catch(() => null) : Promise.resolve(null), [selected])

  if (loading) return <LoadingSpinner />
  if (error) return <ErrorBanner message={error} onRetry={reload} />

  const list = asArray(predictions)
  const jobList = asArray(jobs)
  const backtestList = asArray(backtests)
  const highConfidence = list.filter((item) => Number(asRecord(item).confidence ?? asRecord(item).current_confidence ?? 0) >= 0.7)

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="text-xs text-blue-300">Prediction</p>
          <h1 className="mt-1 text-3xl font-semibold text-slate-50">预测追踪</h1>
          <p className="mt-2 text-sm text-slate-500">展示预测序列、版本、影响分析、修订任务和回测结果。</p>
        </div>
        <button onClick={reload} className="glass-button inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm text-slate-200"><RefreshCw className="h-4 w-4" />刷新</button>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
        <MetricCard label="预测序列" value={list.length} icon={<TrendingUp className="h-5 w-5" />} tone="blue" />
        <MetricCard label="高置信度" value={highConfidence.length} icon={<Target className="h-5 w-5" />} tone="emerald" />
        <MetricCard label="修订任务" value={jobList.length} icon={<Clock className="h-5 w-5" />} tone="amber" />
        <MetricCard label="回测记录" value={backtestList.length} icon={<BarChart3 className="h-5 w-5" />} tone="violet" />
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_1fr]">
        <Card>
          <CardHeader title="预测序列" />
          {list.length === 0 ? <CardBody><EmptyState icon="📈" title="暂无预测序列" /></CardBody> : list.map((item, index) => {
            const record = asRecord(item)
            const id = String(record.series_id ?? record.id ?? '')
            const confidence = Number(record.confidence ?? record.current_confidence ?? 0)
            return (
              <div key={id || index} className="border-b border-slate-800/50 last:border-b-0">
                <button onClick={() => setSelected(id)} className="w-full px-5 py-4 text-left transition hover:bg-blue-500/6">
                  <div className="flex items-center justify-between gap-4">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-slate-100">{titleOf(item, `预测 ${index + 1}`)}</p>
                      <p className="mt-1 truncate text-xs text-slate-600">{String(record.status ?? record.domain_id ?? id)}</p>
                    </div>
                    <div className="w-28 shrink-0 space-y-1">
                      <ProgressBar value={confidence} tone={confidence >= 0.7 ? 'emerald' : 'blue'} />
                      <p className="text-right text-[11px] text-slate-500">{Math.round(confidence * 100)}%</p>
                    </div>
                  </div>
                </button>
              </div>
            )
          })}
        </Card>
        <Card>
          <CardHeader title={selected ? '预测详情' : '修订任务与回测'} />
          {selected ? (
            <CardBody><JsonBlock value={{ detail, versions, impact, timeline }} /></CardBody>
          ) : (
            <>
              {jobList.slice(0, 4).map((item, index) => <ExpandableRecord key={`job-${index}`} item={item} eyebrow="revision" />)}
              {backtestList.slice(0, 4).map((item, index) => <ExpandableRecord key={`backtest-${index}`} item={item} eyebrow="backtest" />)}
              {jobList.length + backtestList.length === 0 && <CardBody><EmptyState icon="▧" title="暂无修订或回测" /></CardBody>}
            </>
          )}
        </Card>
      </div>
    </div>
  )
}
