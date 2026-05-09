import { useState } from 'react'
import { TrendingUp, Target, BarChart3, Activity, RefreshCw } from 'lucide-react'
import { Card, CardHeader, CardBody } from '../components/ui/Card'
import { StatusBadge } from '../components/ui/StatusBadge'
import { EmptyState } from '../components/ui/EmptyState'
import { LoadingSpinner } from '../components/ui/LoadingSpinner'
import { ErrorBanner } from '../components/ui/ErrorBanner'
import { reportApi } from '../api/endpoints'
import { useApi } from '../hooks/useApi'

interface Prediction { series_id?: string; id?: string; name?: string; current_value?: number; confidence?: number; status: string; last_updated?: string }
interface Decision { id: string; title?: string; outcome?: string; confidence?: number; created_at: string }

type Tab = 'predictions' | 'monitoring' | 'decisions'

export default function Reports() {
  const [tab, setTab] = useState<Tab>('predictions')
  const { data: predictions, loading, error, reload } = useApi(() => reportApi.listPredictions())
  const { data: monitoringRaw } = useApi(() => reportApi.getMonitoringDashboard())
  const monitoring = (monitoringRaw || {}) as Record<string, unknown>
  const { data: decisions } = useApi(() => reportApi.listDecisions())
  const { data: decisionStats } = useApi(() => reportApi.getDecisionStats())

  const tabs: { key: Tab; label: string }[] = [
    { key: 'predictions', label: '预测追踪' },
    { key: 'monitoring', label: '监测看板' },
    { key: 'decisions', label: '决策记录' },
  ]

  if (loading) return <LoadingSpinner />
  if (error) return <ErrorBanner message={error} onRetry={reload} />

  const predList = (predictions || []) as Prediction[]
  const decList = (decisions || []) as Decision[]

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">报告中心</h1>
          <p className="text-sm text-slate-500 mt-1">预测追踪 · 校准监测 · 决策分析</p>
        </div>
        <button onClick={reload} className="flex items-center gap-2 px-4 py-2 rounded-lg bg-slate-800/60 text-slate-400 text-sm hover:text-slate-200 transition-colors border border-slate-700/50">
          <RefreshCw className="w-4 h-4" /> 刷新
        </button>
      </div>

      <div className="flex gap-1 p-1 bg-slate-900/60 rounded-lg border border-slate-800 w-fit">
        {tabs.map((t) => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={`px-4 py-2 rounded-md text-sm transition-all ${tab === t.key ? 'bg-blue-500/10 text-blue-400 font-medium' : 'text-slate-500 hover:text-slate-300'}`}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'predictions' && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {[
              { label: '预测总数', value: String(predList.length), icon: TrendingUp, color: 'text-blue-400', bg: 'bg-blue-500/10' },
              { label: '高置信度', value: String(predList.filter((p) => (p.confidence || 0) > 0.7).length), icon: Target, color: 'text-emerald-400', bg: 'bg-emerald-500/10' },
              { label: '待更新', value: String(predList.filter((p) => p.status === 'pending').length), icon: RefreshCw, color: 'text-amber-400', bg: 'bg-amber-500/10' },
            ].map((s) => (
              <Card key={s.label} className="p-5">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-xs text-slate-500 uppercase tracking-wider">{s.label}</span>
                  <div className={`w-8 h-8 rounded-lg ${s.bg} flex items-center justify-center`}>
                    <s.icon className={`w-4 h-4 ${s.color}`} />
                  </div>
                </div>
                <div className="text-2xl font-bold text-slate-100">{s.value}</div>
              </Card>
            ))}
          </div>
          <Card>
            <CardHeader title="预测序列" />
            <div className="divide-y divide-slate-800/60">
              {predList.length === 0 ? (
                <EmptyState icon="📈" title="暂无预测" description="运行场景模拟后自动生成预测" />
              ) : predList.map((p, i) => (
                <div key={p.series_id || p.id || i} className="px-6 py-4 flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <div className="w-10 h-10 rounded-lg bg-blue-500/10 flex items-center justify-center">
                      <TrendingUp className="w-5 h-5 text-blue-400" />
                    </div>
                    <div>
                      <p className="text-sm font-medium text-slate-200">{p.name || p.series_id || '未命名'}</p>
                      <p className="text-xs text-slate-500">
                        {p.current_value !== undefined ? `当前值: ${p.current_value}` : ''}
                        {p.confidence !== undefined ? ` · 置信度: ${Math.round(p.confidence * 100)}%` : ''}
                      </p>
                    </div>
                  </div>
                  <StatusBadge status={p.status} />
                </div>
              ))}
            </div>
          </Card>
        </>
      )}

      {tab === 'monitoring' && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <Card className="p-6">
            <div className="flex items-center gap-3 mb-4">
              <BarChart3 className="w-5 h-5 text-blue-400" />
              <h3 className="text-sm font-semibold text-slate-300">校准概览</h3>
            </div>
            {monitoring ? (
              <div className="space-y-4">
                {monitoring.calibration ? (
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-slate-400">校准数据</span>
                    <span className="text-sm font-medium text-slate-200">已加载</span>
                  </div>
                ) : null}
                {monitoring.predictions ? (
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-slate-400">预测数</span>
                    <span className="text-sm font-medium text-slate-200">{Array.isArray(monitoring.predictions) ? monitoring.predictions.length : '—'}</span>
                  </div>
                ) : null}
                {monitoring.watch_rules ? (
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-slate-400">监控规则</span>
                    <span className="text-sm font-medium text-slate-200">{Array.isArray(monitoring.watch_rules) ? monitoring.watch_rules.length : '—'}</span>
                  </div>
                ) : null}
              </div>
            ) : (
              <EmptyState icon="📊" title="暂无监测数据" />
            )}
          </Card>
          <Card className="p-6">
            <div className="flex items-center gap-3 mb-4">
              <Activity className="w-5 h-5 text-emerald-400" />
              <h3 className="text-sm font-semibold text-slate-300">最近变更</h3>
            </div>
            {monitoring?.recent_changes && Array.isArray(monitoring.recent_changes) && monitoring.recent_changes.length > 0 ? (
              <div className="space-y-3">
                {monitoring.recent_changes.slice(0, 5).map((c: Record<string, unknown>, i: number) => (
                  <div key={i} className="p-3 rounded-lg bg-slate-800/30 text-sm text-slate-400">
                    {String(c.description || c.name || JSON.stringify(c).slice(0, 80))}
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState icon="📊" title="暂无变更记录" />
            )}
          </Card>
        </div>
      )}

      {tab === 'decisions' && (
        <>
          {decisionStats && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {Object.entries(decisionStats).map(([key, val]) => (
                <Card key={key} className="p-4">
                  <p className="text-xs text-slate-500 uppercase tracking-wider">{key}</p>
                  <p className="text-xl font-bold text-slate-100 mt-1">{typeof val === 'object' ? JSON.stringify(val) : String(val)}</p>
                </Card>
              ))}
            </div>
          )}
          <Card>
            <CardHeader title="决策记录" />
            <div className="divide-y divide-slate-800/60">
              {decList.length === 0 ? (
                <EmptyState icon="📋" title="暂无决策记录" />
              ) : decList.map((d) => (
                <div key={d.id} className="px-6 py-4 flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-slate-200">{d.title || d.id}</p>
                    <p className="text-xs text-slate-500 mt-0.5">
                      {d.confidence !== undefined ? `置信度: ${Math.round(d.confidence * 100)}%` : ''}
                      · {new Date(d.created_at).toLocaleDateString()}
                    </p>
                  </div>
                  {d.outcome && <StatusBadge status={d.outcome} />}
                </div>
              ))}
            </div>
          </Card>
        </>
      )}
    </div>
  )
}
