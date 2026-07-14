import { useState } from 'react'
import { FlaskConical, Plus, Play, GitBranch, X, Save, ChevronDown, ChevronRight, Clock, Target, BarChart3 } from 'lucide-react'
import { Card, CardHeader } from '../components/ui/Card'
import { StatusBadge } from '../components/ui/StatusBadge'
import { EmptyState } from '../components/ui/EmptyState'
import { LoadingSpinner } from '../components/ui/LoadingSpinner'
import { ErrorBanner } from '../components/ui/ErrorBanner'
import { simulationApi } from '../api/endpoints'
import { useApi, useApiAction } from '../hooks/useApi'

interface SimRun {
  id: string; company_id?: string; status: string; domain_id?: string;
  created_at: string; tick_count?: number; description?: string;
}
interface Hypothesis {
  id: string; statement: string; status: string; evidence_count?: number;
  created_at?: string;
}
interface WorkbenchData {
  kpis?: { name: string; value: number; target?: number; unit?: string }[];
  events?: { tick: number; description: string }[];
  [key: string]: unknown;
}

const DOMAINS = [
  { value: 'tech', label: '科技行业' },
  { value: 'finance', label: '金融行业' },
  { value: 'healthcare', label: '医疗健康' },
  { value: 'energy', label: '能源行业' },
  { value: 'retail', label: '零售行业' },
  { value: 'general', label: '综合领域' },
]

