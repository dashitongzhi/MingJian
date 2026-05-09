import { useState } from 'react'
import { MessageSquare, Play, X, Clock, Users, ChevronDown, ChevronRight, Save, Loader2, FileText } from 'lucide-react'
import { Card, CardHeader, CardBody } from '../components/ui/Card'
import { StatusBadge } from '../components/ui/StatusBadge'
import { EmptyState } from '../components/ui/EmptyState'
import { LoadingSpinner } from '../components/ui/LoadingSpinner'
import { ErrorBanner } from '../components/ui/ErrorBanner'
import { debateApi, agentsApi } from '../api/endpoints'
import { useApi, useApiAction } from '../hooks/useApi'

interface DebateItem {
  id: string; topic: string; status: string; created_at: string;
  rounds?: number; agents?: string[]; result?: string; summary?: string;
}
interface TimelineEntry { round: number; agent: string; content: string; timestamp?: string }
interface Agent { role_key: string; name: string; is_custom?: boolean }

export default function Debate() {
  const { data: debates, loading, error, reload } = useApi(() => debateApi.list())
  const { data: allAgents } = useApi(() => agentsApi.listAll())
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [formTopic, setFormTopic] = useState('')
  const [formAgents, setFormAgents] = useState<string[]>([])
  const [formRounds, setFormRounds] = useState(3)

  const { data: timeline } = useApi(
    () => selectedId ? debateApi.getTimeline(selectedId) : Promise.resolve(null),
    [selectedId]
  )
  const { data: summary } = useApi(
    () => selectedId ? debateApi.getSummary(selectedId) : Promise.resolve(null),
    [selectedId]
  )

  const { execute: doTrigger, loading: triggering } = useApiAction(
    (data: { topic: string; agents: string[]; rounds: number }) => debateApi.trigger(data)
  )

  const handleTrigger = async () => {
    if (!formTopic.trim()) return
    const r = await doTrigger({ topic: formTopic, agents: formAgents, rounds: formRounds })
    if (r) {
      setShowForm(false)
      setFormTopic('')
      setFormAgents([])
      setFormRounds(3)
      reload()
    }
  }

  const toggleAgent = (key: string) => {
    setFormAgents((prev) => prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key])
  }

  if (loading) return <LoadingSpinner />
  if (error) return <ErrorBanner message={error} onRetry={reload} />

  const list = (debates || []) as DebateItem[]
  const agentList = ((allAgents || []) as Agent[]).filter((a) => !a.is_custom)
  const timelineEntries = (Array.isArray(timeline) ? timeline : (timeline as Record<string, unknown>)?.entries || []) as TimelineEntry[]
  const summaryData = (summary || {}) as Record<string, unknown>

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
          { label: '进行中', value: String(list.filter((d) => d.status === 'running').length), icon: Loader2, color: 'text-emerald-400', bg: 'bg-emerald-500/10' },
          { label: '已完成', value: String(list.filter((d) => d.status === 'completed').length), icon: FileText, color: 'text-slate-400', bg: 'bg-slate-500/10' },
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
          ) : list.map((d) => (
            <div key={d.id}>
              <button onClick={() => setSelectedId(selectedId === d.id ? null : d.id)}
                className={`w-full text-left px-6 py-4 hover:bg-slate-800/30 transition-colors ${selectedId === d.id ? 'bg-blue-500/5' : ''}`}>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <div className="w-10 h-10 rounded-lg bg-cyan-500/10 flex items-center justify-center">
                      <MessageSquare className="w-5 h-5 text-cyan-400" />
                    </div>
                    <div>
                      <p className="text-sm font-medium text-slate-200">{d.topic}</p>
                      <p className="text-xs text-slate-500 mt-0.5">
                        {d.rounds ? `${d.rounds} 轮` : ''} · {d.agents?.length || 0} 参与者 · {new Date(d.created_at).toLocaleDateString()}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <StatusBadge status={d.status} />
                    {selectedId === d.id ? <ChevronDown className="w-4 h-4 text-slate-500" /> : <ChevronRight className="w-4 h-4 text-slate-500" />}
                  </div>
                </div>
              </button>

              {/* Detail Panel */}
              {selectedId === d.id && (
                <div className="px-6 pb-5 border-t border-slate-800/40">
                  {/* Debate Summary */}
                  {!!(d.summary || d.result || summaryData.summary) && (
                    <div className="mt-4 p-4 rounded-lg bg-slate-800/30 border border-slate-700/50">
                      <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">辩论结果摘要</h4>
                      <p className="text-sm text-slate-300">{String(d.summary || d.result || summaryData.summary || '')}</p>
                    </div>
                  )}

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
          ))}
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
              <div>
                <label className="block text-xs text-slate-500 mb-1.5">参与智能体</label>
                <div className="grid grid-cols-2 gap-2 max-h-40 overflow-y-auto">
                  {agentList.map((a) => (
                    <button key={a.role_key} onClick={() => toggleAgent(a.role_key)}
                      className={`flex items-center gap-2 p-2 rounded-lg text-xs transition-colors ${formAgents.includes(a.role_key)
                        ? 'bg-blue-500/10 text-blue-400 border border-blue-500/20'
                        : 'bg-slate-800/30 text-slate-400 border border-slate-700/50 hover:bg-slate-800/50'}`}>
                      <Users className="w-3.5 h-3.5" />
                      {a.name}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <label className="block text-xs text-slate-500 mb-1.5">辩论轮数</label>
                <div className="flex items-center gap-3">
                  <input type="range" min={1} max={10} value={formRounds} onChange={(e) => setFormRounds(Number(e.target.value))}
                    className="flex-1 accent-blue-500" />
                  <span className="text-sm font-mono text-slate-300 w-8 text-right">{formRounds}</span>
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
