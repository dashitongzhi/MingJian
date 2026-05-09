import { Activity, Database, Bot, FlaskConical, Wifi, WifiOff } from 'lucide-react'
import { Card, CardHeader, CardBody } from '../components/ui/Card'
import { EmptyState } from '../components/ui/EmptyState'
import { LoadingSpinner } from '../components/ui/LoadingSpinner'
import { consoleApi, agentsApi, simulationApi, evidenceApi, monitoringApi } from '../api/endpoints'
import { useApi } from '../hooks/useApi'

export default function Dashboard() {
  const { data: health, loading: hLoad } = useApi(() => consoleApi.health())
  const { data: agentsResp, loading: aLoad } = useApi(() => agentsApi.list())
  const { data: simRuns, loading: sLoad } = useApi(() => simulationApi.listRuns())
  const { data: evidenceResp, loading: eLoad } = useApi(() => evidenceApi.list())
  const { data: watchRules, loading: wLoad } = useApi(() => monitoringApi.listWatchRules())

  const loading = hLoad || aLoad || sLoad || eLoad || wLoad
  if (loading) return <LoadingSpinner />

  const agentCount = agentsResp?.agents?.length ?? 0
  const simCount = simRuns?.length ?? 0
  const evCount = evidenceResp?.total ?? 0
  const watchCount = watchRules?.length ?? 0

  const stats = [
    { label: '运行中智能体', value: String(agentCount), icon: Bot, color: 'text-blue-400', bg: 'bg-blue-500/10' },
    { label: '模拟场景', value: String(simCount), icon: FlaskConical, color: 'text-emerald-400', bg: 'bg-emerald-500/10' },
    { label: '证据数据', value: String(evCount), icon: Database, color: 'text-violet-400', bg: 'bg-violet-500/10' },
    { label: '监控规则', value: String(watchCount), icon: Activity, color: 'text-amber-400', bg: 'bg-amber-500/10' },
  ]

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">总览</h1>
          <p className="text-sm text-slate-500 mt-1">MingJian 平台运行状态</p>
        </div>
        {health ? (
          <div className="flex items-center gap-2 text-emerald-400 text-sm"><Wifi className="w-4 h-4" /> 系统在线</div>
        ) : (
          <div className="flex items-center gap-2 text-red-400 text-sm"><WifiOff className="w-4 h-4" /> 离线</div>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
        {stats.map((s) => (
          <Card key={s.label} className="p-5">
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs text-slate-500 uppercase tracking-wider">{s.label}</span>
              <div className={`w-8 h-8 rounded-lg ${s.bg} flex items-center justify-center`}>
                <s.icon className={`w-4 h-4 ${s.color}`} />
              </div>
            </div>
            <div className="text-2xl font-bold text-slate-100">{s.value}</div>
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader title="快速操作" />
          <CardBody className="space-y-2">
            {[
              { label: '新建辩论场景', desc: '启动多智能体辩论，校验决策判断', href: '/debate' },
              { label: '创建智能体', desc: '配置新的自定义智能体', href: '/agents' },
              { label: '运行推演', desc: '执行带分支与对比的情景推演', href: '/simulation' },
              { label: '导入证据', desc: '从多来源采集验证证据', href: '/evidence' },
            ].map((a) => (
              <a key={a.label} href={a.href}
                className="flex items-center justify-between p-3 rounded-lg border border-slate-800 bg-slate-800/20 hover:bg-slate-800/40 transition-colors group">
                <div>
                  <p className="text-sm text-slate-300 group-hover:text-slate-100 transition-colors">{a.label}</p>
                  <p className="text-xs text-slate-600">{a.desc}</p>
                </div>
                <span className="text-slate-600 group-hover:text-slate-400 transition-colors">→</span>
              </a>
            ))}
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="最近活动" />
          <CardBody><EmptyState icon="📋" title="暂无最近活动" description="系统活动将在此处显示" /></CardBody>
        </Card>
      </div>
    </div>
  )
}
