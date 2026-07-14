import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Outlet, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AuthGate } from '../../auth/AuthGate'
import AppLayout from './AppLayout'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function Workspace() {
  return <Outlet />
}

function renderLayout() {
  render(
    <MemoryRouter>
      <AuthGate>
        <Routes>
          <Route element={<Workspace />}>
            <Route element={<AppLayout />}>
              <Route index element={<div>Community workspace</div>} />
            </Route>
          </Route>
        </Routes>
      </AuthGate>
    </MemoryRouter>,
  )
}

describe('authenticated Community layout', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('labels loopback access as local and hides remote account actions', async () => {
    const user = userEvent.setup()
    vi.spyOn(window, 'fetch').mockResolvedValue(new Response('<html></html>', { status: 200 }))

    renderLayout()

    await user.click(await screen.findByRole('button', { name: /本地用户/ }))
    expect(screen.queryByRole('button', { name: '修改密码' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '退出登录' })).not.toBeInTheDocument()
  })

  it('shows the remote username and returns to login after logout', async () => {
    const user = userEvent.setup()
    vi.spyOn(window, 'fetch')
      .mockResolvedValueOnce(jsonResponse({ detail: 'Missing Authorization header' }, 401))
      .mockResolvedValueOnce(jsonResponse({
        access_token: 'access-token',
        refresh_token: 'refresh-token',
        token_type: 'bearer',
        expires_in: 900,
      }))
      .mockResolvedValueOnce(jsonResponse({ message: 'Logged out successfully' }))

    renderLayout()
    await user.type(await screen.findByLabelText('密码'), 'bootstrap-password')
    await user.click(screen.getByRole('button', { name: '登录' }))

    await user.click(await screen.findByRole('button', { name: /admin/ }))
    await user.click(screen.getByRole('button', { name: '退出登录' }))

    expect(await screen.findByRole('heading', { name: '登录明鉴 Community' })).toBeInTheDocument()
    expect(window.localStorage.getItem('mingjian_access_token')).toBeNull()
  })

  it('rotates the remote password and requires a fresh login', async () => {
    const user = userEvent.setup()
    const fetchMock = vi.spyOn(window, 'fetch')
      .mockResolvedValueOnce(jsonResponse({ detail: 'Missing Authorization header' }, 401))
      .mockResolvedValueOnce(jsonResponse({
        access_token: 'access-token',
        refresh_token: 'refresh-token',
        token_type: 'bearer',
        expires_in: 900,
      }))
      .mockResolvedValueOnce(jsonResponse({ message: 'Password changed successfully' }))

    renderLayout()
    await user.type(await screen.findByLabelText('密码'), 'bootstrap-password')
    await user.click(screen.getByRole('button', { name: '登录' }))
    await user.click(await screen.findByRole('button', { name: /admin/ }))
    await user.click(screen.getByRole('button', { name: '修改密码' }))

    await user.type(screen.getByLabelText('当前密码'), 'bootstrap-password')
    await user.type(screen.getByLabelText('新密码'), 'new-password-12345')
    await user.type(screen.getByLabelText('确认新密码'), 'new-password-12345')
    await user.click(screen.getByRole('button', { name: '确认修改' }))

    expect(await screen.findByRole('heading', { name: '登录明鉴 Community' })).toBeInTheDocument()
    expect(fetchMock.mock.calls[2][0]).toBe('/api/auth/change-password')
    expect(JSON.parse(String(fetchMock.mock.calls[2][1]?.body))).toEqual({
      current_password: 'bootstrap-password',
      new_password: 'new-password-12345',
    })
    expect(new Headers(fetchMock.mock.calls[2][1]?.headers).get('Authorization')).toBe('Bearer access-token')
  })
})
