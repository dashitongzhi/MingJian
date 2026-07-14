import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import userEvent from '@testing-library/user-event'

import { AuthGate } from './AuthGate'
import { AUTH_TOKEN_KEYS, REFRESH_TOKEN_KEYS } from '../lib/auth'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('Community access gate', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('opens the workspace without a login prompt when the local access probe succeeds', async () => {
    vi.spyOn(window, 'fetch').mockResolvedValue(new Response('<html></html>', { status: 200 }))

    render(
      <AuthGate>
        <div>Community workspace</div>
      </AuthGate>,
    )

    expect(await screen.findByText('Community workspace')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: '登录明鉴 Community' })).not.toBeInTheDocument()
  })

  it('shows bootstrap admin login after a remote 401 and stores the authenticated session', async () => {
    const user = userEvent.setup()
    const fetchMock = vi.spyOn(window, 'fetch')
      .mockResolvedValueOnce(jsonResponse({ detail: 'Missing Authorization header' }, 401))
      .mockResolvedValueOnce(jsonResponse({
        access_token: 'access-token',
        refresh_token: 'refresh-token',
        token_type: 'bearer',
        expires_in: 900,
      }))

    render(
      <AuthGate>
        <div>Community workspace</div>
      </AuthGate>,
    )

    expect(await screen.findByRole('heading', { name: '登录明鉴 Community' })).toBeInTheDocument()
    await user.type(screen.getByLabelText('密码'), 'bootstrap-password')
    await user.click(screen.getByRole('button', { name: '登录' }))

    expect(await screen.findByText('Community workspace')).toBeInTheDocument()
    for (const key of AUTH_TOKEN_KEYS) expect(window.localStorage.getItem(key)).toBe('access-token')
    for (const key of REFRESH_TOKEN_KEYS) expect(window.localStorage.getItem(key)).toBe('refresh-token')

    const loginRequest = fetchMock.mock.calls[1]
    expect(loginRequest[0]).toBe('/api/auth/login')
    expect(new Headers(loginRequest[1]?.headers).has('Authorization')).toBe(false)
  })
})
