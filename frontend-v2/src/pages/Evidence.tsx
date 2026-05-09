import { useState } from 'react'
import { Library, Search, Shield, Radio, CheckCircle, XCircle, AlertTriangle } from 'lucide-react'
import { Card, CardHeader } from '../components/ui/Card'
import { StatusBadge } from '../components/ui/StatusBadge'
import { EmptyState } from '../components/ui/EmptyState'
import { LoadingSpinner } from '../components/ui/LoadingSpinner'
import { ErrorBanner } from '../components/ui/ErrorBanner'
import { evidenceApi, sourcesApi } from '../api/endpoints'
import { useApi } from '../hooks/useApi'

interface EvItem { id: string; title: string; summary?: string; body_text?: string; source_url?: string; confidence?: number; status?: string; created_at: string }
interface ReviewItem { id: string; title?: string; status: string; source?: string; created_at: string }
interface SourceState { key: string; name: string; status: string; last_check?: string; error_count?: number }

type Tab = 'evidence' | 'claims' | 'signals' | 'review' | 'sources'

export default function Evidence() {
  const [tab, setTab] = useState<Tab>('evidence')
  const { data: evidenceResp, loading, error, reload } = useApi(() => evidenceApi.list())
  const { data: claimsResp } = useApi(() => evidenceApi.listClaims())
  const { data: signalsResp } = useApi(() => evidenceApi.listSignals())
  const { data: reviewItems } = useApi(() => evidenceApi.listReviewItems())
  const { data: sourceStates } = useApi(() => sourcesApi.listStates())

  if (loading) return <LoadingSpinner />
  if (error) return <ErrorBanner message={error} onRetry={reload} />

  const evidence = (evidenceResp?.items || []) as EvItem[]
  const claims = (claimsResp?.items || []) as { id: string; statement?: string; claim_text?: string; status: string }[]
  const signals = (signalsResp?.items || []) as { id: string; name?: string; signal_text?: string; value?: number; change?: number; source?: string }[]
  const reviews = (reviewItems || []) as ReviewItem[]
  const sources = (sourceStates || []) as SourceState[]

  const tabs: { key: Tab; label: string; count: number }[] = [
    { key: 'evidence', label: '证据', count: evidence.length },
    { key: 'claims', label: '论断', count: claims.length },
    { key: 'signals', label: '信号', count: signals.length },
    { key: 'review', label: '待审核', count: reviews.filter((r) => r.status === 'pending').length },
    { key: 'sources', label: '数据源', count: sources.length },
  ]

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-slate-100">证据库</h1>
        <p className="text-sm text-slate-500 mt-1">证据采集 · 论断验证 · 数据源管理</p>
      </div>

      <div className="flex gap-1 p-1 bg-slate-900/60 rounded-lg border border-slate-800 w-fit">
        {tabs.map((t) => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={`px-4 py-2 rounded-md text-sm transition-all ${tab === t.key ? 'bg-blue-500/10 text-blue-400 font-medium' : 'text-slate-500 hover:text-slate-300'}`}>
            {t.label} <span className="text-xs opacity-60">({t.count})</span>
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {[
          { label: '证据总数', value: String(evidence.length), icon: Library, color: 'text-blue-400', bg: 'bg-blue-500/10' },
          { label: '论断', value: String(claims.length), icon: Shield, color: 'text-emerald-400', bg: 'bg-emerald-500/10' },
          { label: '信号', value: String(signals.length), icon: Radio, color: 'text-amber-400', bg: 'bg-amber-500/10' },
          { label: '待审核', value: String(reviews.filter((r) => r.status === 'pending').length), icon: AlertTriangle, color: 'text-red-400', bg: 'bg-red-500/10' },
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
        <CardHeader title={tabs.find((t) => t.key === tab)?.label || ''}
          action={tab === 'evidence' ? (
            <div className="flex items-center gap-2 bg-slate-800/40 rounded-lg px-3 py-1.5 border border-slate-700/50">
              <Search className="w-3.5 h-3.5 text-slate-500" />
              <input placeholder="搜索证据..." className="bg-transparent text-sm text-slate-300 placeholder:text-slate-600 focus:outline-none w-40" />
            </div>
          ) : undefined}
        />
        <div className="divide-y divide-slate-800/60">
          {tab === 'evidence' && (evidence.length === 0 ? <EmptyState icon="📚" title="暂无证据" description="通过数据源采集证据" /> :
            evidence.map((e) => (
              <div key={e.id} className="px-6 py-4">
                <div className="flex items-start justify-between">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-slate-200">{e.title}</p>
                    <p className="text-xs text-slate-500 mt-1 line-clamp-2">{e.summary || e.body_text}</p>
                    <p className="text-xs text-slate-600 mt-2">{new Date(e.created_at).toLocaleDateString()}</p>
                  </div>
                  {e.confidence !== undefined && (
                    <span className="text-xs text-slate-500 bg-slate-800/60 px-2 py-1 rounded ml-4 shrink-0">
                      可信度 {Math.round(e.confidence * 100)}%
                    </span>
                  )}
                </div>
              </div>
            ))
          )}

          {tab === 'claims' && (claims.length === 0 ? <EmptyState icon="🛡️" title="暂无论断" /> :
            claims.map((c) => (
              <div key={c.id} className="px-6 py-4 flex items-center justify-between">
                <p className="text-sm text-slate-300">{c.statement || c.claim_text || c.id}</p>
                <StatusBadge status={c.status} />
              </div>
            ))
          )}

          {tab === 'signals' && (signals.length === 0 ? <EmptyState icon="📡" title="暂无信号" /> :
            signals.map((s) => (
              <div key={s.id} className="px-6 py-4 flex items-center justify-between">
                <div>
                  <p className="text-sm text-slate-300">{s.name || s.signal_text || s.id}</p>
                  {s.source && <p className="text-xs text-slate-500">{s.source}</p>}
                </div>
                <div className="text-right">
                  {s.value !== undefined && <span className="text-sm font-mono text-slate-200">{s.value}</span>}
                  {s.change !== undefined && (
                    <span className={`text-xs ml-2 ${s.change >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                      {s.change >= 0 ? '+' : ''}{s.change}%
                    </span>
                  )}
                </div>
              </div>
            ))
          )}

          {tab === 'review' && (reviews.length === 0 ? <EmptyState icon="✅" title="暂无待审核项" /> :
            reviews.map((r) => (
              <div key={r.id} className="px-6 py-4 flex items-center justify-between">
                <div>
                  <p className="text-sm text-slate-300">{r.title || r.id}</p>
                  <p className="text-xs text-slate-500">{new Date(r.created_at).toLocaleDateString()}</p>
                </div>
                <div className="flex items-center gap-2">
                  <StatusBadge status={r.status} />
                  {r.status === 'pending' && (
                    <div className="flex gap-1">
                      <button className="p-1.5 rounded hover:bg-emerald-500/10 text-emerald-400 transition-colors"><CheckCircle className="w-4 h-4" /></button>
                      <button className="p-1.5 rounded hover:bg-red-500/10 text-red-400 transition-colors"><XCircle className="w-4 h-4" /></button>
                    </div>
                  )}
                </div>
              </div>
            ))
          )}

          {tab === 'sources' && (sources.length === 0 ? <EmptyState icon="🔌" title="暂无数据源" /> :
            sources.map((s) => (
              <div key={s.key} className="px-6 py-4 flex items-center justify-between">
                <div>
                  <p className="text-sm text-slate-300">{s.name}</p>
                  <p className="text-xs text-slate-500">{s.key} · 上次检查: {s.last_check || '未知'}</p>
                </div>
                <div className="flex items-center gap-3">
                  {s.error_count !== undefined && s.error_count > 0 && <span className="text-xs text-red-400">{s.error_count} 错误</span>}
                  <StatusBadge status={s.status} />
                </div>
              </div>
            ))
          )}
        </div>
      </Card>
    </div>
  )
}
