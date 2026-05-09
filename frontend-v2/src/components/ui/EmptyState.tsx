export function EmptyState({ icon, title, description }: { icon?: string; title: string; description?: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      {icon && <div className="text-3xl mb-3">{icon}</div>}
      <p className="text-sm text-slate-400">{title}</p>
      {description && <p className="text-xs text-slate-600 mt-1">{description}</p>}
    </div>
  )
}
