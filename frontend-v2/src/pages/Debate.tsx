import { useState } from 'react'
import { MessageSquare, Play, X, Clock, Users, ChevronDown, ChevronRight, Save, Loader2, FileText } from 'lucide-react'
import { Card, CardHeader, CardBody } from '../components/ui/Card'
import { StatusBadge } from '../components/ui/StatusBadge'
import { EmptyState } from '../components/ui/EmptyState'
import { LoadingSpinner } from '../components/ui/LoadingSpinner'
import { ErrorBanner } from '../components/ui/ErrorBanner'
import { debateApi, agentsApi, simulationApi } from '../api/endpoints'
import { useApi, useApiAction } from '../hooks/useApi'

interface DebateItem {
  id?: string; debate_id?: string; topic: string; status?: string; created_at: string;
  rounds?: number; agents?: string[]; result?: string; summary?: string; verdict?: string | null;
}
interface TimelineEntry { round: number; agent: string; content: string; timestamp?: string; event_type?: string }
interface Agent { role_key: string; name: string; is_custom?: boolean }
type TriggerPayload = {
  topic: string;
  target_type: 'run' | 'claim';
  target_id: string;
  run_id?: string;
  claim_id?: string;
  trigger_type: 'manual';
  debate_mode: 'full' | 'fast';
}

const REQUIRED_ROLES = ['advocate', 'challenger', 'arbitrator', 'intel_analyst', 'geo_expert', 'econ_analyst', 'military_strategist', 'tech_foresight', 'social_impact']

function debateId(item: DebateItem): string {
  return item.debate_id || item.id || ''
}

function normalizeTimeline(value: unknown): TimelineEntry[] {
  const source = Array.isArray(value)
    ? value
    : Array.isArray((value as Record<string, unknown> | null)?.events)
      ? ((value as Record<string, unknown>).events as unknown[])
      : Array.isArray((value as Record<string, unknown> | null)?.timeline)
        ? ((value as Record<string, unknown>).timeline as unknown[])
        : []
  return source.map((entry, index) => {
    const record = entry && typeof entry === 'object' ? entry as Record<string, unknown> : {}
    const args = Array.isArray(record.arguments) ? record.arguments : []
    const content = typeof record.content === 'string' && record.content
      ? record.content
      : typeof record.message === 'string' && record.message
        ? record.message
        : args.map((arg) => {
          const item = arg && typeof arg === 'object' ? arg as Record<string, unknown> : {}
          return typeof item.claim === 'string' ? item.claim : ''
        }).filter(Boolean).join('；')
    return {
      round: Number(record.round_number || record.injected_at_round || index + 1),
      agent: typeof record.role === 'string' ? record.role : record.event_type === 'interrupt' ? '用户插话' : '智能体',
      content: content || '—',
      timestamp: typeof record.timestamp === 'string' ? record.timestamp : undefined,
      event_type: typeof record.event_type === 'string' ? record.event_type : undefined,
    }
  })
}

