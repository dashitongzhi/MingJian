import { useNavigate, useLocation } from 'react-router-dom'
import {
  LayoutGrid,
  Bot,
  Users,
  MessageSquare,
  FlaskConical,
  Library,
  FileText,
  Settings,
  ChevronLeft,
  ChevronRight,
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
  { label: '智能体管理', icon: Users, path: '/agents' },
  { label: '辩论中心', icon: MessageSquare, path: '/debate' },
  { label: '场景模拟', icon: FlaskConical, path: '/simulation' },
  { label: '证据库', icon: Library, path: '/evidence' },
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
          group relative flex items-center gap-3 w-full rounded-lg px-3 py-2.5
          transition-all duration-200 cursor-pointer
          ${active
            ? 'text-blue-400 bg-blue-500/10 font-semibold'
            : 'text-slate-400 hover:text-slate-100 hover:bg-slate-800/40 font-normal'
          }
        `}
        title={collapsed ? item.label : undefined}
      >
        {active && (
          <div className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-5 bg-blue-400 rounded-r-full" />
        )}
        <item.icon className="w-5 h-5 shrink-0" />
        {!collapsed && (
          <span className="text-sm whitespace-nowrap">{item.label}</span>
        )}
      </button>
    )
  }

  return (
    <aside
      className={`
        fixed left-0 top-0 h-screen flex flex-col
        bg-[#0B0F19] border-r border-slate-800
        transition-all duration-300
        ${collapsed ? 'w-[68px]' : 'w-60'}
      `}
    >
      {/* Logo */}
      <div className="flex items-center justify-between h-16 px-4 border-b border-slate-800/60">
        {!collapsed && (
          <span className="text-xl font-bold tracking-wider text-slate-100 select-none">
            MingJian
          </span>
        )}
        {collapsed && (
          <span className="text-lg font-bold tracking-wider text-slate-100 select-none mx-auto">
            MJ
          </span>
        )}
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="text-slate-500 hover:text-slate-300 transition-colors p-1 rounded hover:bg-slate-800/40"
          title={collapsed ? '展开' : '收起'}
        >
          {collapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
        </button>
      </div>

      {/* Main nav */}
      <nav className="flex-1 flex flex-col gap-1 px-3 pt-4 pb-2 overflow-y-auto">
        {MENU_ITEMS.map(renderMenuItem)}
      </nav>

      {/* Bottom nav */}
      <div className="px-3 pb-4 pt-2 border-t border-slate-800/60">
        {BOTTOM_ITEMS.map(renderMenuItem)}
      </div>
    </aside>
  )
}
