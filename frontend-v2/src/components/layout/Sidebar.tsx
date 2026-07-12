import { useNavigate, useLocation } from 'react-router-dom'
import {
  Activity,
  Bot,
  BriefcaseBusiness,
  ChevronLeft,
  ChevronRight,
  Database,
  FileText,
  FlaskConical,
  Gauge,
  LayoutGrid,
  Library,
  MessageSquare,
  Radio,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  Users,
  type LucideIcon,
} from 'lucide-react'
import { useState } from 'react'

interface MenuItem {
  label: string
  icon: LucideIcon
  path: string
}

const MENU_ITEMS: MenuItem[] = [
  { label: '总览', icon: LayoutGrid, path: '/dashboard' },
  { label: 'AI 助手', icon: Bot, path: '/ai-assistant' },
  { label: '工作台', icon: BriefcaseBusiness, path: '/workbench' },
  { label: '智能体管理', icon: Users, path: '/agents' },
  { label: '辩论中心', icon: MessageSquare, path: '/debate' },
  { label: '场景模拟', icon: FlaskConical, path: '/simulation' },
  { label: '证据库', icon: Library, path: '/evidence' },
  { label: '24小时监控', icon: Activity, path: '/monitoring' },
  { label: '数据源', icon: Database, path: '/sources' },
  { label: '报告中心', icon: FileText, path: '/reports' },
]

const BOTTOM_ITEMS: MenuItem[] = [
  { label: '设置', icon: Settings, path: '/settings' },
]

export default function Sidebar() {
  const navigate = useNavigate()
  const location = useLocation()
  const [collapsed, setCollapsed] = useState(false)

  const isActive = (path: string) => location.pathname === path

  const renderMenuItem = (item: MenuItem) => {
    const active = isActive(item.path)
    return (
      <button
        key={item.path}
        onClick={() => navigate(item.path)}
        className={`
          group relative flex items-center gap-3 w-full rounded-[18px] px-3 py-2.5
          transition-all duration-200 cursor-pointer
          ${active
            ? 'nav-item-active font-semibold'
            : 'text-slate-400 hover:text-slate-100 hover:bg-blue-500/8 font-normal'
          }
        `}
        title={collapsed ? item.label : undefined}
      >
        {active && (
          <div className="absolute left-0 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-r-full bg-[var(--color-accent)]" />
        )}
        <item.icon className="w-5 h-5 shrink-0" />
        {!collapsed && (
          <span className="hidden text-sm whitespace-nowrap lg:inline">{item.label}</span>
        )}
      </button>
    )
  }

  return (
    <aside
      className={`
        app-sidebar fixed z-40 flex flex-col
        left-3 top-3 bottom-3 h-auto overflow-hidden border backdrop-blur-xl
        transition-all duration-300
        ${collapsed ? 'w-[76px]' : 'w-[76px] lg:w-[248px]'}
      `}
    >
      {/* Logo */}
      <div className="mx-3 mt-3 flex h-[58px] items-center justify-between rounded-[22px] border border-[var(--color-border-subtle)] bg-white/[0.035] px-3">
        {!collapsed && (
          <div className="flex min-w-0 items-center gap-3">
            <div className="grid h-9 w-9 place-items-center rounded-[16px] border border-blue-400/30 bg-blue-500/12 text-blue-200 shadow-[var(--shadow-interactive)]">
              <ShieldCheck className="h-5 w-5" />
            </div>
            <div className="hidden min-w-0 lg:block">
              <div className="truncate text-lg font-semibold tracking-normal text-slate-50">明鉴 <span className="text-sm font-semibold text-slate-400">MingJian</span></div>
              <div className="editorial-copy text-[11px]">Strategic Intelligence</div>
            </div>
          </div>
        )}
        {collapsed && (
          <div className="mx-auto grid h-9 w-9 place-items-center rounded-[16px] border border-blue-400/30 bg-blue-500/12 text-blue-200">
            <ShieldCheck className="h-5 w-5" />
          </div>
        )}
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="rounded-full p-1 text-slate-500 transition-colors hover:bg-blue-500/10 hover:text-slate-300"
          title={collapsed ? '展开' : '收起'}
        >
          {collapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
        </button>
      </div>

      {/* Main nav */}
      <nav className="flex flex-1 flex-col gap-1 overflow-y-auto px-3 pb-2 pt-4">
        {MENU_ITEMS.map(renderMenuItem)}
      </nav>

      {!collapsed && (
        <div className="paper-row mx-3 mb-3 hidden p-4 lg:block">
          <div className="flex items-center gap-2 text-sm text-emerald-300">
            <span className="h-2.5 w-2.5 rounded-full bg-emerald-400" />
            系统状态
          </div>
          <p className="mt-1 text-xs text-slate-500">正常运行 · 所有系统健康</p>
          <div className="mt-3 grid grid-cols-3 gap-2 text-center text-[11px] text-slate-500">
            <div className="rounded-[14px] border border-slate-800/80 bg-slate-950/28 py-2"><Gauge className="mx-auto mb-1 h-3.5 w-3.5 text-blue-300" />控制</div>
            <div className="rounded-[14px] border border-slate-800/80 bg-slate-950/28 py-2"><Radio className="mx-auto mb-1 h-3.5 w-3.5 text-emerald-300" />同步</div>
            <div className="rounded-[14px] border border-slate-800/80 bg-slate-950/28 py-2"><SlidersHorizontal className="mx-auto mb-1 h-3.5 w-3.5 text-violet-300" />配置</div>
          </div>
        </div>
      )}

      {/* Bottom nav */}
      <div className="px-3 pb-4 pt-2">
        {BOTTOM_ITEMS.map(renderMenuItem)}
      </div>
    </aside>
  )
}
