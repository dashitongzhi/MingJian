export function ErrorBanner({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
	    <div className="flex items-center justify-between gap-4 rounded-[20px] border border-red-500/20 bg-red-500/5 px-4 py-3">
      <span className="text-sm text-red-400">{message}</span>
      {onRetry && (
	        <button onClick={onRetry} className="rounded-full border border-red-500/20 px-3 py-1 text-xs text-red-400 transition hover:bg-red-500/10 hover:text-red-300">
          重试
        </button>
      )}
    </div>
  )
}
