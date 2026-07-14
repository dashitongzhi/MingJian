import { useState } from 'react'
import type { FormEvent } from 'react'
import { X } from 'lucide-react'

import { ApiError } from '../api/client'

export function ChangePasswordDialog({
  onClose,
  onSubmit,
}: {
  onClose: () => void
  onSubmit: (currentPassword: string, newPassword: string) => Promise<void>
}) {
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    if (newPassword !== confirmation) {
      setError('两次输入的新密码不一致')
      return
    }

    setSubmitting(true)
    setError('')
    try {
      await onSubmit(currentPassword, newPassword)
    } catch (submitError) {
      setError(
        submitError instanceof ApiError && submitError.status === 400
          ? '当前密码不正确'
          : '密码修改失败，请稍后重试',
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-slate-950/75 px-5 backdrop-blur-sm">
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="change-password-title"
        className="liquid-glass w-full max-w-md p-6"
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 id="change-password-title" className="text-xl font-semibold text-slate-50">修改密码</h2>
            <p className="mt-2 text-sm leading-6 text-slate-400">修改成功后，所有现有会话都会失效，需要重新登录。</p>
          </div>
          <button type="button" onClick={onClose} aria-label="关闭修改密码" className="glass-button grid h-9 w-9 place-items-center">
            <X className="h-4 w-4" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="mt-6 space-y-4">
          <label className="block text-sm text-slate-300">
            当前密码
            <input
              aria-label="当前密码"
              autoComplete="current-password"
              type="password"
              value={currentPassword}
              onChange={(event) => setCurrentPassword(event.target.value)}
              className="glass-input mt-2 h-11 w-full px-3 text-slate-100 focus:outline-none"
              minLength={6}
              required
            />
          </label>
          <label className="block text-sm text-slate-300">
            新密码
            <input
              aria-label="新密码"
              autoComplete="new-password"
              type="password"
              value={newPassword}
              onChange={(event) => setNewPassword(event.target.value)}
              className="glass-input mt-2 h-11 w-full px-3 text-slate-100 focus:outline-none"
              minLength={12}
              required
            />
          </label>
          <label className="block text-sm text-slate-300">
            确认新密码
            <input
              aria-label="确认新密码"
              autoComplete="new-password"
              type="password"
              value={confirmation}
              onChange={(event) => setConfirmation(event.target.value)}
              className="glass-input mt-2 h-11 w-full px-3 text-slate-100 focus:outline-none"
              minLength={12}
              required
            />
          </label>
          {error && <p role="alert" className="text-sm text-rose-300">{error}</p>}
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={onClose} className="glass-button px-4 py-2 text-sm">取消</button>
            <button type="submit" disabled={submitting} className="primary-ink-button px-4 py-2 text-sm font-semibold disabled:opacity-50">
              {submitting ? '修改中…' : '确认修改'}
            </button>
          </div>
        </form>
      </section>
    </div>
  )
}
