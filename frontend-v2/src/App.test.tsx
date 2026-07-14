import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App'

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
})
