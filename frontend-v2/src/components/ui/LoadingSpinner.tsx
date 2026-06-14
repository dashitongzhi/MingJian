export function LoadingSpinner() {
  return (
    <div className="flex items-center justify-center px-6 py-16">
      <div className="w-full max-w-sm space-y-3" aria-label="加载中">
	        <div className="h-3 w-28 animate-pulse rounded-full bg-[var(--color-border-subtle)]" />
	        <div className="h-10 animate-pulse rounded-full bg-[var(--color-bg-surface)]" />
	        <div className="grid grid-cols-3 gap-2">
	          <div className="h-8 animate-pulse rounded-full bg-[var(--color-bg-surface)]" />
	          <div className="h-8 animate-pulse rounded-full bg-[var(--color-bg-surface)]" />
	          <div className="h-8 animate-pulse rounded-full bg-[var(--color-bg-surface)]" />
        </div>
      </div>
    </div>
  )
}
