import { clearAuthTokens, readAuthToken, readRefreshToken, storeAuthTokens } from '../lib/auth'

const BASE = '/api'
const REQUEST_TIMEOUT_MS = 30_000
const NETWORK_RETRY_DELAYS_MS = [300, 800, 1500]

type TokenRefreshResponse = {
  access_token: string
  refresh_token: string
}

export class ApiError extends Error {
  status: number

  constructor(status: number, body: string) {
    super(`API ${status}: ${body}`)
    this.name = 'ApiError'
    this.status = status
  }
}

let refreshSessionPromise: Promise<boolean> | null = null

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

function isNetworkFailure(error: unknown) {
  return error instanceof TypeError && error.message === 'Failed to fetch'
}

function isAbortFailure(error: unknown) {
  return error instanceof DOMException && error.name === 'AbortError'
}

async function fetchWithTimeout(input: RequestInfo | URL, init?: RequestInit) {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)
  const upstreamSignal = init?.signal

  if (upstreamSignal?.aborted) {
    controller.abort()
  }

  const abortFromUpstream = () => controller.abort()
  upstreamSignal?.addEventListener('abort', abortFromUpstream, { once: true })

  try {
    return await fetch(input, {
      ...init,
      signal: controller.signal,
    })
  } finally {
    window.clearTimeout(timeout)
    upstreamSignal?.removeEventListener('abort', abortFromUpstream)
  }
}

function requestHeaders(headers?: HeadersInit, includeAuth = true) {
  const merged = new Headers(headers)
  if (!merged.has('Content-Type')) merged.set('Content-Type', 'application/json')
  const token = includeAuth ? readAuthToken() : ''
  if (token) merged.set('Authorization', `Bearer ${token}`)
  return merged
}

function isPublicAuthRequest(path: string) {
  return path === '/auth/login' || path === '/auth/refresh' || path === '/auth/register'
}

function expireAuthSession() {
  clearAuthTokens()
  window.dispatchEvent(new CustomEvent('mingjian:auth-expired'))
}

async function refreshAuthSession() {
  const refreshToken = readRefreshToken()
  if (!refreshToken) return false

  if (!refreshSessionPromise) {
    refreshSessionPromise = (async () => {
      const res = await fetchWithTimeout(`${BASE}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken }),
      })

      if (!res.ok) return false

      const body = (await res.json()) as TokenRefreshResponse
      if (!body.access_token || !body.refresh_token) return false
      storeAuthTokens(body.access_token, body.refresh_token)
      return true
    })().finally(() => {
      refreshSessionPromise = null
    })
  }

  return refreshSessionPromise
}

async function requestResponse(path: string, init?: RequestInit): Promise<Response> {
  const method = (init?.method || 'GET').toUpperCase()
  const retryNetworkFailure = method === 'GET' || method === 'HEAD'
  const publicAuthRequest = isPublicAuthRequest(path)
  let authRetryAvailable = !publicAuthRequest
  let lastError: unknown

  for (let attempt = 0; attempt <= NETWORK_RETRY_DELAYS_MS.length; attempt += 1) {
    try {
      const res = await fetchWithTimeout(`${BASE}${path}`, {
        ...init,
        headers: requestHeaders(init?.headers, !publicAuthRequest),
      })

      if (!res.ok) {
        if (res.status === 401 && !publicAuthRequest && authRetryAvailable) {
          authRetryAvailable = false
          const refreshed = await refreshAuthSession()
          if (refreshed) {
            attempt -= 1
            continue
          }
          expireAuthSession()
        } else if (res.status === 401 && !publicAuthRequest) {
          expireAuthSession()
        }
        const body = await res.text().catch(() => '')
        throw new ApiError(res.status, body)
      }

      return res
    } catch (error) {
      lastError = error
      const canRetry = retryNetworkFailure && isNetworkFailure(error) && attempt < NETWORK_RETRY_DELAYS_MS.length
      if (!canRetry) break
      await sleep(NETWORK_RETRY_DELAYS_MS[attempt])
    }
  }

  if (isNetworkFailure(lastError)) {
    throw new Error('网络连接失败，请确认后端服务已启动后重试')
  }
  if (isAbortFailure(lastError)) {
    throw new Error('请求超时，请稍后重试')
  }
  throw lastError
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await requestResponse(path, init)
  return res.json()
}

function filenameFromDisposition(disposition: string | null, fallback: string) {
  if (!disposition) return fallback
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
  if (encoded) return decodeURIComponent(encoded)
  const plain = disposition.match(/filename="?([^"]+)"?/i)?.[1]
  return plain || fallback
}

async function download(path: string, fallbackFilename: string): Promise<void> {
  let res = await fetchWithTimeout(`${BASE}${path}`, { headers: requestHeaders() })
  if (res.status === 401) {
    const refreshed = await refreshAuthSession()
    if (refreshed) {
      res = await fetchWithTimeout(`${BASE}${path}`, { headers: requestHeaders() })
    } else {
      expireAuthSession()
    }
  }
  if (!res.ok) {
    if (res.status === 401) expireAuthSession()
    const body = await res.text().catch(() => '')
    throw new Error(`API ${res.status}: ${body}`)
  }
  const blob = await res.blob()
  const filename = filenameFromDisposition(res.headers.get('Content-Disposition'), fallbackFilename)
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.URL.revokeObjectURL(url)
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  probe: async (path: string, options?: { authenticated?: boolean }) => {
    if (options?.authenticated === false) {
      const res = await fetchWithTimeout(`${BASE}${path}`, {
        headers: requestHeaders(undefined, false),
      })
      if (!res.ok) {
        const body = await res.text().catch(() => '')
        throw new ApiError(res.status, body)
      }
      return
    }
    await requestResponse(path)
  },
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'PUT', body: body ? JSON.stringify(body) : undefined }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'PATCH', body: body ? JSON.stringify(body) : undefined }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
  download,
}
