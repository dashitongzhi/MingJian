const STYLES: Record<string, string> = {
  active: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  running: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  completed: 'bg-slate-500/10 text-slate-400 border-slate-500/20',
  pending: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  failed: 'bg-red-500/10 text-red-400 border-red-500/20',
  error: 'bg-red-500/10 text-red-400 border-red-500/20',
  accepted: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  rejected: 'bg-red-500/10 text-red-400 border-red-500/20',
  verified: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  refuted: 'bg-red-500/10 text-red-400 border-red-500/20',
  online: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  offline: 'bg-slate-500/10 text-slate-500 border-slate-500/20',
}

export function StatusBadge({ status }: { status?: string | null }) {
  if (!status) return null
  const s = status.toLowerCase()
  const style = STYLES[s] || 'bg-slate-500/10 text-slate-400 border-slate-500/20'
  return (
	    <span className={`mono-data inline-flex items-center rounded-full border px-2.5 py-0.5 text-[11px] font-medium ${style}`}>
      {status}
    </span>
  )
}
