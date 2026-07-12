import { Bot, RotateCcw, ShieldCheck, Wifi, WifiOff } from 'lucide-react'
import { Card, CardHeader } from '../components/ui/Card'
import { StatusBadge } from '../components/ui/StatusBadge'
import { EmptyState } from '../components/ui/EmptyState'
import { LoadingSpinner } from '../components/ui/LoadingSpinner'
import { ErrorBanner } from '../components/ui/ErrorBanner'
import { agentsApi } from '../api/endpoints'
import { useApi } from '../hooks/useApi'

interface Agent {
  role_key?: string
  role?: string
  name?: string
  name_en?: string
  description?: string
  effective_model?: string
  has_key?: boolean
  status?: string
  priority?: number
}

export default function Agents() {
  const { data, loading, error, reload } = useApi(() => agentsApi.list())

  if (loading) return <LoadingSpinner />
  if (error) return <ErrorBanner message={error} onRetry={reload} />

  const payload = (data || {}) as { agents?: Agent[]; total?: number; ready?: number }
  const agents = Array.isArray(payload.agents) ? payload.agents : []
  const ready = typeof payload.ready === 'number' ? payload.ready : agents.filter((a) => a.has_key).length

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">智能体</h1>
          <p className="mt-1 text-sm text-slate-500">
            开源版使用内置智能体；多供应商和模型通过环境变量或配置文件设置。
          </p>
        </div>
        <button
          onClick={reload}
          className="flex items-center gap-2 rounded-lg border border-slate-700/50 bg-slate-800/60 px-4 py-2 text-sm text-slate-400 transition-colors hover:text-slate-200"
        >
          <RotateCcw className="h-4 w-4" /> 刷新
        </button>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        {[
          { label: '内置智能体', value: String(agents.length), icon: Bot },
          { label: '已配置 Key', value: `${ready}/${agents.length}`, icon: ShieldCheck },
          { label: '配置方式', value: '文件/env', icon: Wifi },
        ].map((item) => (
          <Card key={item.label} className="p-5">
            <div className="mb-3 flex items-center justify-between">
              <span className="text-xs uppercase tracking-wider text-slate-500">{item.label}</span>
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-500/10">
                <item.icon className="h-4 w-4 text-blue-400" />
              </div>
            </div>
            <div className="text-2xl font-bold text-slate-100">{item.value}</div>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader title={`系统智能体 (${agents.length})`} />
        <div className="divide-y divide-slate-800/60">
          {agents.length === 0 ? (
            <EmptyState icon="🤖" title="暂无系统智能体" />
          ) : (
            agents.map((agent) => {
              const key = agent.role_key || agent.role || agent.name || 'agent'
              const configured = Boolean(agent.has_key)
              return (
                <div
                  key={key}
                  className="flex items-center justify-between gap-4 px-6 py-4 transition-colors hover:bg-slate-800/30"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-slate-200">{agent.name || key}</p>
                    <p className="mt-1 truncate text-xs text-slate-500">
                      {key} · {agent.effective_model || '默认模型'} · priority {agent.priority ?? '-'}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    {configured ? (
                      <Wifi className="h-3.5 w-3.5 text-emerald-400" />
                    ) : (
                      <WifiOff className="h-3.5 w-3.5 text-slate-500" />
                    )}
                    <StatusBadge status={configured ? 'configured' : 'env'} />
                  </div>
                </div>
              )
            })
          )}
        </div>
      </Card>
    </div>
  )
}
