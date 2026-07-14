import { useCallback, useEffect, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'

import { api, ApiError } from '../api/client'
import { LoadingSpinner } from '../components/ui/LoadingSpinner'
import { clearAuthTokens, readAuthToken, storeAuthTokens } from '../lib/auth'
import { AuthContext } from './AuthContext'
import type { AuthContextValue } from './AuthContext'

type TokenResponse = {
  access_token: string
  refresh_token: string
}

type UserInfo = {
  username: string
}

type AuthSession = {
  mode: 'local' | 'remote'
  username: string
}

type AccessState =
  | { status: 'checking' }
  | { status: 'ready'; session: AuthSession }
  | { status: 'login-required' }
  | { status: 'error' }

function LoginPanel({ onLogin }: { onLogin: (username: string, password: string) => Promise<void> }) {
  const [username, setUsername] = useState('admin')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setSubmitting(true)
    setError('')
    try {
      await onLogin(username.trim(), password)
    } catch (loginError) {
      setError(
        loginError instanceof ApiError && loginError.status === 401
          ? '用户名或密码错误'
          : '登录失败，请确认服务状态后重试',
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="app-shell grid min-h-screen place-items-center px-5 py-10 text-slate-100">
      <section className="cockpit-hero w-full max-w-md px-6 py-7 md:px-8">
        <p className="cockpit-kicker">Remote Community Access</p>
        <h1 className="mt-3 text-3xl font-semibold text-slate-50">登录明鉴 Community</h1>
        <p className="mt-3 text-sm leading-6 text-slate-400">
          当前实例启用了远程访问，请使用部署时配置的 bootstrap admin 凭据登录。
        </p>

        <form className="mt-7 space-y-4" onSubmit={handleSubmit}>
          <label className="block text-sm text-slate-300">
            用户名
            <input
              aria-label="用户名"
              autoComplete="username"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              className="glass-input mt-2 h-11 w-full px-3 text-slate-100 focus:outline-none"
              required
            />
          </label>
          <label className="block text-sm text-slate-300">
            密码
            <input
              aria-label="密码"
              autoComplete="current-password"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="glass-input mt-2 h-11 w-full px-3 text-slate-100 focus:outline-none"
              required
            />
          </label>
          {error && <p role="alert" className="text-sm text-rose-300">{error}</p>}
          <button
            type="submit"
            disabled={submitting}
            className="primary-ink-button h-11 w-full px-4 text-sm font-semibold disabled:opacity-50"
          >
            {submitting ? '登录中…' : '登录'}
          </button>
        </form>

        <p className="mt-5 text-xs leading-5 text-slate-500">
          会话令牌仅保存在当前浏览器的 localStorage 中，不会写入 URL 或前端日志。
        </p>
      </section>
    </main>
  )
}

export function AuthGate({ children }: { children: ReactNode }) {
  const [accessState, setAccessState] = useState<AccessState>({ status: 'checking' })

  const checkAccess = useCallback(async () => {
    try {
      await api.probe('/console', { authenticated: false })
      clearAuthTokens()
      setAccessState({ status: 'ready', session: { mode: 'local', username: '本地用户' } })
      return
    } catch (error) {
      if (!(error instanceof ApiError) || error.status !== 401) {
        setAccessState({ status: 'error' })
        return
      }
    }

    if (!readAuthToken()) {
      setAccessState({ status: 'login-required' })
      return
    }

    try {
      await api.probe('/console')
      const user = await api.get<UserInfo>('/auth/me')
      setAccessState({
        status: 'ready',
        session: { mode: 'remote', username: user.username },
      })
    } catch {
      clearAuthTokens()
      setAccessState({ status: 'login-required' })
    }
  }, [])

  useEffect(() => {
    const handleExpired = () => {
      clearAuthTokens()
      setAccessState({ status: 'login-required' })
    }
    window.addEventListener('mingjian:auth-expired', handleExpired)
    const initialCheck = window.setTimeout(() => void checkAccess(), 0)

    return () => {
      window.clearTimeout(initialCheck)
      window.removeEventListener('mingjian:auth-expired', handleExpired)
    }
  }, [checkAccess])

  const login = useCallback(async (username: string, password: string) => {
    const tokens = await api.post<TokenResponse>('/auth/login', { username, password })
    if (!tokens.access_token || !tokens.refresh_token) {
      throw new Error('Authentication response did not include both session tokens')
    }
    storeAuthTokens(tokens.access_token, tokens.refresh_token)
    setAccessState({ status: 'ready', session: { mode: 'remote', username } })
  }, [])

  const logout = useCallback(async () => {
    await api.post('/auth/logout').catch(() => undefined)
    clearAuthTokens()
    setAccessState({ status: 'login-required' })
  }, [])

  const changePassword = useCallback(async (currentPassword: string, newPassword: string) => {
    await api.post('/auth/change-password', {
      current_password: currentPassword,
      new_password: newPassword,
    })
    clearAuthTokens()
    setAccessState({ status: 'login-required' })
  }, [])

  if (accessState.status === 'checking') return <LoadingSpinner />
  if (accessState.status === 'login-required') return <LoginPanel onLogin={login} />
  if (accessState.status === 'error') {
    return (
      <main className="app-shell grid min-h-screen place-items-center px-5 text-slate-100">
        <div className="cockpit-hero max-w-lg px-6 py-7 text-center">
          <p role="alert">无法连接到明鉴服务，请确认后端已启动后重试。</p>
          <button
            type="button"
            onClick={() => {
              setAccessState({ status: 'checking' })
              void checkAccess()
            }}
            className="glass-button mt-5 px-4 py-2 text-sm"
          >
            重新检查
          </button>
        </div>
      </main>
    )
  }

  const contextValue: AuthContextValue = { ...accessState.session, logout, changePassword }
  return <AuthContext.Provider value={contextValue}>{children}</AuthContext.Provider>
}