export default function Simulation() {
  const { data: runs, loading, error, reload } = useApi(() => simulationApi.listRuns())
  const [selectedRun, setSelectedRun] = useState<string | null>(null)
  const [showCreateForm, setShowCreateForm] = useState(false)
  const [formCompanyId, setFormCompanyId] = useState('')
  const [formDomain, setFormDomain] = useState('general')

  const { data: hypotheses } = useApi(
    () => selectedRun ? simulationApi.listHypotheses(selectedRun) : Promise.resolve([]),
    selectedRun
  )
  const { data: workbench } = useApi(
    () => selectedRun ? simulationApi.getWorkbench(selectedRun) : Promise.resolve(null),
    selectedRun
  )

  const { execute: doCreate, loading: creating } = useApiAction(
    (data: { company_id: string; domain_id: string }) => simulationApi.createRun(data)
  )

  const handleCreate = async () => {
    const r = await doCreate({ company_id: formCompanyId, domain_id: formDomain })
    if (r) {
      setShowCreateForm(false)
      setFormCompanyId('')
      setFormDomain('general')
      reload()
    }
  }

  if (loading) return <LoadingSpinner />
  if (error) return <ErrorBanner message={error} onRetry={reload} />

  const runList = (runs || []) as SimRun[]
  const hypList = (hypotheses || []) as Hypothesis[]
  const wb = (workbench || {}) as WorkbenchData

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">场景模拟</h1>
          <p className="text-sm text-slate-500 mt-1">假设推演 · 分支时间线 · KPI 追踪</p>
        </div>
        <button onClick={() => setShowCreateForm(true)}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-500/10 text-blue-400 text-sm font-medium hover:bg-blue-500/20 transition-colors border border-blue-500/20">
          <Plus className="w-4 h-4" /> 新建模拟
        </button>
      </div>

      {/* Stats */}
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

      {/* Simulation Runs */}
      <Card>
        <CardHeader title="模拟记录" />
        <div className="divide-y divide-slate-800/60">
          {runList.length === 0 ? (
            <EmptyState icon="🧪" title="暂无模拟记录" description="创建第一个场景模拟" />
          ) : runList.map((r) => (
            <div key={r.id}>
              <button onClick={() => setSelectedRun(selectedRun === r.id ? null : r.id)}
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
                  <div className="flex items-center gap-3">
                    <StatusBadge status={r.status.toLowerCase()} />
                    {selectedRun === r.id ? <ChevronDown className="w-4 h-4 text-slate-500" /> : <ChevronRight className="w-4 h-4 text-slate-500" />}
                  </div>
                </div>
              </button>

              {/* Detail Panel */}
              {selectedRun === r.id && (
                <div className="px-6 pb-5 border-t border-slate-800/40">
                  {/* KPI Tracking */}
                  {wb.kpis && Array.isArray(wb.kpis) && wb.kpis.length > 0 && (
                    <div className="mt-4">
                      <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3 flex items-center gap-2">
                        <Target className="w-3.5 h-3.5" /> KPI 追踪
                      </h4>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        {wb.kpis.map((kpi, i) => {
                          const pct = kpi.target ? Math.min(100, Math.round((kpi.value / kpi.target) * 100)) : 0
                          return (
                            <div key={i} className="p-3 rounded-lg bg-slate-800/30 border border-slate-700/50">
                              <div className="flex items-center justify-between mb-2">
                                <span className="text-xs text-slate-400">{kpi.name}</span>
                                <span className="text-xs font-mono text-slate-300">
                                  {kpi.value}{kpi.unit || ''}{kpi.target ? ` / ${kpi.target}` : ''}
                                </span>
                              </div>
                              {kpi.target && (
                                <div className="w-full h-1.5 bg-slate-700/50 rounded-full overflow-hidden">
                                  <div className={`h-full rounded-full transition-all ${pct >= 80 ? 'bg-emerald-500' : pct >= 50 ? 'bg-amber-500' : 'bg-red-500'}`}
                                    style={{ width: `${pct}%` }} />
                                </div>
                              )}
                            </div>
                          )
                        })}
                      </div>
                    </div>
                  )}

                  {/* Timeline Events */}
                  {wb.events && Array.isArray(wb.events) && wb.events.length > 0 && (
                    <div className="mt-4">
                      <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3 flex items-center gap-2">
                        <Clock className="w-3.5 h-3.5" /> 推演时间线
                      </h4>
                      <div className="space-y-2">
                        {wb.events.map((ev, i) => (
                          <div key={i} className="flex gap-3">
                            <div className="flex flex-col items-center">
                              <div className="w-5 h-5 rounded-full bg-emerald-500/10 flex items-center justify-center text-[10px] text-emerald-400 font-mono shrink-0">
                                {ev.tick}
                              </div>
                              {i < wb.events!.length - 1 && <div className="w-px h-full bg-slate-800 mt-0.5" />}
                            </div>
                            <p className="text-sm text-slate-300 pb-2 leading-relaxed">{ev.description}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Hypotheses */}
                  <div className="mt-4">
                    <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3 flex items-center gap-2">
                      <BarChart3 className="w-3.5 h-3.5" /> 假设验证
                    </h4>
                    <div className="divide-y divide-slate-800/60 rounded-lg border border-slate-800/60 overflow-hidden">
                      {hypList.length === 0 ? (
                        <div className="p-4"><EmptyState icon="🔬" title="暂无假设" description="为此模拟创建假设进行验证" /></div>
                      ) : hypList.map((h) => (
                        <div key={h.id} className="px-4 py-3 flex items-center justify-between hover:bg-slate-800/20 transition-colors">
                          <div className="flex items-center gap-3">
                            <GitBranch className="w-4 h-4 text-slate-500 shrink-0" />
                            <div>
                              <p className="text-sm text-slate-300">{h.statement}</p>
                              {h.created_at && <p className="text-xs text-slate-600 mt-0.5">{new Date(h.created_at).toLocaleDateString()}</p>}
                            </div>
                          </div>
                          <div className="flex items-center gap-3 shrink-0">
                            {h.evidence_count !== undefined && <span className="text-xs text-slate-500">{h.evidence_count} 证据</span>}
                            <StatusBadge status={h.status} />
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      </Card>

      {/* Create Form Modal */}
      {showCreateForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={() => setShowCreateForm(false)}>
          <div className="bg-slate-900 border border-slate-800 rounded-xl w-full max-w-lg mx-4 shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800/60">
              <h3 className="text-sm font-semibold text-slate-200">创建模拟</h3>
              <button onClick={() => setShowCreateForm(false)} className="p-1 rounded hover:bg-slate-800 text-slate-500 hover:text-slate-300 transition-colors">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="px-6 py-4 space-y-4">
              <div>
                <label className="block text-xs text-slate-500 mb-1.5">公司标识</label>
                <input value={formCompanyId} onChange={(e) => setFormCompanyId(e.target.value)}
                  placeholder="输入公司ID 或名称"
                  className="w-full bg-slate-800/40 border border-slate-700/50 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-blue-500/50" />
              </div>
              <div>
                <label className="block text-xs text-slate-500 mb-1.5">领域选择</label>
                <div className="grid grid-cols-2 gap-2">
                  {DOMAINS.map((d) => (
                    <button key={d.value} onClick={() => setFormDomain(d.value)}
                      className={`p-2 rounded-lg text-xs text-center transition-colors ${formDomain === d.value
                        ? 'bg-blue-500/10 text-blue-400 border border-blue-500/20'
                        : 'bg-slate-800/30 text-slate-400 border border-slate-700/50 hover:bg-slate-800/50'}`}>
                      {d.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>
            <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-slate-800/60">
              <button onClick={() => setShowCreateForm(false)}
                className="px-4 py-2 rounded-lg text-sm text-slate-400 hover:text-slate-200 transition-colors">
                取消
              </button>
              <button onClick={handleCreate} disabled={creating}
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-500 text-white text-sm font-medium hover:bg-blue-600 transition-colors disabled:opacity-50">
                <Save className="w-4 h-4" />
                {creating ? '创建中...' : '开始模拟'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
