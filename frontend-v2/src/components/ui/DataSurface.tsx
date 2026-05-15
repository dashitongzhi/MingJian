import { ChevronDown, ChevronRight } from 'lucide-react'
import { useState } from 'react'
import { Card } from './Card'

export type DataRecord = Record<string, unknown>

export function asArray<T = DataRecord>(value: unknown): T[] {
  if (Array.isArray(value)) return value as T[]
  if (value && typeof value === 'object') {
    const record = value as DataRecord
    for (const key of ['items', 'results', 'data', 'tasks', 'agents', 'predictions', 'watch_rules']) {
      if (Array.isArray(record[key])) return record[key] as T[]
    }
  }
  return []
}

export function asRecord(value: unknown): DataRecord {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as DataRecord : {}
}

export function textValue(value: unknown, fallback = '—') {
  if (typeof value === 'string' && value.trim()) return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return fallback
}

export function titleOf(item: unknown, fallback = '未命名') {
  const record = asRecord(item)
  return textValue(
    record.title ?? record.name ?? record.topic ?? record.label ?? record.statement ?? record.id,
    fallback
  )
}

export function formatDate(value: unknown) {
  if (typeof value !== 'string' || !value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

export function metricNumber(value: unknown) {
  if (typeof value === 'number') return value.toLocaleString()
  if (Array.isArray(value)) return value.length.toLocaleString()
  if (value && typeof value === 'object') return Object.keys(value).length.toLocaleString()
  if (value == null || value === '') return '0'
  return String(value)
}

export function MetricCard({
  label,
  value,
  hint,
  icon,
  tone = 'blue',
}: {
  label: string
  value: unknown
  hint?: string
  icon?: React.ReactNode
  tone?: 'blue' | 'emerald' | 'violet' | 'amber' | 'red' | 'slate'
}) {
  const tones: Record<string, string> = {
    blue: 'text-blue-300 bg-blue-500/12 border-blue-400/20',
    emerald: 'text-emerald-300 bg-emerald-500/12 border-emerald-400/20',
    violet: 'text-violet-300 bg-violet-500/12 border-violet-400/20',
    amber: 'text-amber-300 bg-amber-500/12 border-amber-400/20',
    red: 'text-red-300 bg-red-500/12 border-red-400/20',
    slate: 'text-slate-300 bg-slate-500/12 border-slate-400/20',
  }

  return (
    <Card className="p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-xs uppercase tracking-wide text-slate-500">{label}</p>
          <p className="mt-2 text-3xl font-semibold text-slate-50 blue-text-glow">{metricNumber(value)}</p>
          {hint && <p className="mt-1 truncate text-xs text-slate-500">{hint}</p>}
        </div>
        {icon && <div className={`grid h-10 w-10 shrink-0 place-items-center rounded-lg border ${tones[tone]}`}>{icon}</div>}
      </div>
    </Card>
  )
}

export function ProgressBar({ value, tone = 'blue' }: { value?: number | null; tone?: 'blue' | 'emerald' | 'violet' | 'amber' | 'red' }) {
  const pct = Math.max(0, Math.min(100, Math.round((value ?? 0) * ((value ?? 0) <= 1 ? 100 : 1))))
  const colors = {
    blue: 'bg-blue-500',
    emerald: 'bg-emerald-500',
    violet: 'bg-violet-500',
    amber: 'bg-amber-500',
    red: 'bg-red-500',
  }
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-800/80">
      <div className={`h-full rounded-full ${colors[tone]}`} style={{ width: `${pct}%` }} />
    </div>
  )
}

export function JsonBlock({ value }: { value: unknown }) {
  return (
    <pre className="max-h-72 overflow-auto rounded-lg border border-slate-800/70 bg-slate-950/45 p-3 text-xs leading-5 text-slate-400">
      {JSON.stringify(value, null, 2)}
    </pre>
  )
}

export function ExpandableRecord({ item, eyebrow }: { item: unknown; eyebrow?: string }) {
  const [open, setOpen] = useState(false)
  const record = asRecord(item)
  const title = titleOf(item)
  const summary = textValue(record.summary ?? record.description ?? record.body_text ?? record.content ?? record.query, '')

  return (
    <div className="border-b border-slate-800/50 last:border-b-0">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        className="flex w-full items-start justify-between gap-4 px-5 py-4 text-left transition hover:bg-blue-500/6"
      >
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            {eyebrow && <span className="rounded border border-blue-400/18 bg-blue-500/10 px-2 py-0.5 text-[11px] text-blue-300">{eyebrow}</span>}
            <p className="truncate text-sm font-medium text-slate-100">{title}</p>
          </div>
          {summary && <p className="mt-1 line-clamp-2 text-xs leading-5 text-slate-500">{summary}</p>}
          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-slate-600">
            {textValue(record.status, '') && <span>状态 {textValue(record.status)}</span>}
            {textValue(record.created_at ?? record.updated_at, '') && <span>{formatDate(record.created_at ?? record.updated_at)}</span>}
            {textValue(record.source ?? record.domain_id ?? record.trigger_type, '') && <span>{textValue(record.source ?? record.domain_id ?? record.trigger_type)}</span>}
          </div>
        </div>
        {open ? <ChevronDown className="mt-1 h-4 w-4 shrink-0 text-slate-500" /> : <ChevronRight className="mt-1 h-4 w-4 shrink-0 text-slate-500" />}
      </button>
      {open && (
        <div className="px-5 pb-5">
          <JsonBlock value={item} />
        </div>
      )}
    </div>
  )
}
