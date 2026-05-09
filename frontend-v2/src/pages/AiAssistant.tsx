import { useState } from 'react'
import { MessageSquare, Plus, Send } from 'lucide-react'
import { Card, CardHeader } from '../components/ui/Card'
import { EmptyState } from '../components/ui/EmptyState'
import { LoadingSpinner } from '../components/ui/LoadingSpinner'
import { ErrorBanner } from '../components/ui/ErrorBanner'
import { assistantApi } from '../api/endpoints'
import { useApi } from '../hooks/useApi'

interface Session { id: string; title?: string; created_at: string }

export default function AiAssistant() {
  const { data: sessions, loading, error, reload } = useApi(() => assistantApi.listSessions())
  const [input, setInput] = useState('')
  const [activeSession, setActiveSession] = useState<string | null>(null)

  if (loading) return <LoadingSpinner />
  if (error) return <ErrorBanner message={error} onRetry={reload} />

  const sessionList = (sessions || []) as Session[]

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">AI 助手</h1>
          <p className="text-sm text-slate-500 mt-1">战略分析助手 · 多智能体协作</p>
        </div>
        <button className="flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-500/10 text-blue-400 text-sm font-medium hover:bg-blue-500/20 transition-colors border border-blue-500/20">
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
                    <p className="text-xs text-slate-600 mt-0.5">{new Date(s.created_at).toLocaleDateString()}</p>
                  </div>
                </div>
              </button>
            ))}
          </div>
        </Card>

        <Card className="lg:col-span-2 flex flex-col min-h-[600px]">
          <CardHeader title={activeSession ? '会话详情' : '新会话'} />
          <div className="flex-1 px-6 py-4">
            {activeSession ? (
              <p className="text-sm text-slate-400">会话 ID: {activeSession}</p>
            ) : (
              <EmptyState icon="🤖" title="选择或创建会话" description="从左侧选择历史会话，或创建新的分析会话" />
            )}
          </div>
          <div className="px-6 py-4 border-t border-slate-800/60">
            <div className="flex gap-3">
              <input value={input} onChange={(e) => setInput(e.target.value)}
                placeholder="输入分析主题，例如：台海局势分析..."
                className="flex-1 bg-slate-800/40 border border-slate-700/50 rounded-lg px-4 py-2.5 text-sm text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-blue-500/50" />
              <button className="px-4 py-2.5 rounded-lg bg-blue-500 text-white text-sm font-medium hover:bg-blue-600 transition-colors">
                <Send className="w-4 h-4" />
              </button>
            </div>
          </div>
        </Card>
      </div>
    </div>
  )
}
