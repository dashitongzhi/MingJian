export function ErrorBanner({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="rounded-lg border border-red-500/20 bg-red-500/5 px-4 py-3 flex items-center justify-between">
      <span className="text-sm text-red-400">{message}</span>
      {onRetry && (
        <button onClick={onRetry} className="text-xs text-red-400 hover:text-red-300 underline">
          重试
        </button>
      )}
    </div>
  )
}
