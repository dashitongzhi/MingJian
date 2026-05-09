import { Save, RotateCcw, Zap, Server, CheckCircle, Loader2, AlertCircle, Wifi, WifiOff } from 'lucide-react'
import { Card, CardHeader, CardBody } from '../components/ui/Card'
import { LoadingSpinner } from '../components/ui/LoadingSpinner'
import { ErrorBanner } from '../components/ui/ErrorBanner'
import { settingsApi } from '../api/endpoints'
import { useApi, useApiAction } from '../hooks/useApi'
import { useState } from 'react'

const MODEL_LABELS: Record<string, string> = {
  tier_override: '模型层级',
  max_output_tokens_override: '最大输出 Token',
  total_rounds_override: '总轮数上限',
  max_arguments_override: '最大参数数',
}

export default function Settings() {
  const { data: modelSettings, loading, error, reload } = useApi(() => settingsApi.getModelSettings())
  const { data: capabilities } = useApi(() => settingsApi.getModelCapabilities())
  const { data: openaiStatus } = useApi(() => settingsApi.getOpenaiStatus())
  const [saved, setSaved] = useState(false)
  const [editValues, setEditValues] = useState<Record<string, string>>({})
  const [editing, setEditing] = useState<Record<string, boolean>>({})

  const { execute: doSave, loading: saving } = useApiAction((data: Record<string, unknown>) => settingsApi.updateModelSettings(data))
  const { execute: doTest, loading: testing } = useApiAction(() => settingsApi.testOpenai())

  const handleSave = async () => {
    const payload: Record<string, unknown> = {}
    Object.entries(editValues).forEach(([k, v]) => {
      if (v === '') { payload[k] = null }
      else if (!isNaN(Number(v))) { payload[k] = Number(v) }
      else { payload[k] = v }
    })
    const r = await doSave(payload)
    if (r) {
      setSaved(true)
      setEditing({})
      setEditValues({})
      setTimeout(() => setSaved(false), 2000)
      reload()
    }
  }

  const handleTestOpenai = async () => {
    await doTest()
  }

  const startEdit = (key: string, currentVal: unknown) => {
    setEditing((prev) => ({ ...prev, [key]: true }))
    setEditValues((prev) => ({ ...prev, [key]: currentVal == null ? '' : String(currentVal) }))
  }

  if (loading) return <LoadingSpinner />
  if (error) return <ErrorBanner message={error} onRetry={reload} />

  const ms = (modelSettings || {}) as Record<string, unknown>
  const caps = (capabilities || {}) as Record<string, unknown>
  const oai = (openaiStatus || {}) as Record<string, unknown>
  const knownModels: string[] = Array.isArray(caps.known_models) ? caps.known_models : []

  const configured = Boolean(oai.configured)
  const responsesApi = Boolean(oai.responses_api)
  const primaryOk = Boolean(oai.primary_configured)
  const authMode = typeof oai.auth_mode === 'string' ? oai.auth_mode : '未知'

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">设置</h1>
          <p className="text-sm text-slate-500 mt-1">模型配置 · 系统状态</p>
        </div>
        <div className="flex gap-3">
          <button onClick={reload} className="flex items-center gap-2 px-4 py-2 rounded-lg bg-slate-800/60 text-slate-400 text-sm hover:text-slate-200 transition-colors border border-slate-700/50">
            <RotateCcw className="w-4 h-4" /> 刷新
          </button>
          <button onClick={handleSave} disabled={saving}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-500 text-white text-sm font-medium hover:bg-blue-600 transition-colors disabled:opacity-50">
            {saved ? <CheckCircle className="w-4 h-4" /> : saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            {saved ? '已保存' : saving ? '保存中...' : '保存'}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Model Config */}
        <Card>
          <CardHeader title="模型配置" />
          <CardBody className="space-y-3">
            {['tier_override', 'max_output_tokens_override', 'total_rounds_override', 'max_arguments_override'].map((key) => {
              const val = ms[key]
              const isEditing = editing[key]
              return (
                <div key={key} className="flex items-center justify-between p-3 rounded-lg bg-slate-800/30 border border-slate-700/50">
                  <span className="text-sm text-slate-400">{MODEL_LABELS[key] || key.replace(/_/g, ' ')}</span>
                  {isEditing ? (
                    <input value={editValues[key] ?? ''} onChange={(e) => setEditValues((prev) => ({ ...prev, [key]: e.target.value }))}
                      placeholder="留空恢复默认"
                      className="w-32 bg-slate-900/60 border border-slate-700/50 rounded px-2 py-1 text-sm text-slate-200 text-right focus:outline-none focus:border-blue-500/50" />
                  ) : (
                    <button onClick={() => startEdit(key, val)}
                      className="text-sm font-medium text-slate-200 hover:text-blue-400 transition-colors cursor-pointer">
                      {val == null ? '默认' : String(val)}
                    </button>
                  )}
                </div>
              )
            })}
            {Object.keys(editing).some((k) => editing[k]) && (
              <p className="text-xs text-slate-600 mt-2">修改后点击右上角「保存」按钮应用更改</p>
            )}
          </CardBody>
        </Card>

        {/* System Status */}
        <Card>
          <CardHeader title="系统状态" />
          <CardBody className="space-y-3">
            {/* OpenAI Connection */}
            <div className="flex items-center justify-between p-3 rounded-lg bg-slate-800/30 border border-slate-700/50">
              <div className="flex items-center gap-3">
                <Server className="w-4 h-4 text-slate-500" />
                <span className="text-sm text-slate-400">OpenAI 连接</span>
              </div>
              <div className="flex items-center gap-2">
                <span className={`text-xs px-2 py-0.5 rounded-full ${configured ? 'bg-emerald-500/10 text-emerald-400' : 'bg-red-500/10 text-red-400'}`}>
                  {configured ? '已连接' : '未连接'}
                </span>
              </div>
            </div>

            {/* Test Button */}
            <button onClick={handleTestOpenai} disabled={testing}
              className="w-full flex items-center justify-center gap-2 p-3 rounded-lg bg-blue-500/10 text-blue-400 text-sm font-medium hover:bg-blue-500/20 transition-colors border border-blue-500/20 disabled:opacity-50">
              {testing ? (
                <><Loader2 className="w-4 h-4 animate-spin" /> 测试中...</>
              ) : (
                <><Wifi className="w-4 h-4" /> 测试 OpenAI 连接</>
              )}
            </button>

            <div className="flex items-center justify-between p-3 rounded-lg bg-slate-800/30 border border-slate-700/50">
              <span className="text-sm text-slate-400">认证模式</span>
              <span className="text-sm font-medium text-slate-200">{authMode}</span>
            </div>
            <div className="flex items-center justify-between p-3 rounded-lg bg-slate-800/30 border border-slate-700/50">
              <span className="text-sm text-slate-400">Responses API</span>
              <span className={`text-xs px-2 py-0.5 rounded-full ${responsesApi ? 'bg-emerald-500/10 text-emerald-400' : 'bg-slate-500/10 text-slate-500'}`}>
                {responsesApi ? '可用' : '不可用'}
              </span>
            </div>
            <div className="flex items-center justify-between p-3 rounded-lg bg-slate-800/30 border border-slate-700/50">
              <span className="text-sm text-slate-400">主配置</span>
              <span className={`text-xs px-2 py-0.5 rounded-full ${primaryOk ? 'bg-emerald-500/10 text-emerald-400' : 'bg-red-500/10 text-red-400'}`}>
                {primaryOk ? '已配置' : '未配置'}
              </span>
            </div>
          </CardBody>
        </Card>
      </div>

      {/* Known Models */}
      {knownModels.length > 0 && (
        <Card>
          <CardHeader title={`已知模型 (${caps.model_count || knownModels.length})`} />
          <div className="divide-y divide-slate-800/60">
            {knownModels.map((m, i) => (
              <div key={`${m}-${i}`} className="px-6 py-3 flex items-center gap-3 hover:bg-slate-800/30 transition-colors">
                <Zap className="w-4 h-4 text-slate-500" />
                <span className="text-sm text-slate-300">{m}</span>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  )
}
