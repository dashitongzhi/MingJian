import { useState } from 'react'
import { Users, Plus, Settings, RotateCcw, Cpu, Trash2, Edit3, Wifi, WifiOff, X, Save, Bot } from 'lucide-react'
import { Card, CardHeader, CardBody } from '../components/ui/Card'
import { StatusBadge } from '../components/ui/StatusBadge'
import { EmptyState } from '../components/ui/EmptyState'
import { LoadingSpinner } from '../components/ui/LoadingSpinner'
import { ErrorBanner } from '../components/ui/ErrorBanner'
import { agentsApi } from '../api/endpoints'
import { useApi, useApiAction } from '../hooks/useApi'

interface Agent {
  role_key: string; name: string; name_en?: string; description?: string;
  model_override?: string; effective_model?: string; is_custom?: boolean; status?: string;
  system_prompt?: string;
}

interface AgentForm {
  role_key: string; name: string; description: string; model_override: string; system_prompt: string;
}

const emptyForm: AgentForm = { role_key: '', name: '', description: '', model_override: '', system_prompt: '' }

export default function Agents() {
  const { data: allAgents, loading, error, reload } = useApi(() => agentsApi.listAll())
  const [showModal, setShowModal] = useState(false)
  const [editingKey, setEditingKey] = useState<string | null>(null)
  const [systemDetail, setSystemDetail] = useState<Agent | null>(null)
  const [form, setForm] = useState<AgentForm>(emptyForm)
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null)

  const { execute: doCreate, loading: creating } = useApiAction((data: AgentForm) => agentsApi.createCustom(data))
  const { execute: doUpdate, loading: updating } = useApiAction((data: { roleKey: string; form: AgentForm }) => agentsApi.updateCustom(data.roleKey, data.form))
  const { execute: doDelete, loading: deleting } = useApiAction((roleKey: string) => agentsApi.deleteCustom(roleKey))

  const handleOpenCreate = () => {
    setEditingKey(null)
    setForm(emptyForm)
    setShowModal(true)
  }

  const handleOpenEdit = (a: Agent) => {
    setEditingKey(a.role_key)
    setForm({
      role_key: a.role_key,
      name: a.name,
      description: a.description || '',
      model_override: a.model_override || '',
      system_prompt: a.system_prompt || '',
    })
    setShowModal(true)
  }

  const handleSubmit = async () => {
    if (!form.name.trim() || !form.role_key.trim()) return
    if (editingKey) {
      const r = await doUpdate({ roleKey: editingKey, form })
      if (r) { setShowModal(false); reload() }
    } else {
      const r = await doCreate(form)
      if (r) { setShowModal(false); reload() }
    }
  }

  const handleDelete = async (roleKey: string) => {
    const r = await doDelete(roleKey)
    if (r) { setDeleteConfirm(null); reload() }
  }

  if (loading) return <LoadingSpinner />
  if (error) return <ErrorBanner message={error} onRetry={reload} />

  const agents = (allAgents || []) as Agent[]
  const systemAgents = agents.filter((a) => !a.is_custom)
  const customAgents = agents.filter((a) => a.is_custom)
  const onlineCount = agents.filter((a) => a.status === 'online' || a.status === 'active').length

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">智能体管理</h1>
          <p className="text-sm text-slate-500 mt-1">管理系统智能体与自定义 Agent</p>
        </div>
        <div className="flex gap-3">
          <button onClick={reload}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-slate-800/60 text-slate-400 text-sm hover:text-slate-200 transition-colors border border-slate-700/50">
            <RotateCcw className="w-4 h-4" /> 刷新
          </button>
          <button onClick={handleOpenCreate}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-500/10 text-blue-400 text-sm font-medium hover:bg-blue-500/20 transition-colors border border-blue-500/20">
            <Plus className="w-4 h-4" /> 创建智能体
          </button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {[
          { label: '智能体总数', value: String(agents.length), icon: Bot, color: 'text-blue-400', bg: 'bg-blue-500/10' },
          { label: '在线状态', value: `${onlineCount}/${agents.length}`, icon: Wifi, color: 'text-emerald-400', bg: 'bg-emerald-500/10' },
          { label: '自定义', value: String(customAgents.length), icon: Cpu, color: 'text-violet-400', bg: 'bg-violet-500/10' },
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

      {/* System Agents */}
      <Card>
        <CardHeader title={`系统智能体 (${systemAgents.length})`} />
        <div className="divide-y divide-slate-800/60">
          {systemAgents.length === 0 ? (
            <EmptyState icon="🤖" title="暂无系统智能体" />
          ) : systemAgents.map((a) => (
            <div key={a.role_key} className="flex items-center justify-between px-6 py-4 hover:bg-slate-800/30 transition-colors">
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
                {a.status ? (
                  <div className="flex items-center gap-1.5">
                    {a.status === 'online' || a.status === 'active' ? (
                      <Wifi className="w-3.5 h-3.5 text-emerald-400" />
                    ) : (
                      <WifiOff className="w-3.5 h-3.5 text-slate-500" />
                    )}
                    <StatusBadge status={a.status} />
                  </div>
                ) : (
                  <StatusBadge status="active" />
                )}
                <button
                  onClick={() => setSystemDetail(a)}
                  className="p-1.5 rounded hover:bg-slate-800/40 text-slate-500 hover:text-slate-300 transition-colors"
                  title="查看配置"
                >
                  <Settings className="w-4 h-4" />
                </button>
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* Custom Agents */}
      <Card>
        <CardHeader title={`自定义智能体 (${customAgents.length})`} />
        <div className="divide-y divide-slate-800/60">
          {customAgents.length === 0 ? (
            <EmptyState icon="✨" title="暂无自定义智能体" description='点击右上角「创建智能体」添加' />
          ) : customAgents.map((a) => (
            <div key={a.role_key} className="flex items-center justify-between px-6 py-4 hover:bg-slate-800/30 transition-colors">
              <div className="flex items-center gap-4">
                <div className="w-10 h-10 rounded-lg bg-violet-500/10 flex items-center justify-center">
                  <Cpu className="w-5 h-5 text-violet-400" />
                </div>
                <div>
                  <p className="text-sm font-medium text-slate-200">{a.name}</p>
                  <p className="text-xs text-slate-500">{a.description || a.role_key} · {a.effective_model || '默认模型'}</p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                {a.status && (
                  <div className="flex items-center gap-1.5">
                    {a.status === 'online' || a.status === 'active' ? (
                      <Wifi className="w-3.5 h-3.5 text-emerald-400" />
                    ) : (
                      <WifiOff className="w-3.5 h-3.5 text-slate-500" />
                    )}
                    <StatusBadge status={a.status} />
                  </div>
                )}
                <button onClick={() => handleOpenEdit(a)}
                  className="p-1.5 rounded hover:bg-slate-800/40 text-slate-500 hover:text-slate-300 transition-colors">
                  <Edit3 className="w-4 h-4" />
                </button>
                {deleteConfirm === a.role_key ? (
                  <div className="flex items-center gap-2">
                    <button onClick={() => handleDelete(a.role_key)} disabled={deleting}
                      className="px-2 py-1 rounded text-xs bg-red-500/20 text-red-400 hover:bg-red-500/30 transition-colors">
                      确认删除
                    </button>
                    <button onClick={() => setDeleteConfirm(null)}
                      className="px-2 py-1 rounded text-xs bg-slate-800/60 text-slate-400 hover:text-slate-200 transition-colors">
                      取消
                    </button>
                  </div>
                ) : (
                  <button onClick={() => setDeleteConfirm(a.role_key)}
                    className="p-1.5 rounded hover:bg-red-500/10 text-slate-500 hover:text-red-400 transition-colors">
                    <Trash2 className="w-4 h-4" />
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* Create / Edit Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={() => setShowModal(false)}>
          <div className="bg-slate-900 border border-slate-800 rounded-xl w-full max-w-lg mx-4 shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800/60">
              <h3 className="text-sm font-semibold text-slate-200">{editingKey ? '编辑智能体' : '创建智能体'}</h3>
              <button onClick={() => setShowModal(false)} className="p-1 rounded hover:bg-slate-800 text-slate-500 hover:text-slate-300 transition-colors">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="px-6 py-4 space-y-4">
              <div>
                <label className="block text-xs text-slate-500 mb-1.5">角色标识 *</label>
                <input value={form.role_key} onChange={(e) => setForm({ ...form, role_key: e.target.value })} disabled={!!editingKey}
                  placeholder="例如: strategist"
                  className="w-full bg-slate-800/40 border border-slate-700/50 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-blue-500/50 disabled:opacity-50" />
              </div>
              <div>
                <label className="block text-xs text-slate-500 mb-1.5">名称 *</label>
                <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
                  placeholder="例如: 战略分析师"
                  className="w-full bg-slate-800/40 border border-slate-700/50 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-blue-500/50" />
              </div>
              <div>
                <label className="block text-xs text-slate-500 mb-1.5">描述</label>
                <input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })}
                  placeholder="智能体描述"
                  className="w-full bg-slate-800/40 border border-slate-700/50 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-blue-500/50" />
              </div>
              <div>
                <label className="block text-xs text-slate-500 mb-1.5">模型覆盖</label>
                <input value={form.model_override} onChange={(e) => setForm({ ...form, model_override: e.target.value })}
                  placeholder="留空使用默认模型"
                  className="w-full bg-slate-800/40 border border-slate-700/50 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-blue-500/50" />
              </div>
              <div>
                <label className="block text-xs text-slate-500 mb-1.5">系统提示</label>
                <textarea value={form.system_prompt} onChange={(e) => setForm({ ...form, system_prompt: e.target.value })} rows={4}
                  placeholder="定义智能体的行为和能力..."
                  className="w-full bg-slate-800/40 border border-slate-700/50 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-blue-500/50 resize-none" />
              </div>
            </div>
            <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-slate-800/60">
              <button onClick={() => setShowModal(false)}
                className="px-4 py-2 rounded-lg text-sm text-slate-400 hover:text-slate-200 transition-colors">
                取消
              </button>
              <button onClick={handleSubmit} disabled={creating || updating || !form.name.trim() || !form.role_key.trim()}
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-500 text-white text-sm font-medium hover:bg-blue-600 transition-colors disabled:opacity-50">
                <Save className="w-4 h-4" />
                {creating || updating ? '保存中...' : editingKey ? '更新' : '创建'}
              </button>
            </div>
          </div>
        </div>
      )}

      {systemDetail && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={() => setSystemDetail(null)}>
          <div className="liquid-glass w-full max-w-lg rounded-lg" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800/60">
              <h3 className="text-sm font-semibold text-slate-100">{systemDetail.name} 配置</h3>
              <button onClick={() => setSystemDetail(null)} className="p-1 rounded hover:bg-slate-800 text-slate-500 hover:text-slate-300 transition-colors">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="px-6 py-4 space-y-3">
              {[
                ['角色标识', systemDetail.role_key],
                ['当前模型', systemDetail.effective_model || '默认模型'],
                ['模型覆盖', systemDetail.model_override || '未覆盖'],
                ['状态', systemDetail.status || 'active'],
              ].map(([label, value]) => (
                <div key={label} className="flex items-center justify-between rounded-lg border border-slate-800/60 bg-slate-950/25 px-3 py-2">
                  <span className="text-xs text-slate-500">{label}</span>
                  <span className="text-sm text-slate-200">{value}</span>
                </div>
              ))}
              {systemDetail.description && (
                <div className="rounded-lg border border-slate-800/60 bg-slate-950/25 p-3">
                  <p className="text-xs text-slate-500 mb-2">描述</p>
                  <p className="max-h-48 overflow-auto text-sm leading-6 text-slate-300 whitespace-pre-wrap">{systemDetail.description}</p>
                </div>
              )}
            </div>
            <div className="flex justify-end px-6 py-4 border-t border-slate-800/60">
              <button onClick={() => setSystemDetail(null)} className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-500">
                知道了
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
