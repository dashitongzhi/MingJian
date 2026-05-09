import { useState } from 'react'
import { MessageSquare, Play } from 'lucide-react'
import { Card, CardHeader } from '../components/ui/Card'
import { StatusBadge } from '../components/ui/StatusBadge'
import { EmptyState } from '../components/ui/EmptyState'
import { LoadingSpinner } from '../components/ui/LoadingSpinner'
import { ErrorBanner } from '../components/ui/ErrorBanner'
import { debateApi } from '../api/endpoints'
import { useApi } from '../hooks/useApi'

interface DebateItem { id: string; topic: string; status: string; created_at: string; rounds?: number; agents?: string[] }

export default function Debate() {
  const { data: debates, loading, error, reload } = useApi(() => debateApi.list())
  const [selectedId, setSelectedId] = useState<string | null>(null)

  if (loading) return <LoadingSpinner />
  if (error) return <ErrorBanner message={error} onRetry={reload} />

  const list = (debates || []) as DebateItem[]

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">辩论中心</h1>
          <p className="text-sm text-slate-500 mt-1">多智能体辩论 · 观点交锋 · 决策校验</p>
        </div>
        <button className="flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-500/10 text-blue-400 text-sm font-medium hover:bg-blue-500/20 transition-colors border border-blue-500/20">
          <Play className="w-4 h-4" /> 发起辩论
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {[
          { label: '辩论总数', value: String(list.length), icon: MessageSquare, color: 'text-blue-400', bg: 'bg-blue-500/10' },
          { label: '进行中', value: String(list.filter((d) => d.status === 'running').length), icon: Play, color: 'text-emerald-400', bg: 'bg-emerald-500/10' },
          { label: '已完成', value: String(list.filter((d) => d.status === 'completed').length), icon: MessageSquare, color: 'text-slate-400', bg: 'bg-slate-500/10' },
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
        <CardHeader title="辩论记录" />
        <div className="divide-y divide-slate-800/60">
          {list.length === 0 ? (
            <EmptyState icon="🗣️" title="暂无辩论记录" description="发起第一场辩论吧" />
          ) : list.map((d) => (
            <button key={d.id} onClick={() => setSelectedId(d.id)}
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
                <StatusBadge status={d.status} />
              </div>
            </button>
          ))}
        </div>
      </Card>
    </div>
  )
}
