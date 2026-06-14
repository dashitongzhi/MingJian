export function Card({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
	    <section className={`cockpit-panel ${className}`}>
      {children}
    </section>
  )
}

export function CardHeader({ title, action }: { title: string; action?: React.ReactNode }) {
  return (
	    <div className="flex items-center justify-between gap-4 border-b border-[var(--color-border-subtle)] px-5 py-4">
      <h3 className="min-w-0 truncate text-sm font-semibold text-slate-100">{title}</h3>
      {action}
    </div>
  )
}

export function CardBody({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return <div className={`px-5 py-4 ${className}`}>{children}</div>
}