export default function Debate() {
  const { data: debates, loading, error, reload } = useApi(() => debateApi.list())
  const { data: allAgents } = useApi(() => agentsApi.listAll())
  const { data: runs } = useApi(() => simulationApi.listRuns())
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [formTopic, setFormTopic] = useState('')
  const [formTargetType, setFormTargetType] = useState<'run' | 'claim'>('run')
  const [formTargetId, setFormTargetId] = useState('')
  const [formMode, setFormMode] = useState<'full' | 'fast'>('full')

  const { data: timeline } = useApi(
    () => selectedId ? debateApi.getTimeline(selectedId) : Promise.resolve(null),
    [selectedId]
  )
  const { data: summary } = useApi(
    () => selectedId ? debateApi.getSummary(selectedId) : Promise.resolve(null),
    [selectedId]
  )

  const { execute: doTrigger, loading: triggering } = useApiAction(
    (data: TriggerPayload) => debateApi.trigger(data)
  )

  const handleTrigger = async () => {
    if (!formTopic.trim()) return
    const latestRun = (runs || [])[0] as Record<string, unknown> | undefined
    const targetId = formTargetId.trim() || (typeof latestRun?.id === 'string' ? latestRun.id : '')
    if (!targetId) return
    const payload: TriggerPayload = {
      topic: formTopic,
      target_type: formTargetType,
      target_id: targetId,
      trigger_type: 'manual',
      debate_mode: formMode,
      ...(formTargetType === 'run' ? { run_id: targetId } : { claim_id: targetId }),
    }
    const r = await doTrigger(payload)
    if (r) {
      setShowForm(false)
      setFormTopic('')
      setFormTargetId('')
      setFormMode('full')
      reload()
    }
  }

  if (loading) return <LoadingSpinner />
  if (error) return <ErrorBanner message={error} onRetry={reload} />

  const list = (debates || []) as DebateItem[]
  const agentList = ((allAgents || []) as Agent[]).filter((a) => !a.is_custom)
  const timelineEntries = normalizeTimeline(timeline)
  const summaryData = (summary || {}) as Record<string, unknown>
  const participatedRoles = new Set(timelineEntries.filter((entry) => entry.event_type !== 'interrupt').map((entry) => entry.agent))
  const coveredBuiltIns = REQUIRED_ROLES.filter((role) => participatedRoles.has(role)).length
  const coveragePct = REQUIRED_ROLES.length ? Math.round((coveredBuiltIns / REQUIRED_ROLES.length) * 100) : 0

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">辩论中心</h1>
          <p className="text-sm text-slate-500 mt-1">多智能体辩论 · 观点交锋 · 决策校验</p>
        </div>
        <button onClick={() => setShowForm(true)}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-500/10 text-blue-400 text-sm font-medium hover:bg-blue-500/20 transition-colors border border-blue-500/20">
          <Play className="w-4 h-4" /> 发起辩论
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {[
          { label: '辩论总数', value: String(list.length), icon: MessageSquare, color: 'text-blue-400', bg: 'bg-blue-500/10' },
          { label: '进行中', value: String(list.filter((d) => (d.status || '').toUpperCase() === 'RUNNING').length), icon: Loader2, color: 'text-emerald-400', bg: 'bg-emerald-500/10' },
          { label: '已完成', value: String(list.filter((d) => (d.status || 'COMPLETED').toUpperCase() === 'COMPLETED').length), icon: FileText, color: 'text-slate-400', bg: 'bg-slate-500/10' },
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

      {/* Debate List */}
      <Card>
        <CardHeader title="辩论记录" />
        <div className="divide-y divide-slate-800/60">
          {list.length === 0 ? (
            <EmptyState icon="🗣️" title="暂无辩论记录" description="发起第一场辩论吧" />
          ) : list.map((d) => {
            const id = debateId(d)
            return (
            <div key={id}>
              <button onClick={() => setSelectedId(selectedId === id ? null : id)}
                className={`w-full text-left px-6 py-4 hover:bg-slate-800/30 transition-colors ${selectedId === id ? 'bg-blue-500/5' : ''}`}>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <div className="w-10 h-10 rounded-lg bg-cyan-500/10 flex items-center justify-center">
                      <MessageSquare className="w-5 h-5 text-cyan-400" />
                    </div>
                    <div>
                      <p className="text-sm font-medium text-slate-200">{d.topic}</p>
                      <p className="text-xs text-slate-500 mt-0.5">
                        {d.rounds ? `${d.rounds} 轮` : ''} · {d.agents?.length || '9+'} 参与者 · {new Date(d.created_at).toLocaleDateString()}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <StatusBadge status={d.status || 'COMPLETED'} />
                    {selectedId === id ? <ChevronDown className="w-4 h-4 text-slate-500" /> : <ChevronRight className="w-4 h-4 text-slate-500" />}
                  </div>
                </div>
              </button>

              {/* Detail Panel */}
              {selectedId === id && (
                <div className="px-6 pb-5 border-t border-slate-800/40">
                  {/* Debate Summary */}
                  {!!(d.summary || d.result || summaryData.summary) && (
                    <div className="mt-4 p-4 rounded-lg bg-slate-800/30 border border-slate-700/50">
                      <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">辩论结果摘要</h4>
                      <p className="text-sm text-slate-300">{String(d.summary || d.result || summaryData.summary || '')}</p>
                    </div>
                  )}

                  <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-3">
                    <div className="rounded-lg bg-slate-800/30 border border-slate-700/50 p-3">
                      <div className="text-xs text-slate-500">内置智能体覆盖率</div>
                      <div className="mt-1 text-xl font-semibold text-slate-100">{coveragePct}%</div>
                    </div>
                    <div className="rounded-lg bg-slate-800/30 border border-slate-700/50 p-3">
                      <div className="text-xs text-slate-500">已发言角色</div>
                      <div className="mt-1 text-xl font-semibold text-slate-100">{participatedRoles.size}</div>
                    </div>
                    <div className="rounded-lg bg-slate-800/30 border border-slate-700/50 p-3">
                      <div className="text-xs text-slate-500">状态</div>
                      <div className="mt-1 text-sm font-medium text-emerald-300">
                        {coveredBuiltIns >= REQUIRED_ROLES.length ? '全部内置智能体已参与' : '等待更多发言'}
                      </div>
                    </div>
                  </div>

                  {/* Timeline */}
                  <div className="mt-4">
                    <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">辩论时间线</h4>
                    {Array.isArray(timelineEntries) && timelineEntries.length > 0 ? (
                      <div className="space-y-3">
                        {timelineEntries.map((entry, i) => (
                          <div key={i} className="flex gap-3">
                            <div className="flex flex-col items-center">
                              <div className="w-6 h-6 rounded-full bg-blue-500/10 flex items-center justify-center text-xs text-blue-400 font-medium shrink-0">
                                {entry.round || i + 1}
                              </div>
                              {i < timelineEntries.length - 1 && <div className="w-px h-full bg-slate-800 mt-1" />}
                            </div>
                            <div className="flex-1 pb-3">
                              <div className="flex items-center gap-2 mb-1">
                                <span className="text-xs font-medium text-blue-400">{entry.agent || '智能体'}</span>
                                <span className="text-xs text-slate-600">第 {entry.round || i + 1} 轮</span>
                                {entry.timestamp && <span className="text-xs text-slate-600">{new Date(entry.timestamp).toLocaleTimeString()}</span>}
                              </div>
                              <p className="text-sm text-slate-300 leading-relaxed">{entry.content || '—'}</p>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <EmptyState icon="⏱️" title="暂无时间线数据" description="辩论进行中或数据尚未加载" />
                    )}
                  </div>
                </div>
              )}
            </div>
          )})}
        </div>
      </Card>

      {/* Trigger Form Modal */}
      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={() => setShowForm(false)}>
          <div className="bg-slate-900 border border-slate-800 rounded-xl w-full max-w-lg mx-4 shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800/60">
              <h3 className="text-sm font-semibold text-slate-200">发起辩论</h3>
              <button onClick={() => setShowForm(false)} className="p-1 rounded hover:bg-slate-800 text-slate-500 hover:text-slate-300 transition-colors">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="px-6 py-4 space-y-4">
              <div>
                <label className="block text-xs text-slate-500 mb-1.5">辩论主题 *</label>
                <input value={formTopic} onChange={(e) => setFormTopic(e.target.value)}
                  placeholder="输入辩论主题..."
                  className="w-full bg-slate-800/40 border border-slate-700/50 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-blue-500/50" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-slate-500 mb-1.5">目标类型</label>
                  <select value={formTargetType} onChange={(e) => setFormTargetType(e.target.value as 'run' | 'claim')}
                    className="w-full bg-slate-800/40 border border-slate-700/50 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-blue-500/50">
                    <option value="run">Run</option>
                    <option value="claim">Claim</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-slate-500 mb-1.5">模式</label>
                  <select value={formMode} onChange={(e) => setFormMode(e.target.value as 'full' | 'fast')}
                    className="w-full bg-slate-800/40 border border-slate-700/50 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-blue-500/50">
                    <option value="full">Full</option>
                    <option value="fast">Fast</option>
                  </select>
                </div>
              </div>
              <div>
                <label className="block text-xs text-slate-500 mb-1.5">Run ID / Claim ID *</label>
                <input value={formTargetId} onChange={(e) => setFormTargetId(e.target.value)}
                  placeholder={(runs || [])[0] ? `默认使用最新 Run：${String(((runs || [])[0] as Record<string, unknown>).id || '').slice(0, 8)}` : '输入目标 ID'}
                  className="w-full bg-slate-800/40 border border-slate-700/50 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-blue-500/50" />
              </div>
              <div className="rounded-lg bg-slate-800/30 border border-slate-700/50 p-3">
                <div className="text-xs text-slate-500 mb-2">Community 固定参与智能体</div>
                <div className="grid grid-cols-2 gap-2 max-h-32 overflow-y-auto">
                  {agentList.slice(0, 9).map((a) => (
                    <div key={a.role_key} className="flex items-center gap-2 p-2 rounded-lg text-xs bg-slate-900/40 text-slate-300 border border-slate-800">
                      <Users className="w-3.5 h-3.5" />
                      {a.name}
                    </div>
                  ))}
                </div>
              </div>
            </div>
            <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-slate-800/60">
              <button onClick={() => setShowForm(false)}
                className="px-4 py-2 rounded-lg text-sm text-slate-400 hover:text-slate-200 transition-colors">
                取消
              </button>
              <button onClick={handleTrigger} disabled={triggering || !formTopic.trim()}
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-500 text-white text-sm font-medium hover:bg-blue-600 transition-colors disabled:opacity-50">
                <Play className="w-4 h-4" />
                {triggering ? '发起中...' : '开始辩论'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
