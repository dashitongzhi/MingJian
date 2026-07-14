import { useState, useEffect, useCallback, useRef } from 'react'

export function useApi<T>(fetcher: () => Promise<T>, dependency?: unknown) {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const fetcherRef = useRef(fetcher)

  useEffect(() => {
    fetcherRef.current = fetcher
  }, [fetcher])

  const reload = useCallback(() => {
    setLoading(true)
    setError(null)
    fetcherRef.current()
      .then(setData)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    let active = true

    const load = async () => {
      await Promise.resolve()
      if (!active) return
      setLoading(true)
      setError(null)
      try {
        const result = await fetcherRef.current()
        if (active) setData(result)
      } catch (e: unknown) {
        if (active) setError(e instanceof Error ? e.message : String(e))
      } finally {
        if (active) setLoading(false)
      }
    }

    void load()
    return () => {
      active = false
    }
  }, [dependency])

  return { data, loading, error, reload }
}

export function useApiAction<T, A extends unknown[]>(
  action: (...args: A) => Promise<T>
) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const actionRef = useRef(action)

  useEffect(() => {
    actionRef.current = action
  }, [action])

  const execute = useCallback(async (...args: A): Promise<T | null> => {
    setLoading(true)
    setError(null)
    try {
      const result = await actionRef.current(...args)
      return result
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
      return null
    } finally {
      setLoading(false)
    }
  }, [])

  return { execute, loading, error }
}
