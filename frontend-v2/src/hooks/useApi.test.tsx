import { act, renderHook, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { useApi, useApiAction } from './useApi'


describe('useApi', () => {
  it('loads again with the latest fetcher when its dependency key changes', async () => {
    const fetcher = vi.fn((key: string) => Promise.resolve(`value-${key}`))
    const { result, rerender } = renderHook(
      ({ keyValue }) => useApi(() => fetcher(keyValue), keyValue),
      { initialProps: { keyValue: 'a' } },
    )

    await waitFor(() => expect(result.current.data).toBe('value-a'))

    rerender({ keyValue: 'b' })

    await waitFor(() => expect(result.current.data).toBe('value-b'))
    expect(fetcher).toHaveBeenCalledWith('a')
    expect(fetcher).toHaveBeenCalledWith('b')
  })

  it('accepts an object dependency using React identity semantics', async () => {
    const firstKey: Record<string, unknown> = {}
    firstKey.self = firstKey
    const secondKey: Record<string, unknown> = {}
    secondKey.self = secondKey
    const fetcher = vi.fn(() => Promise.resolve('loaded'))
    const { result, rerender } = renderHook(
      ({ keyValue }) => useApi(fetcher, keyValue),
      { initialProps: { keyValue: firstKey } },
    )

    await waitFor(() => expect(result.current.data).toBe('loaded'))
    rerender({ keyValue: secondKey })
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2))
  })
})


describe('useApiAction', () => {
  it('executes the latest action after a rerender', async () => {
    const { result, rerender } = renderHook(
      ({ prefix }) => useApiAction((value: string) => Promise.resolve(`${prefix}-${value}`)),
      { initialProps: { prefix: 'first' } },
    )

    rerender({ prefix: 'latest' })

    let response: string | null = null
    await act(async () => {
      response = await result.current.execute('value')
    })

    expect(response).toBe('latest-value')
  })
})
