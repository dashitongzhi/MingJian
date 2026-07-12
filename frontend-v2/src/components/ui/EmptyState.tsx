import { Inbox } from 'lucide-react'

export function EmptyState({ icon, title, description }: { icon?: string; title: string; description?: string }) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-16 text-center">
      <div
	        className="mb-4 grid h-10 w-10 place-items-center rounded-[16px] border border-[var(--color-border)] bg-[var(--color-bg-surface)] text-[var(--color-text-tertiary)]"
        aria-hidden="true"
        title={icon}
      >
        <Inbox className="h-5 w-5" />
      </div>
      <p className="text-sm font-medium text-slate-400">{title}</p>
      {description && <p className="editorial-copy mt-1 max-w-sm text-xs leading-5">{description}</p>}
    </div>
  )
}
