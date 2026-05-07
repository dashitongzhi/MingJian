import { Activity, Database, Bot, FlaskConical } from 'lucide-react'

const STATS = [
  { label: '运行中智能体', value: '12', change: '+3', icon: Bot, color: 'text-blue-400', bg: 'bg-blue-500/10' },
  { label: '活跃场景', value: '8', change: '+2', icon: FlaskConical, color: 'text-emerald-400', bg: 'bg-emerald-500/10' },
  { label: '证据数据', value: '2,847', change: '+156', icon: Database, color: 'text-violet-400', bg: 'bg-violet-500/10' },
  { label: '系统事件', value: '1,203', change: '+89', icon: Activity, color: 'text-amber-400', bg: 'bg-amber-500/10' },
]

export default function Dashboard() {
  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-slate-100">总览</h1>
        <p className="text-sm text-slate-500 mt-1">MingJian 平台运行状态</p>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
        {STATS.map((s) => (
          <div
            key={s.label}
            className="rounded-xl border border-slate-800 bg-slate-900/40 p-5 hover:border-slate-700 transition-colors"
          >
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs text-slate-500 uppercase tracking-wider">{s.label}</span>
              <div className={`w-8 h-8 rounded-lg ${s.bg} flex items-center justify-center`}>
                <s.icon className={`w-4 h-4 ${s.color}`} />
              </div>
            </div>
            <div className="text-2xl font-bold text-slate-100">{s.value}</div>
            <div className="text-xs text-emerald-400 mt-1">{s.change} 本周</div>
          </div>
        ))}
      </div>

      {/* Quick links */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-6">
          <h3 className="text-sm font-semibold text-slate-300 mb-4">快速操作</h3>
          <div className="space-y-2">
            {['新建辩论场景', '创建智能体', '导入证据'].map((a) => (
              <button
                key={a}
                className="w-full text-left px-4 py-3 rounded-lg border border-slate-800 bg-slate-800/30 text-sm text-slate-400 hover:text-slate-200 hover:bg-slate-800/60 transition-all"
              >
                {a}
              </button>
            ))}
          </div>
        </div>
        <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-6">
          <h3 className="text-sm font-semibold text-slate-300 mb-4">最近活动</h3>
          <div className="space-y-3 text-sm text-slate-500">
            <p>暂无最近活动记录</p>
          </div>
        </div>
      </div>
    </div>
  )
}
