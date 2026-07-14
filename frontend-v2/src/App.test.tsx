import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, useLocation, useNavigate } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App'

function RouterProbe() {
  const location = useLocation()
  const navigate = useNavigate()
  return (
    <div>
      <output data-testid="route-search">{location.search}</output>
      <button type="button" onClick={() => navigate(-1)}>back</button>
    </div>
  )
}

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('Community application routes', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('renders the 24-hour Monitoring page at /monitoring', async () => {
    vi.spyOn(window, 'fetch').mockImplementation(async (input) => {
      if (String(input) === '/api/console') {
        return new Response('<html></html>', { status: 200 })
      }
      if (String(input) === '/api/watch/rules' || String(input) === '/api/source-changes') {
        return jsonResponse([])
      }
      return jsonResponse({})
    })

    render(
      <MemoryRouter initialEntries={['/monitoring']}>
        <App />
      </MemoryRouter>,
    )

    expect(await screen.findByRole('heading', { name: '监控中心' })).toBeInTheDocument()
    expect(screen.getByText('24 小时窗口')).toBeInTheDocument()
  })

  it('keeps the active assistant session in the URL across selection and history navigation', async () => {
    vi.spyOn(window, 'fetch').mockImplementation(async (input) => {
      const url = String(input)
      if (url === '/api/console') return new Response('<html></html>', { status: 200 })
      if (url === '/api/assistant/sessions') {
        return jsonResponse([
          { id: 'one', title: 'Session one', created_at: '2026-07-14T00:00:00Z' },
          { id: 'two', title: 'Session two', created_at: '2026-07-14T01:00:00Z' },
        ])
      }
      if (url.startsWith('/api/assistant/sessions/')) {
        const id = url.split('/').at(-1)
        return jsonResponse({ id, title: `Session ${id}`, messages: [], recent_runs: [] })
      }
      if (url.includes('/recommendations') || url.startsWith('/api/decisions?')) {
        return jsonResponse([])
      }
      return jsonResponse({})
    })

    render(
      <MemoryRouter initialEntries={['/ai-assistant?session=one&view=compact']}>
        <App />
        <RouterProbe />
      </MemoryRouter>,
    )

    expect(await screen.findByRole('heading', { name: 'AI 助手' })).toBeInTheDocument()
    expect(screen.getByTestId('route-search')).toHaveTextContent('?session=one&view=compact')

    fireEvent.click(screen.getByRole('button', { name: /Session two/ }))
    await waitFor(() => {
      expect(screen.getByTestId('route-search')).toHaveTextContent('?session=two&view=compact')
    })

    fireEvent.click(screen.getByRole('button', { name: 'back' }))
    await waitFor(() => {
      expect(screen.getByTestId('route-search')).toHaveTextContent('?session=one&view=compact')
    })
  })
})
