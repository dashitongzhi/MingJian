import { useState, useRef, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  Activity,
  Bot,
  Check,
  Clock3,
  Database,
  Download,
  Edit3,
  GitBranch,
  HelpCircle,
  Loader2,
  MessageSquare,
  PauseCircle,
  Plus,
  Radio,
  Send,
  ShieldCheck,
  ThumbsUp,
  User,
  XCircle,
  Zap,
} from 'lucide-react'
import { Card, CardBody, CardHeader } from '../components/ui/Card'
import { EmptyState } from '../components/ui/EmptyState'
import { LoadingSpinner } from '../components/ui/LoadingSpinner'
import { ErrorBanner } from '../components/ui/ErrorBanner'
import { assistantApi, monitoringApi, reportApi, workbenchApi } from '../api/endpoints'
import { useApi, useApiAction } from '../hooks/useApi'

interface Session { id: string; title?: string; created_at: string; message_count?: number }
interface Message { role: string; content: string; created_at?: string }
interface SessionDetail { id: string; title?: string; messages?: Message[]; recent_runs?: unknown[]; [key: string]: unknown }

const decisionOptions = [
  { value: 'adopt', label: '采纳', icon: ThumbsUp },
  { value: 'defer', label: '暂缓', icon: PauseCircle },
  { value: 'need_more_info', label: '需更多信息', icon: HelpCircle },
  { value: 'reject', label: '拒绝', icon: XCircle },
]

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' ? value as Record<string, unknown> : {}
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : []
}

function displayStatus(value: unknown) {
  const status = String(value || 'pending')
  if (status === 'complete') return '完成'
  if (status === 'active') return '运行中'
  if (status === 'blocked') return '受限'
  if (status === 'failed') return '失败'
  if (status === 'skipped') return '跳过'
  if (status === 'healthy') return '正常'
  if (status === 'changed') return '已变化'
  if (status === 'degraded') return '降级'
  if (status === 'error') return '错误'
  if (status === 'pending') return '待检查'
  if (status === 'not_persisted') return '未持久化'
  return status
}

function formatDateTime(value: unknown) {
  if (typeof value !== 'string' || !value) return '待调度'
  return new Date(value).toLocaleString()
}

function decisionLabel(value: unknown) {
  const option = decisionOptions.find((item) => item.value === value)
  return option?.label || String(value || '未记录')
}

