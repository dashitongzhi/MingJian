import { useState } from 'react'
import { Library, Search, Shield, Radio, CheckCircle, XCircle, AlertTriangle, ExternalLink, ChevronDown, ChevronRight, Wifi, WifiOff } from 'lucide-react'
import { Card, CardHeader } from '../components/ui/Card'
import { StatusBadge } from '../components/ui/StatusBadge'
import { EmptyState } from '../components/ui/EmptyState'
import { LoadingSpinner } from '../components/ui/LoadingSpinner'
import { ErrorBanner } from '../components/ui/ErrorBanner'
import { evidenceApi, sourcesApi } from '../api/endpoints'
import { useApi, useApiAction } from '../hooks/useApi'

interface EvItem {
  id: string; title: string; summary?: string; body_text?: string; source_url?: string;
  confidence?: number; status?: string; created_at: string; source?: string; tags?: string[];
}
interface ReviewItem { id: string; title?: string; status: string; source?: string; created_at: string }
interface SourceState {
  key: string; name: string; status: string; last_check?: string; error_count?: number;
  health_score?: number; last_success?: string; total_fetched?: number;
}

type Tab = 'evidence' | 'claims' | 'signals' | 'review' | 'sources'

export default function Evidence() {
  const [tab, setTab] = useState<Tab>('evidence')
  const [expandedEvidence, setExpandedEvidence] = useState<string | null>(null)
  const { data: evidenceResp, loading, error, reload } = useApi(() => evidenceApi.list())
  const { data: claimsResp } = useApi(() => evidenceApi.listClaims())
  const { data: signalsResp } = useApi(() => evidenceApi.listSignals())
  const { data: reviewItems, reload: reloadReview } = useApi(() => evidenceApi.listReviewItems())
  const { data: sourceStates } = useApi(() => sourcesApi.listStates())

  const { execute: doAccept, loading: accepting } = useApiAction((id: string) => evidenceApi.acceptReview(id))
  const { execute: doReject, loading: rejecting } = useApiAction((id: string) => evidenceApi.rejectReview(id))

  const handleAccept = async (id: string) => {
    const r = await doAccept(id)
    if (r) reloadReview()
  }

  const handleReject = async (id: string) => {
    const r = await doReject(id)
    if (r) reloadReview()
  }

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

      {/* Tabs */}
      <div className="flex gap-1 p-1 bg-slate-900/60 rounded-lg border border-slate-800 w-fit">
        {tabs.map((t) => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={`px-4 py-2 rounded-md text-sm transition-all ${tab === t.key ? 'bg-blue-500/10 text-blue-400 font-medium' : 'text-slate-500 hover:text-slate-300'}`}>
            {t.label} <span className="text-xs opacity-60">({t.count})</span>
          </button>
        ))}
      </div>

      {/* Stats */}
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

      {/* Main Content */}
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
          {/* Evidence Tab */}
          {tab === 'evidence' && (evidence.length === 0 ? <EmptyState icon="📚" title="暂无证据" description="通过数据源采集证据" /> :
            evidence.map((e) => (
              <div key={e.id}>
                <button onClick={() => setExpandedEvidence(expandedEvidence === e.id ? null : e.id)}
                  className="w-full text-left px-6 py-4 hover:bg-slate-800/30 transition-colors">
                  <div className="flex items-start justify-between">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <p className="text-sm font-medium text-slate-200">{e.title}</p>
                        {expandedEvidence === e.id ? <ChevronDown className="w-3.5 h-3.5 text-slate-500 shrink-0" /> : <ChevronRight className="w-3.5 h-3.5 text-slate-500 shrink-0" />}
                      </div>
                      <p className="text-xs text-slate-500 mt-1 line-clamp-2">{e.summary || e.body_text}</p>
                      <div className="flex items-center gap-3 mt-2">
                        <span className="text-xs text-slate-600">{new Date(e.created_at).toLocaleDateString()}</span>
                        {e.source && <span className="text-xs text-slate-600">来源: {e.source}</span>}
                      </div>
                    </div>
                    <div className="flex flex-col items-end gap-1 ml-4 shrink-0">
                      {e.confidence !== undefined && (
                        <span className="text-xs text-slate-500 bg-slate-800/60 px-2 py-1 rounded">
                          可信度 {Math.round(e.confidence * 100)}%
                        </span>
                      )}
                      {e.status && <StatusBadge status={e.status} />}
                    </div>
                  </div>
                </button>

                {/* Expanded Detail */}
                {expandedEvidence === e.id && (
                  <div className="px-6 pb-4 border-t border-slate-800/40">
                    {/* Confidence Bar */}
                    {e.confidence !== undefined && (
                      <div className="mt-4 mb-3">
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-xs text-slate-500">可信度</span>
                          <span className="text-xs font-mono text-slate-300">{Math.round(e.confidence * 100)}%</span>
                        </div>
                        <div className="w-full h-1.5 bg-slate-700/50 rounded-full overflow-hidden">
                          <div className={`h-full rounded-full transition-all ${e.confidence >= 0.7 ? 'bg-emerald-500' : e.confidence >= 0.4 ? 'bg-amber-500' : 'bg-red-500'}`}
                            style={{ width: `${Math.round(e.confidence * 100)}%` }} />
                        </div>
                      </div>
                    )}

                    {/* Full Content */}
                    {e.body_text && (
                      <div className="mt-3 p-3 rounded-lg bg-slate-800/30 border border-slate-700/50">
                        <p className="text-sm text-slate-300 leading-relaxed whitespace-pre-wrap">{e.body_text}</p>
                      </div>
                    )}

                    {/* Source Link */}
                    {e.source_url && (
                      <div className="mt-3 flex items-center gap-2">
                        <ExternalLink className="w-3.5 h-3.5 text-slate-500" />
                        <a href={e.source_url} target="_blank" rel="noopener noreferrer"
                          className="text-xs text-blue-400 hover:text-blue-300 transition-colors truncate">{e.source_url}</a>
                      </div>
                    )}

                    {/* Tags */}
                    {e.tags && e.tags.length > 0 && (
                      <div className="mt-3 flex flex-wrap gap-1.5">
                        {e.tags.map((tag, i) => (
                          <span key={i} className="px-2 py-0.5 rounded-full bg-slate-800/60 text-xs text-slate-400 border border-slate-700/50">{tag}</span>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))
          )}

          {/* Claims Tab */}
          {tab === 'claims' && (claims.length === 0 ? <EmptyState icon="🛡️" title="暂无论断" /> :
            claims.map((c) => (
              <div key={c.id} className="px-6 py-4 flex items-center justify-between hover:bg-slate-800/30 transition-colors">
                <p className="text-sm text-slate-300">{c.statement || c.claim_text || c.id}</p>
                <StatusBadge status={c.status} />
              </div>
            ))
          )}

          {/* Signals Tab */}
          {tab === 'signals' && (signals.length === 0 ? <EmptyState icon="📡" title="暂无信号" /> :
            signals.map((s) => (
              <div key={s.id} className="px-6 py-4 flex items-center justify-between hover:bg-slate-800/30 transition-colors">
                <div>
                  <p className="text-sm text-slate-300">{s.name || s.signal_text || s.id}</p>
                  {s.source && <p className="text-xs text-slate-500">{s.source}</p>}
                </div>
                <div className="text-right flex items-center gap-3">
                  {s.value !== undefined && <span className="text-sm font-mono text-slate-200">{s.value}</span>}
                  {s.change !== undefined && (
                    <span className={`text-xs ${s.change >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                      {s.change >= 0 ? '+' : ''}{s.change}%
                    </span>
                  )}
                </div>
              </div>
            ))
          )}

          {/* Review Tab */}
          {tab === 'review' && (reviews.length === 0 ? <EmptyState icon="✅" title="暂无待审核项" /> :
            reviews.map((r) => (
              <div key={r.id} className="px-6 py-4 flex items-center justify-between hover:bg-slate-800/30 transition-colors">
                <div>
                  <p className="text-sm text-slate-300">{r.title || r.id}</p>
                  <div className="flex items-center gap-2 mt-0.5">
                    <span className="text-xs text-slate-600">{new Date(r.created_at).toLocaleDateString()}</span>
                    {r.source && <span className="text-xs text-slate-600">来源: {r.source}</span>}
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <StatusBadge status={r.status} />
                  {r.status === 'pending' && (
                    <div className="flex gap-1">
                      <button onClick={() => handleAccept(r.id)} disabled={accepting}
                        className="p-1.5 rounded hover:bg-emerald-500/10 text-emerald-400 transition-colors disabled:opacity-50">
                        <CheckCircle className="w-4 h-4" />
                      </button>
                      <button onClick={() => handleReject(r.id)} disabled={rejecting}
                        className="p-1.5 rounded hover:bg-red-500/10 text-red-400 transition-colors disabled:opacity-50">
                        <XCircle className="w-4 h-4" />
                      </button>
                    </div>
                  )}
                </div>
              </div>
            ))
          )}

          {/* Sources Tab */}
          {tab === 'sources' && (sources.length === 0 ? <EmptyState icon="🔌" title="暂无数据源" /> :
            sources.map((s) => (
              <div key={s.key} className="px-6 py-4 hover:bg-slate-800/30 transition-colors">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${s.status === 'active' || s.status === 'online' ? 'bg-emerald-500/10' : s.status === 'error' || s.status === 'failed' ? 'bg-red-500/10' : 'bg-slate-500/10'}`}>
                      {s.status === 'active' || s.status === 'online' ? (
                        <Wifi className="w-4 h-4 text-emerald-400" />
                      ) : (
                        <WifiOff className="w-4 h-4 text-slate-500" />
                      )}
                    </div>
                    <div>
                      <p className="text-sm text-slate-200">{s.name}</p>
                      <p className="text-xs text-slate-500">{s.key}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    {s.health_score !== undefined && (
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-slate-500">健康度</span>
                        <div className="w-16 h-1.5 bg-slate-700/50 rounded-full overflow-hidden">
                          <div className={`h-full rounded-full transition-all ${s.health_score >= 80 ? 'bg-emerald-500' : s.health_score >= 50 ? 'bg-amber-500' : 'bg-red-500'}`}
                            style={{ width: `${s.health_score}%` }} />
                        </div>
                        <span className="text-xs font-mono text-slate-400">{s.health_score}%</span>
                      </div>
                    )}
                    {s.error_count !== undefined && s.error_count > 0 && (
                      <span className="text-xs text-red-400">{s.error_count} 错误</span>
                    )}
                    <StatusBadge status={s.status} />
                  </div>
                </div>
                {/* Source Details */}
                <div className="mt-2 flex items-center gap-4 text-xs text-slate-600">
                  <span>上次检查: {s.last_check || '未知'}</span>
                  {s.last_success && <span>上次成功: {s.last_success}</span>}
                  {s.total_fetched !== undefined && <span>已采集: {s.total_fetched}</span>}
                </div>
              </div>
            ))
          )}
        </div>
      </Card>
    </div>
  )
}
