const BASE = '/api'
const NETWORK_RETRY_DELAYS_MS = [300, 800, 1500]
const AUTH_TOKEN_KEYS = ['mingjian_access_token', 'planagent_access_token', 'auth_token']

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

function isNetworkFailure(error: unknown) {
  return error instanceof TypeError && error.message === 'Failed to fetch'
}

function authToken() {
  for (const key of AUTH_TOKEN_KEYS) {
    const token = window.localStorage.getItem(key)
    if (token) return token
  }
  return ''
}

function requestHeaders(headers?: HeadersInit) {
  const token = authToken()
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...headers,
  }
}

function handleUnauthorized() {
  for (const key of AUTH_TOKEN_KEYS) {
    window.localStorage.removeItem(key)
  }
  window.dispatchEvent(new CustomEvent('mingjian:auth-expired'))
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const method = (init?.method || 'GET').toUpperCase()
  const retryNetworkFailure = method === 'GET' || method === 'HEAD'
  let lastError: unknown

  for (let attempt = 0; attempt <= NETWORK_RETRY_DELAYS_MS.length; attempt += 1) {
    try {
      const res = await fetch(`${BASE}${path}`, {
        headers: requestHeaders(init?.headers),
        ...init,
      })

      if (!res.ok) {
        if (res.status === 401) handleUnauthorized()
        const body = await res.text().catch(() => '')
        throw new Error(`API ${res.status}: ${body}`)
      }

      return res.json()
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
  throw lastError
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'PUT', body: body ? JSON.stringify(body) : undefined }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'PATCH', body: body ? JSON.stringify(body) : undefined }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
}
