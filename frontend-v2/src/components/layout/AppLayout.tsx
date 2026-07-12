import { Outlet } from 'react-router-dom'
import { useState } from 'react'
import type { FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { Bell, ChevronDown, Moon, Plus, Search, Sun } from 'lucide-react'
import Sidebar from './Sidebar'
import { useTheme } from '../../hooks/useTheme'

export default function AppLayout() {
  const navigate = useNavigate()
  const [mode, setMode] = useState<'enterprise' | 'military'>('enterprise')
  const [notificationsOpen, setNotificationsOpen] = useState(false)
  const [userOpen, setUserOpen] = useState(false)
  const [search, setSearch] = useState('')
  const { theme, toggleTheme } = useTheme()

  const handleSearchSubmit = (event: FormEvent) => {
    event.preventDefault()
    const q = search.trim()
    if (q) navigate(`/evidence?search=${encodeURIComponent(q)}`)
  }

  return (
    <div className="app-shell flex min-h-screen text-slate-100">
      <Sidebar />
      <main className="ml-[96px] flex min-h-screen flex-1 flex-col overflow-x-hidden lg:ml-[268px]">
        <header className="app-header sticky top-3 z-30 mx-3 px-3 py-2.5 backdrop-blur-xl lg:mx-5 lg:px-4">
          <div className="flex items-center gap-3">
            <form onSubmit={handleSearchSubmit} className="glass-input flex h-10 min-w-0 flex-1 items-center gap-2 px-3 lg:max-w-[620px]">
              <Search className="h-4 w-4 shrink-0 text-slate-500" />
              <input
                aria-label="全局搜索"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="搜索场景、报告、智能体或证据..."
                className="min-w-0 flex-1 bg-transparent text-sm text-slate-200 placeholder:text-slate-600 focus:outline-none"
              />
              <span className="mono-data hidden rounded-full border border-slate-700/60 px-1.5 py-0.5 text-[10px] text-slate-500 sm:block">⌘K</span>
            </form>

            <div className="hidden items-center rounded-full border border-blue-400/20 bg-blue-500/10 p-1 text-sm lg:flex">
              <button
                type="button"
                onClick={() => setMode('enterprise')}
                className={`rounded-full px-4 py-1.5 transition ${mode === 'enterprise' ? 'segmented-active' : 'text-slate-500 hover:text-slate-200'}`}
              >
                企业
              </button>
              <button
                type="button"
                onClick={() => setMode('military')}
                className={`rounded-full px-4 py-1.5 transition ${mode === 'military' ? 'segmented-active' : 'text-slate-500 hover:text-slate-200'}`}
              >
                军事
              </button>
            </div>

            <button
              type="button"
              onClick={toggleTheme}
              aria-label={theme === 'dark' ? '切换到浅色模式' : '切换到深色模式'}
              aria-pressed={theme === 'light'}
              title={theme === 'dark' ? '切换到浅色模式' : '切换到深色模式'}
              className="theme-toggle-button glass-button grid h-10 w-10 shrink-0 place-items-center"
            >
              {theme === 'dark' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </button>

            <div className="relative">
              <button
                type="button"
                onClick={() => setNotificationsOpen((prev) => !prev)}
                className="glass-button relative grid h-10 w-10 shrink-0 place-items-center text-slate-300"
                aria-label="通知"
              >
                <Bell className="h-4 w-4" />
                <span className="absolute right-1.5 top-1.5 grid h-4 min-w-4 place-items-center rounded-full bg-red-500 px-1 text-[10px] font-bold text-white">3</span>
              </button>
              {notificationsOpen && (
                <div className="liquid-glass absolute right-0 top-12 w-72 p-3">
                  <p className="text-sm font-semibold text-slate-100">通知</p>
                  {['数据源同步完成', '预测序列已更新', '监控规则待确认'].map((item) => (
                    <button
                      key={item}
                      type="button"
                      onClick={() => {
                        setNotificationsOpen(false)
                        navigate('/monitoring')
                      }}
                      className="paper-row mt-2 block w-full px-3 py-2 text-left text-xs text-slate-400 transition hover:bg-blue-500/10 hover:text-blue-100"
                    >
                      {item}
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div className="relative hidden md:block">
              <button
                type="button"
                onClick={() => setUserOpen((prev) => !prev)}
                className="glass-button flex h-10 items-center gap-2 px-3 text-sm text-slate-200"
              >
                <span className="grid h-7 w-7 place-items-center rounded-full bg-slate-200 text-xs font-bold text-slate-900">U</span>
                User
                <ChevronDown className="h-4 w-4 text-slate-500" />
              </button>
              {userOpen && (
                <div className="liquid-glass absolute right-0 top-12 w-44 p-2">
                  <button type="button" onClick={() => { setUserOpen(false); navigate('/settings') }} className="block w-full rounded-[16px] px-3 py-2 text-left text-sm text-slate-300 transition hover:bg-blue-500/10">账户设置</button>
                  <button type="button" onClick={() => { setUserOpen(false); navigate('/dashboard') }} className="block w-full rounded-[16px] px-3 py-2 text-left text-sm text-slate-300 transition hover:bg-blue-500/10">返回总览</button>
                </div>
              )}
            </div>

            <button
              type="button"
              onClick={() => navigate('/ai-assistant')}
              className="primary-ink-button hidden h-10 items-center gap-2 px-4 text-sm font-semibold transition xl:flex"
            >
              新建分析
              <Plus className="h-4 w-4" />
            </button>
          </div>
        </header>
        <div className="w-full px-4 py-6 md:px-6 lg:px-7">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
