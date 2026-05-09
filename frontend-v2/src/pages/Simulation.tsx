import { FlaskConical, Plus, Play, GitBranch } from 'lucide-react'
import { Card, CardHeader } from '../components/ui/Card'
import { StatusBadge } from '../components/ui/StatusBadge'
import { EmptyState } from '../components/ui/EmptyState'
import { LoadingSpinner } from '../components/ui/LoadingSpinner'
import { ErrorBanner } from '../components/ui/ErrorBanner'
import { simulationApi } from '../api/endpoints'
import { useApi } from '../hooks/useApi'
import { useState } from 'react'

interface SimRun { id: string; company_id?: string; status: string; domain_id?: string; created_at: string; tick_count?: number }
interface Hypothesis { id: string; statement: string; status: string; evidence_count?: number }

export default function Simulation() {
  const { data: runs, loading, error, reload } = useApi(() => simulationApi.listRuns())
  const [selectedRun, setSelectedRun] = useState<string | null>(null)
  const { data: hypotheses } = useApi(
    () => selectedRun ? simulationApi.listHypotheses(selectedRun) : Promise.resolve([]),
    [selectedRun]
  )

  if (loading) return <LoadingSpinner />
  if (error) return <ErrorBanner message={error} onRetry={reload} />

  const runList = (runs || []) as SimRun[]
  const hypList = (hypotheses || []) as Hypothesis[]

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">场景模拟</h1>
          <p className="text-sm text-slate-500 mt-1">假设推演 · 分支时间线 · KPI 追踪</p>
        </div>
        <button className="flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-500/10 text-blue-400 text-sm font-medium hover:bg-blue-500/20 transition-colors border border-blue-500/20">
          <Plus className="w-4 h-4" /> 新建模拟
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {[
          { label: '模拟总数', value: String(runList.length), icon: FlaskConical, color: 'text-blue-400', bg: 'bg-blue-500/10' },
          { label: '运行中', value: String(runList.filter((r) => r.status === 'RUNNING').length), icon: Play, color: 'text-emerald-400', bg: 'bg-emerald-500/10' },
          { label: '已完成', value: String(runList.filter((r) => r.status === 'COMPLETED').length), icon: FlaskConical, color: 'text-slate-400', bg: 'bg-slate-500/10' },
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
        <CardHeader title="模拟记录" />
        <div className="divide-y divide-slate-800/60">
          {runList.length === 0 ? (
            <EmptyState icon="🧪" title="暂无模拟记录" description="创建第一个场景模拟" />
          ) : runList.map((r) => (
            <button key={r.id} onClick={() => setSelectedRun(r.id)}
              className={`w-full text-left px-6 py-4 hover:bg-slate-800/30 transition-colors ${selectedRun === r.id ? 'bg-blue-500/5' : ''}`}>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-4">
                  <div className="w-10 h-10 rounded-lg bg-emerald-500/10 flex items-center justify-center">
                    <FlaskConical className="w-5 h-5 text-emerald-400" />
                  </div>
                  <div>
                    <p className="text-sm font-medium text-slate-200">{r.company_id || r.id.slice(0, 8)}</p>
                    <p className="text-xs text-slate-500 mt-0.5">
                      {r.domain_id} · {r.tick_count ? `${r.tick_count} ticks` : ''} · {new Date(r.created_at).toLocaleDateString()}
                    </p>
                  </div>
                </div>
                <StatusBadge status={r.status.toLowerCase()} />
              </div>
            </button>
          ))}
        </div>
      </Card>

      {selectedRun && (
        <Card>
          <CardHeader title="假设验证" action={<button className="text-xs text-blue-400 hover:text-blue-300 transition-colors">+ 新建假设</button>} />
          <div className="divide-y divide-slate-800/60">
            {hypList.length === 0 ? (
              <EmptyState icon="🔬" title="暂无假设" description="为此模拟创建假设进行验证" />
            ) : hypList.map((h) => (
              <div key={h.id} className="px-6 py-4 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <GitBranch className="w-4 h-4 text-slate-500" />
                  <p className="text-sm text-slate-300">{h.statement}</p>
                </div>
                <div className="flex items-center gap-3">
                  {h.evidence_count !== undefined && <span className="text-xs text-slate-500">{h.evidence_count} 证据</span>}
                  <StatusBadge status={h.status} />
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  )
}
