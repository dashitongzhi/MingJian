import { Outlet } from 'react-router-dom'
import { useState } from 'react'
import type { FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { ChevronDown, KeyRound, LogOut, Moon, Plus, Search, Sun } from 'lucide-react'
import Sidebar from './Sidebar'
import { useTheme } from '../../hooks/useTheme'
import { useAuth } from '../../auth/AuthContext'
import { ChangePasswordDialog } from '../../auth/ChangePasswordDialog'

export default function AppLayout() {
  const navigate = useNavigate()
  const [userOpen, setUserOpen] = useState(false)
  const [passwordOpen, setPasswordOpen] = useState(false)
  const [search, setSearch] = useState('')
  const { theme, toggleTheme } = useTheme()
  const { mode, username, logout, changePassword } = useAuth()
  const userInitial = username.trim().charAt(0).toUpperCase() || 'U'

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
                onClick={() => setUserOpen((prev) => !prev)}
                aria-label={`用户菜单 ${username}`}
                aria-expanded={userOpen}
                className="glass-button flex h-10 items-center gap-2 px-3 text-sm text-slate-200"
              >
                <span className="grid h-7 w-7 place-items-center rounded-full bg-slate-200 text-xs font-bold text-slate-900">{userInitial}</span>
                <span className="hidden sm:inline">{username}</span>
                <ChevronDown className="h-4 w-4 text-slate-500" />
              </button>
              {userOpen && (
                <div className="liquid-glass absolute right-0 top-12 w-44 p-2">
                  <button type="button" onClick={() => { setUserOpen(false); navigate('/dashboard') }} className="block w-full rounded-[16px] px-3 py-2 text-left text-sm text-slate-300 transition hover:bg-blue-500/10">返回总览</button>
                  {mode === 'remote' && (
                    <>
                      <button
                        type="button"
                        onClick={() => {
                          setUserOpen(false)
                          setPasswordOpen(true)
                        }}
                        className="flex w-full items-center gap-2 rounded-[16px] px-3 py-2 text-left text-sm text-slate-300 transition hover:bg-blue-500/10"
                      >
                        <KeyRound className="h-4 w-4" />
                        修改密码
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setUserOpen(false)
                          void logout()
                        }}
                        className="flex w-full items-center gap-2 rounded-[16px] px-3 py-2 text-left text-sm text-rose-200 transition hover:bg-rose-500/10"
                      >
                        <LogOut className="h-4 w-4" />
                        退出登录
                      </button>
                    </>
                  )}
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
      {passwordOpen && mode === 'remote' && (
        <ChangePasswordDialog
          onClose={() => setPasswordOpen(false)}
          onSubmit={changePassword}
        />
      )}
    </div>
  )
}