export default function AiAssistant() {
  const [searchParams] = useSearchParams()
  const sessionParam = searchParams.get('session')
  const { data: sessions, loading, error, reload } = useApi(() => assistantApi.listSessions())
  const [input, setInput] = useState('')
  const [activeSession, setActiveSession] = useState<string | null>(null)
  const [editingTitle, setEditingTitle] = useState(false)
  const [titleInput, setTitleInput] = useState('')
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState<string | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const { data: sessionDetail, reload: reloadSession } = useApi(
    () => activeSession ? assistantApi.getSession(activeSession) : Promise.resolve(null),
    [activeSession]
  )

  const { execute: doCreateSession, loading: creating } = useApiAction(
    (data: { topic: string; session_name?: string }) => assistantApi.createSession(data)
  )
  const { execute: doCreateRun, loading: sending } = useApiAction(
    (data: { session_id?: string; message: string; session_name?: string }) => assistantApi.createRun(data)
  )
  const { execute: createDecision, loading: deciding, error: decisionError } = useApiAction(
    (decision: string) => reportApi.createDecision({ session_id: activeSession, decision })
  )

  useEffect(() => {
    if (sessionParam && sessionParam !== activeSession) {
      setActiveSession(sessionParam)
    }
  }, [sessionParam, activeSession])

  const detail = (sessionDetail || {}) as SessionDetail
  const messages = (detail.messages || []) as Message[]
  const latestRun = asRecord(asArray(detail.recent_runs)[0])
  const latestResult = asRecord(latestRun.result)
  const workflow = asRecord(latestResult.workflow)
  const monitoring = asRecord(latestResult.monitoring)
  const phases = asArray(workflow.phases).map(asRecord)
  const watchRuleId = typeof monitoring.watch_rule_id === 'string' ? monitoring.watch_rule_id : null
  const { data: recommendationsRaw } = useApi(
    () => activeSession ? assistantApi.getRecommendations(activeSession) : Promise.resolve([]),
    [activeSession]
  )
  const { data: sourceStatesRaw } = useApi(
    () => watchRuleId ? monitoringApi.getWatchRuleSources(watchRuleId) : Promise.resolve([]),
    [watchRuleId]
  )
  const { data: decisionsRaw, reload: reloadDecisions } = useApi(
    () => activeSession ? reportApi.listDecisions(activeSession) : Promise.resolve([]),
    [activeSession]
  )
  const recommendationVersions = asArray(recommendationsRaw).map(asRecord)
  const sourceStates = asArray(sourceStatesRaw).map(asRecord)
  const decisions = asArray(decisionsRaw).map(asRecord)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages.length])

  const handleCreateSession = async () => {
    const r = await doCreateSession({ topic: '新的辅助决策问题', session_name: '新会话' })
    if (r) {
      const newSession = r as { id: string }
      setActiveSession(newSession.id)
      reload()
    }
  }

  const handleSend = async () => {
    if (!input.trim()) return
    const msg = input
    setInput('')
    let sessionId = activeSession
    if (!sessionId) {
      const created = await doCreateSession({
        topic: msg,
        session_name: msg.slice(0, 48),
      })
      if (!created) {
        setInput(msg)
        return
      }
      sessionId = (created as { id: string }).id
      setActiveSession(sessionId)
      reload()
    }
    const r = await doCreateRun({ session_id: sessionId, message: msg })
    if (r) {
      reloadSession()
      reload()
    }
  }

  const handleDecision = async (decision: string) => {
    if (!activeSession) return
    const r = await createDecision(decision)
    if (r) reloadDecisions()
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleSaveTitle = () => {
    setEditingTitle(false)
  }

  const handleExport = async () => {
    if (!activeSession) return
    setExporting(true)
    setExportError(null)
    try {
      await workbenchApi.exportAssistantSession(activeSession)
    } catch (err) {
      setExportError(err instanceof Error ? err.message : '导出失败')
    } finally {
      setExporting(false)
    }
  }

  if (loading) return <LoadingSpinner />
  if (error) return <ErrorBanner message={error} onRetry={reload} />

  const sessionList = (sessions || []) as Session[]
  const headerAction = editingTitle ? (
    <div className="flex items-center gap-2">
      <input value={titleInput} onChange={(e) => setTitleInput(e.target.value)}
        className="bg-slate-800/40 border border-slate-700/50 rounded px-2 py-0.5 text-sm text-slate-200 focus:outline-none focus:border-blue-500/50" />
      <button onClick={handleSaveTitle} className="p-0.5 text-emerald-400 hover:text-emerald-300"><Check className="w-3.5 h-3.5" /></button>
    </div>
  ) : activeSession ? (
    <div className="flex items-center gap-2">
      <button onClick={handleExport} disabled={exporting}
        className="p-1 rounded hover:bg-slate-800/40 text-slate-500 hover:text-slate-300 transition-colors disabled:opacity-50"
        title="导出 Markdown 报告">
        {exporting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />}
      </button>
      <button onClick={() => { setEditingTitle(true); setTitleInput((detail.title as string) || '') }}
        className="p-1 rounded hover:bg-slate-800/40 text-slate-500 hover:text-slate-300 transition-colors"
        title="编辑标题">
        <Edit3 className="w-3.5 h-3.5" />
      </button>
    </div>
  ) : undefined

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">AI 助手</h1>
          <p className="text-sm text-slate-500 mt-1">战略分析助手 · 多智能体协作</p>
        </div>
        <button onClick={handleCreateSession} disabled={creating}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-500/10 text-blue-400 text-sm font-medium hover:bg-blue-500/20 transition-colors border border-blue-500/20 disabled:opacity-50">
          <Plus className="w-4 h-4" /> 新建会话
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-1">
          <CardHeader title={`历史会话 (${sessionList.length})`} />
          <div className="divide-y divide-slate-800/60">
            {sessionList.length === 0 ? (
              <div className="p-6"><EmptyState icon="💬" title="暂无会话" description="创建新会话开始分析" /></div>
            ) : sessionList.map((s) => (
              <button key={s.id} onClick={() => setActiveSession(s.id)}
                className={`w-full text-left px-6 py-4 hover:bg-slate-800/30 transition-colors ${activeSession === s.id ? 'bg-blue-500/5' : ''}`}>
                <div className="flex items-center gap-3">
                  <MessageSquare className="w-4 h-4 text-slate-500 shrink-0" />
                  <div className="min-w-0">
                    <p className="text-sm text-slate-300 truncate">{s.title || '未命名会话'}</p>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className="text-xs text-slate-600">{new Date(s.created_at).toLocaleDateString()}</span>
                      {s.message_count !== undefined && <span className="text-xs text-slate-600">{s.message_count} 消息</span>}
                    </div>
                  </div>
                </div>
              </button>
            ))}
          </div>
        </Card>

        <Card className="lg:col-span-2 flex flex-col min-h-[600px]">
          <CardHeader
            title={
              editingTitle
                ? titleInput || detail.title || '会话详情'
                : activeSession
                  ? (detail.title as string) || '会话详情'
                  : '新会话'
            }
            action={headerAction}
          />

          {(phases.length > 0 || Object.keys(monitoring).length > 0 || exportError) && (
            <CardBody className="border-b border-slate-800/60 bg-slate-950/20">
              <div className="grid grid-cols-1 gap-3 xl:grid-cols-[1.3fr_0.7fr]">
                <div className="rounded-lg border border-slate-800/70 bg-slate-950/35 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-2 text-sm font-semibold text-slate-100">
                      <GitBranch className="h-4 w-4 text-blue-300" />
                      决策工作流
                    </div>
                    <span className="rounded-md border border-emerald-400/20 bg-emerald-500/10 px-2 py-1 text-xs text-emerald-300">
                      {workflow.user_can_decide ? '可辅助决策' : '处理中'}
                    </span>
                  </div>
                  <div className="mt-4 grid gap-2 md:grid-cols-4">
                    {phases.map((phase) => (
                      <div key={String(phase.key)} className="min-h-[92px] rounded-md border border-slate-800/70 bg-slate-900/35 p-3">
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-xs font-medium text-slate-200">{String(phase.label || phase.key)}</span>
                          <ShieldCheck className={`h-4 w-4 ${phase.status === 'complete' || phase.status === 'active' ? 'text-emerald-300' : 'text-amber-300'}`} />
                        </div>
                        <div className="mt-2 text-xs text-slate-500">{displayStatus(phase.status)}</div>
                        {phase.count !== undefined && <div className="mt-1 text-xs text-slate-600">证据 {String(phase.count)}</div>}
                      </div>
                    ))}
                  </div>
                  {exportError && <div className="mt-3 text-xs text-red-300">{exportError}</div>}
                </div>
                <div className="rounded-lg border border-slate-800/70 bg-slate-950/35 p-4">
                  <div className="flex items-center gap-2 text-sm font-semibold text-slate-100">
                    <Radio className="h-4 w-4 text-emerald-300" />
                    24 小时监控
                  </div>
                  <div className="mt-3 space-y-2 text-xs text-slate-500">
                    <div className="flex items-center justify-between gap-3">
                      <span>状态</span>
                      <span className={`rounded border px-2 py-1 ${monitoring.status === 'active' ? 'border-emerald-400/20 bg-emerald-500/10 text-emerald-300' : 'border-amber-400/20 bg-amber-500/10 text-amber-300'}`}>
                        {displayStatus(monitoring.status)}
                      </span>
                    </div>
                    <div className="flex items-center justify-between gap-3">
                      <span>轮询间隔</span>
                      <span className="text-slate-300">{String(monitoring.poll_interval_minutes || '—')} 分钟</span>
                    </div>
                    <div className="flex items-center justify-between gap-3">
                      <span>下次更新</span>
                      <span className="text-right text-slate-300">{formatDateTime(monitoring.next_poll_at)}</span>
                    </div>
                    <div className="flex items-center gap-2 pt-1 text-slate-600">
                      <Activity className="h-3.5 w-3.5" />
                      固定时间更新，重大源变更会触发重新分析和辩论
                    </div>
                  </div>
                </div>
              </div>

              <div className="mt-3 grid grid-cols-1 gap-3 xl:grid-cols-3">
                <div className="rounded-lg border border-slate-800/70 bg-slate-950/35 p-4">
                  <div className="flex items-center gap-2 text-sm font-semibold text-slate-100">
                    <Database className="h-4 w-4 text-cyan-300" />
                    信息源监测
                  </div>
                  <div className="mt-3 grid gap-2">
                    {sourceStates.length === 0 ? (
                      <div className="text-xs text-slate-600">暂无源游标状态</div>
                    ) : sourceStates.slice(0, 6).map((source) => (
                      <div key={String(source.id)} className="rounded-md border border-slate-800/70 bg-slate-900/30 p-3">
                        <div className="flex items-center justify-between gap-2">
                          <span className="truncate text-xs font-medium text-slate-200">{String(source.source_type || 'source')}</span>
                          <span className={`rounded border px-1.5 py-0.5 text-[11px] ${source.health_status === 'healthy' ? 'border-emerald-400/20 bg-emerald-500/10 text-emerald-300' : source.health_status === 'pending' ? 'border-slate-600 bg-slate-800/50 text-slate-400' : 'border-amber-400/20 bg-amber-500/10 text-amber-300'}`}>
                            {displayStatus(source.health_status)}
                          </span>
                        </div>
                        <div className="mt-2 space-y-1 text-[11px] text-slate-500">
                          <div className="flex justify-between gap-2"><span>检查</span><span className="truncate text-slate-400">{formatDateTime(source.last_checked_at)}</span></div>
                          <div className="flex justify-between gap-2"><span>变化</span><span className="truncate text-slate-400">{formatDateTime(source.last_change_at)}</span></div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="rounded-lg border border-slate-800/70 bg-slate-950/35 p-4">
                  <div className="flex items-center gap-2 text-sm font-semibold text-slate-100">
                    <Zap className="h-4 w-4 text-amber-300" />
                    建议版本
                  </div>
                  <div className="mt-3 space-y-2">
                    {recommendationVersions.length === 0 ? (
                      <div className="text-xs text-slate-600">暂无建议版本</div>
                    ) : recommendationVersions.slice(0, 5).map((version) => (
                      <div key={String(version.id)} className="rounded-md border border-slate-800/70 bg-slate-900/30 p-3">
                        <div className="flex items-center justify-between gap-3">
                          <div className="flex items-center gap-2 text-xs text-slate-300">
                            <Clock3 className="h-3.5 w-3.5 text-slate-500" />
                            v{String(version.version_number || '-')} · {String(version.trigger_type || 'update')}
                          </div>
                          <span className={`rounded border px-1.5 py-0.5 text-[11px] ${version.significance === 'high' ? 'border-red-400/20 bg-red-500/10 text-red-300' : version.significance === 'medium' ? 'border-amber-400/20 bg-amber-500/10 text-amber-300' : 'border-slate-700 bg-slate-800/40 text-slate-400'}`}>
                            {String(version.significance || 'none')}
                          </span>
                        </div>
                        <p className="mt-2 line-clamp-2 text-xs leading-relaxed text-slate-300">{String(version.recommendation_summary || '暂无建议摘要')}</p>
                        <div className="mt-2 text-[11px] text-slate-600">{formatDateTime(version.generated_at)}</div>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="rounded-lg border border-slate-800/70 bg-slate-950/35 p-4">
                  <div className="flex items-center gap-2 text-sm font-semibold text-slate-100">
                    <Check className="h-4 w-4 text-emerald-300" />
                    决策反馈
                  </div>
                  <div className="mt-3 grid grid-cols-2 gap-2">
                    {decisionOptions.map((option) => {
                      const Icon = option.icon
                      return (
                        <button key={option.value} onClick={() => handleDecision(option.value)} disabled={!activeSession || deciding}
                          className="flex items-center justify-center gap-1.5 rounded-md border border-slate-800/80 bg-slate-900/35 px-2 py-2 text-xs text-slate-300 transition-colors hover:border-blue-400/30 hover:text-blue-200 disabled:opacity-50">
                          <Icon className="h-3.5 w-3.5" />
                          {option.label}
                        </button>
                      )
                    })}
                  </div>
                  {decisionError && <div className="mt-2 text-xs text-red-300">{decisionError}</div>}
                  <div className="mt-3 space-y-2">
                    {decisions.length === 0 ? (
                      <div className="text-xs text-slate-600">尚未记录用户决策</div>
                    ) : decisions.slice(0, 3).map((decision) => (
                      <div key={String(decision.id)} className="rounded-md border border-slate-800/70 bg-slate-900/30 p-3">
                        <div className="flex items-center justify-between gap-2 text-xs">
                          <span className="text-slate-200">{decisionLabel(decision.decision)}</span>
                          <span className="text-slate-600">{formatDateTime(decision.created_at)}</span>
                        </div>
                        {typeof decision.notes === 'string' && decision.notes.length > 0 && (
                          <p className="mt-1 line-clamp-2 text-xs text-slate-500">{decision.notes}</p>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </CardBody>
          )}

          <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
            {activeSession ? (
              messages.length > 0 ? (
                messages.map((m, i) => (
                  <div key={i} className={`flex gap-3 ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                    {m.role !== 'user' && (
                      <div className="w-7 h-7 rounded-full bg-blue-500/10 flex items-center justify-center shrink-0">
                        <Bot className="w-4 h-4 text-blue-400" />
                      </div>
                    )}
                    <div className={`max-w-[75%] rounded-lg px-4 py-2.5 text-sm leading-relaxed ${m.role === 'user'
                      ? 'bg-blue-500/10 text-blue-100 border border-blue-500/20'
                      : 'bg-slate-800/30 text-slate-300 border border-slate-700/50'}`}>
                      <p className="whitespace-pre-wrap">{m.content}</p>
                      {m.created_at && <p className="text-xs text-slate-600 mt-1">{new Date(m.created_at).toLocaleTimeString()}</p>}
                    </div>
                    {m.role === 'user' && (
                      <div className="w-7 h-7 rounded-full bg-slate-700/50 flex items-center justify-center shrink-0">
                        <User className="w-4 h-4 text-slate-400" />
                      </div>
                    )}
                  </div>
                ))
              ) : (
                <div className="flex-1 flex items-center justify-center">
                  <EmptyState icon="🤖" title="开始对话" description="输入消息开始与 AI 助手交流" />
                </div>
              )
            ) : (
              <div className="flex-1 flex items-center justify-center">
                <EmptyState icon="🤖" title="选择或创建会话" description="从左侧选择历史会话，或直接输入新的辅助决策问题" />
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          <div className="px-6 py-4 border-t border-slate-800/60">
            <div className="flex gap-3">
              <input value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={handleKeyDown}
                placeholder="输入辅助决策问题，例如：是否应该进入某个市场，接下来怎么做..."
                className="flex-1 bg-slate-800/40 border border-slate-700/50 rounded-lg px-4 py-2.5 text-sm text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-blue-500/50" />
              <button onClick={handleSend} disabled={sending || creating || !input.trim()}
                className="px-4 py-2.5 rounded-lg bg-blue-500 text-white text-sm font-medium hover:bg-blue-600 transition-colors disabled:opacity-50">
                {sending || creating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
              </button>
            </div>
          </div>
        </Card>
      </div>
    </div>
  )
}
