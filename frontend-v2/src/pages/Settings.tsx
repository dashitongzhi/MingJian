import { AlertCircle, CheckCircle, Loader2, RefreshCw, Server, Wifi } from 'lucide-react'
import { Card, CardHeader, CardBody } from '../components/ui/Card'
import { LoadingSpinner } from '../components/ui/LoadingSpinner'
import { ErrorBanner } from '../components/ui/ErrorBanner'
import { settingsApi } from '../api/endpoints'
import { useApi, useApiAction } from '../hooks/useApi'

export default function Settings() {
  const { data: openaiStatus, loading, error, reload } = useApi(() => settingsApi.getOpenaiStatus())
  const { execute: doTest, loading: testing } = useApiAction(() => settingsApi.testOpenai())

  if (loading) return <LoadingSpinner />
  if (error) return <ErrorBanner message={error} onRetry={reload} />

  const oai = (openaiStatus || {}) as Record<string, unknown>
  const configured = Boolean(oai.configured)
  const responsesApi = Boolean(oai.responses_api)
  const primaryOk = Boolean(oai.primary_configured)
  const authMode = typeof oai.auth_mode === 'string' ? oai.auth_mode : '未知'

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">设置</h1>
          <p className="mt-1 text-sm text-slate-500">
            开源版不提供模型供应商管理 UI；请通过 `.env` 或 `PLANAGENT_OPENAI_*` 配置多供应商。
          </p>
        </div>
        <button onClick={reload} className="flex items-center gap-2 rounded-lg border border-slate-700/50 bg-slate-800/60 px-4 py-2 text-sm text-slate-400 transition-colors hover:text-slate-200">
          <RefreshCw className="h-4 w-4" /> 刷新
        </button>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader title="连接状态" />
          <CardBody className="space-y-3">
            <div className="flex items-center justify-between rounded-lg border border-slate-700/50 bg-slate-800/30 p-3">
              <div className="flex items-center gap-3">
                <Server className="h-4 w-4 text-slate-500" />
                <span className="text-sm text-slate-400">OpenAI 兼容连接</span>
              </div>
              <span className={`rounded-full px-2 py-0.5 text-xs ${configured ? 'bg-emerald-500/10 text-emerald-400' : 'bg-red-500/10 text-red-400'}`}>
                {configured ? '已配置' : '未配置'}
              </span>
            </div>

            <button
              onClick={() => doTest()}
              disabled={testing}
              className="flex w-full items-center justify-center gap-2 rounded-lg border border-blue-500/20 bg-blue-500/10 p-3 text-sm font-medium text-blue-400 transition-colors hover:bg-blue-500/20 disabled:opacity-50"
            >
              {testing ? (
                <><Loader2 className="h-4 w-4 animate-spin" /> 测试中...</>
              ) : (
                <><Wifi className="h-4 w-4" /> 测试连接</>
              )}
            </button>

            {[
              ['认证模式', authMode],
              ['Responses API', responsesApi ? '可用' : '不可用'],
              ['主配置', primaryOk ? '已配置' : '未配置'],
            ].map(([label, value]) => (
              <div key={label} className="flex items-center justify-between rounded-lg border border-slate-700/50 bg-slate-800/30 p-3">
                <span className="text-sm text-slate-400">{label}</span>
                <span className="text-sm font-medium text-slate-200">{value}</span>
              </div>
            ))}
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="多供应商配置" />
          <CardBody className="space-y-4">
            <div className="rounded-lg border border-blue-400/20 bg-blue-500/10 p-4">
              <div className="flex items-start gap-3">
                <CheckCircle className="mt-0.5 h-4 w-4 text-blue-300" />
                <div>
                  <p className="text-sm font-medium text-slate-100">配置文件方式</p>
                  <p className="mt-1 text-xs leading-5 text-slate-500">
                    使用 `.env` 中的 `PLANAGENT_OPENAI_*`、`PLANAGENT_ANTHROPIC_*`
                    和各角色 OpenAI 兼容配置即可启用多供应商。
                  </p>
                </div>
              </div>
            </div>
            <div className="rounded-lg border border-amber-400/20 bg-amber-500/10 p-4">
              <div className="flex items-start gap-3">
                <AlertCircle className="mt-0.5 h-4 w-4 text-amber-300" />
                <div>
                  <p className="text-sm font-medium text-slate-100">无 UI 管理</p>
                  <p className="mt-1 text-xs leading-5 text-slate-500">
                    供应商 CRUD、密钥托管、自定义 base URL 管理保留在 Cloud 和 Enterprise 版本。
                  </p>
                </div>
              </div>
            </div>
          </CardBody>
        </Card>
      </div>
    </div>
  )
}
