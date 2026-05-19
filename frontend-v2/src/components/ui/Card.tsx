export function Card({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`cockpit-panel rounded-lg ${className}`}>
      {children}
    </div>
  )
}

export function CardHeader({ title, action }: { title: string; action?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 px-5 py-4 border-b border-[rgba(148,163,184,0.12)]">
      <h3 className="min-w-0 text-sm font-semibold text-slate-100 truncate">{title}</h3>
      {action}
    </div>
  )
}

export function CardBody({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return <div className={`px-5 py-4 ${className}`}>{children}</div>
}
