import { CheckCircle, KeyRound, PlugZap, RefreshCw, Server, X } from 'lucide-react'
import { useState } from 'react'
import { Card, CardBody, CardHeader } from '../components/ui/Card'
import { EmptyState } from '../components/ui/EmptyState'
import { LoadingSpinner } from '../components/ui/LoadingSpinner'
import { ErrorBanner } from '../components/ui/ErrorBanner'
import { providersApi, settingsApi } from '../api/endpoints'
import { useApi, useApiAction } from '../hooks/useApi'
import { JsonBlock, MetricCard, asArray, asRecord, titleOf } from '../components/ui/DataSurface'

export default function Providers() {
  const { data: providers, loading, error, reload } = useApi(() => providersApi.list())
  const { data: presets } = useApi(() => providersApi.presets())
  const { data: openaiStatus } = useApi(() => settingsApi.getOpenaiStatus())
  const { data: capabilities } = useApi(() => settingsApi.getModelCapabilities())
  const [editing, setEditing] = useState<Record<string, unknown> | null>(null)
  const [apiKey, setApiKey] = useState('')
  const { execute: saveProvider, loading: saving } = useApiAction((data: unknown) => providersApi.save(data))
  const { execute: testProvider, loading: testing } = useApiAction((data: unknown) => providersApi.test(data))

  if (loading) return <LoadingSpinner />
  if (error) return <ErrorBanner message={error} onRetry={reload} />

  const providerList = asArray(providers)
  const presetList = asArray(presets)
  const configured = providerList.filter((p) => Boolean(asRecord(p).configured || asRecord(p).api_key_set))

  const handleSave = async () => {
    if (!editing) return
    const payload = { ...editing, api_key: apiKey }
    const result = await saveProvider(payload)
    if (result) {
      setEditing(null)
      setApiKey('')
      reload()
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="text-xs text-blue-300">Providers</p>
          <h1 className="mt-1 text-3xl font-semibold text-slate-50">模型供应商</h1>
          <p className="mt-2 text-sm text-slate-500">对齐 `/admin/providers` 与模型能力、OpenAI 状态接口。</p>
        </div>
        <button onClick={reload} className="glass-button inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm text-slate-200"><RefreshCw className="h-4 w-4" />刷新</button>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
        <MetricCard label="供应商" value={providerList.length} icon={<Server className="h-5 w-5" />} tone="blue" />
        <MetricCard label="已配置" value={configured.length} icon={<CheckCircle className="h-5 w-5" />} tone="emerald" />
        <MetricCard label="预设" value={presetList.length} icon={<PlugZap className="h-5 w-5" />} tone="violet" />
        <MetricCard label="模型能力字段" value={Object.keys(asRecord(capabilities)).length} icon={<KeyRound className="h-5 w-5" />} tone="amber" />
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1.2fr_0.8fr]">
        <Card>
          <CardHeader title="供应商列表" />
          {providerList.length === 0 ? <CardBody><EmptyState icon="▧" title="暂无供应商" /></CardBody> : providerList.map((provider, index) => {
            const record = asRecord(provider)
            const isConfigured = Boolean(record.configured || record.api_key_set)
            return (
              <div key={String(record.id ?? index)} className="border-b border-slate-800/50 px-5 py-4 last:border-b-0">
                <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: String(record.color ?? '#3b82f6') }} />
                      <p className="truncate text-sm font-medium text-slate-100">{titleOf(provider, 'Provider')}</p>
                      <span className={isConfigured ? 'text-xs text-emerald-300' : 'text-xs text-slate-600'}>{isConfigured ? '已配置' : '未配置'}</span>
                    </div>
                    <p className="mt-1 truncate text-xs text-slate-600">{String(record.base_url ?? record.website ?? '')}</p>
                  </div>
                  <div className="flex gap-2">
                    <button onClick={() => testProvider({ base_url: record.base_url, api_key: apiKey, api_format: record.api_format, model: record.active_model })} disabled={testing} className="rounded-md border border-slate-700/70 px-3 py-1.5 text-xs text-slate-300 disabled:opacity-50">测试</button>
                    <button onClick={() => { setEditing(record); setApiKey('') }} className="rounded-md border border-blue-400/20 bg-blue-500/10 px-3 py-1.5 text-xs text-blue-300">配置</button>
                  </div>
                </div>
              </div>
            )
          })}
        </Card>

        <Card>
          <CardHeader title="模型与连接状态" />
          <CardBody><JsonBlock value={{ openaiStatus, capabilities }} /></CardBody>
        </Card>
      </div>

      {editing && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/62 px-4 backdrop-blur-sm" onClick={() => setEditing(null)}>
          <div className="liquid-glass w-full max-w-lg rounded-lg" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between border-b border-slate-800/60 px-5 py-4">
              <h3 className="text-sm font-semibold text-slate-100">配置 {titleOf(editing)}</h3>
              <button onClick={() => setEditing(null)} className="text-slate-500 hover:text-slate-200"><X className="h-4 w-4" /></button>
            </div>
            <div className="space-y-3 px-5 py-4">
              <input value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder="API Key" className="glass-input w-full rounded-lg px-3 py-2 text-sm" />
              <p className="text-xs text-slate-600">Base URL: {String(editing.base_url ?? '—')}</p>
            </div>
            <div className="flex justify-end gap-2 border-t border-slate-800/60 px-5 py-4">
              <button onClick={() => setEditing(null)} className="rounded-lg px-4 py-2 text-sm text-slate-400">取消</button>
              <button onClick={handleSave} disabled={saving} className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">保存</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
