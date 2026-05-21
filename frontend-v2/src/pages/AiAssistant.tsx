import { useState, useRef, useEffect } from 'react'
import { Activity, Bot, Check, Download, Edit3, GitBranch, Loader2, MessageSquare, Plus, Radio, Send, ShieldCheck, User } from 'lucide-react'
import { Card, CardBody, CardHeader } from '../components/ui/Card'
import { EmptyState } from '../components/ui/EmptyState'
import { LoadingSpinner } from '../components/ui/LoadingSpinner'
import { ErrorBanner } from '../components/ui/ErrorBanner'
import { assistantApi, workbenchApi } from '../api/endpoints'
import { useApi, useApiAction } from '../hooks/useApi'

interface Session { id: string; title?: string; created_at: string; message_count?: number }
interface Message { role: string; content: string; created_at?: string }
interface SessionDetail { id: string; title?: string; messages?: Message[]; recent_runs?: unknown[]; [key: string]: unknown }

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
  if (status === 'pending') return '待检查'
  return status
}

function formatDateTime(value: unknown) {
  if (typeof value !== 'string' || !value) return '待调度'
  return new Date(value).toLocaleString()
}

export default function AiAssistant() {
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
    (data: { title?: string }) => assistantApi.createSession(data)
  )
  const { execute: doCreateRun, loading: sending } = useApiAction(
    (data: { session_id: string; message: string }) => assistantApi.createRun(data)
  )

  const detail = (sessionDetail || {}) as SessionDetail
  const messages = (detail.messages || []) as Message[]
  const latestRun = asRecord(asArray(detail.recent_runs)[0])
  const latestResult = asRecord(latestRun.result)
  const workflow = asRecord(latestResult.workflow)
  const monitoring = asRecord(latestResult.monitoring)
  const phases = asArray(workflow.phases).map(asRecord)

  // Auto-scroll
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages.length])

  const handleCreateSession = async () => {
    const r = await doCreateSession({ title: '新会话' })
    if (r) {
      const newSession = r as { id: string }
      setActiveSession(newSession.id)
      reload()
    }
  }

  const handleSend = async () => {
    if (!input.trim() || !activeSession) return
    const msg = input
    setInput('')
    const r = await doCreateRun({ session_id: activeSession, message: msg })
    if (r) {
      reloadSession()
      reload()
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleSaveTitle = () => {
    // Title update is a best-effort via createSession or a PATCH - keep it local for now
    setEditingTitle(false)
  }

  const handleExport = async () => {
    if (!activeSession) return
    setExporting(true)
    setExportError(null)
    try {
      await workbenchApi.exportAssistantSession(activeSession, 'md')
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
        className="p-1 rounded hover:bg-slate-800/40 text-slate-500 hover:text-slate-300 transition-colors">
        <Edit3 className="w-3.5 h-3.5" />
      </button>
    </div>
  ) : undefined

  return (
    <div className="space-y-8">
      {/* Header */}
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
        {/* Session List */}
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

        {/* Chat Area */}
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
                    24小时监控
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
                      本地短期监控用于首轮建议后的变化提醒
                    </div>
                  </div>
                </div>
              </div>
            </CardBody>
          )}

          {/* Messages */}
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
                <EmptyState icon="🤖" title="选择或创建会话" description="从左侧选择历史会话，或创建新的分析会话" />
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Input Area */}
          {activeSession && (
            <div className="px-6 py-4 border-t border-slate-800/60">
              <div className="flex gap-3">
                <input value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={handleKeyDown}
                  placeholder="输入分析主题，例如：台海局势分析..."
                  className="flex-1 bg-slate-800/40 border border-slate-700/50 rounded-lg px-4 py-2.5 text-sm text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-blue-500/50" />
                <button onClick={handleSend} disabled={sending || !input.trim()}
                  className="px-4 py-2.5 rounded-lg bg-blue-500 text-white text-sm font-medium hover:bg-blue-600 transition-colors disabled:opacity-50">
                  {sending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                </button>
              </div>
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}
