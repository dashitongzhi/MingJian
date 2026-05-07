export default function Placeholder({ title }: { title: string }) {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] text-center">
      <div className="w-16 h-16 rounded-2xl bg-slate-800/60 border border-slate-700/50 flex items-center justify-center mb-6">
        <span className="text-2xl">🚧</span>
      </div>
      <h1 className="text-xl font-bold text-slate-200 mb-2">{title}</h1>
      <p className="text-sm text-slate-500 max-w-xs">
        该模块正在开发中，敬请期待。
      </p>
    </div>
  )
}
