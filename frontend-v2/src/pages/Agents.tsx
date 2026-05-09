import { Users, Plus, Settings, RotateCcw, Cpu } from 'lucide-react'
import { Card, CardHeader } from '../components/ui/Card'
import { StatusBadge } from '../components/ui/StatusBadge'
import { EmptyState } from '../components/ui/EmptyState'
import { LoadingSpinner } from '../components/ui/LoadingSpinner'
import { ErrorBanner } from '../components/ui/ErrorBanner'
import { agentsApi } from '../api/endpoints'
import { useApi } from '../hooks/useApi'

interface Agent { role_key: string; name: string; name_en?: string; description?: string; model_override?: string; effective_model?: string; is_custom?: boolean; status?: string }

export default function Agents() {
  const { data: allAgents, loading, error, reload } = useApi(() => agentsApi.listAll())

  if (loading) return <LoadingSpinner />
  if (error) return <ErrorBanner message={error} onRetry={reload} />

  const agents = (allAgents || []) as Agent[]
  const systemAgents = agents.filter((a) => !a.is_custom)
  const customAgents = agents.filter((a) => a.is_custom)

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">智能体管理</h1>
          <p className="text-sm text-slate-500 mt-1">管理系统智能体与自定义 Agent</p>
        </div>
        <div className="flex gap-3">
          <button onClick={reload} className="flex items-center gap-2 px-4 py-2 rounded-lg bg-slate-800/60 text-slate-400 text-sm hover:text-slate-200 transition-colors border border-slate-700/50">
            <RotateCcw className="w-4 h-4" /> 刷新
          </button>
          <button className="flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-500/10 text-blue-400 text-sm font-medium hover:bg-blue-500/20 transition-colors border border-blue-500/20">
            <Plus className="w-4 h-4" /> 创建智能体
          </button>
        </div>
      </div>

      <Card>
        <CardHeader title={`系统智能体 (${systemAgents.length})`} />
        <div className="divide-y divide-slate-800/60">
          {systemAgents.length === 0 ? (
            <EmptyState icon="🤖" title="暂无系统智能体" />
          ) : systemAgents.map((a) => (
            <div key={a.role_key} className="flex items-center justify-between px-6 py-4">
              <div className="flex items-center gap-4">
                <div className="w-10 h-10 rounded-lg bg-blue-500/10 flex items-center justify-center">
                  <Users className="w-5 h-5 text-blue-400" />
                </div>
                <div>
                  <p className="text-sm font-medium text-slate-200">{a.name}</p>
                  <p className="text-xs text-slate-500">{a.role_key} · {a.effective_model || '默认模型'}</p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <button className="p-1.5 rounded hover:bg-slate-800/40 text-slate-500 hover:text-slate-300 transition-colors">
                  <Settings className="w-4 h-4" />
                </button>
              </div>
            </div>
          ))}
        </div>
      </Card>

      <Card>
        <CardHeader title={`自定义智能体 (${customAgents.length})`} />
        <div className="divide-y divide-slate-800/60">
          {customAgents.length === 0 ? (
            <EmptyState icon="✨" title="暂无自定义智能体" description='点击右上角「创建智能体」添加' />
          ) : customAgents.map((a) => (
            <div key={a.role_key} className="flex items-center justify-between px-6 py-4">
              <div className="flex items-center gap-4">
                <div className="w-10 h-10 rounded-lg bg-violet-500/10 flex items-center justify-center">
                  <Cpu className="w-5 h-5 text-violet-400" />
                </div>
                <div>
                  <p className="text-sm font-medium text-slate-200">{a.name}</p>
                  <p className="text-xs text-slate-500">{a.description || a.role_key}</p>
                </div>
              </div>
              {a.status && <StatusBadge status={a.status} />}
            </div>
          ))}
        </div>
      </Card>
    </div>
  )
}
