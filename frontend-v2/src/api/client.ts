const BASE = '/api'
const NETWORK_RETRY_DELAYS_MS = [300, 800, 1500]

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

function isNetworkFailure(error: unknown) {
  return error instanceof TypeError && error.message === 'Failed to fetch'
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const method = (init?.method || 'GET').toUpperCase()
  const retryNetworkFailure = method === 'GET' || method === 'HEAD'
  let lastError: unknown

  for (let attempt = 0; attempt <= NETWORK_RETRY_DELAYS_MS.length; attempt += 1) {
    try {
      const res = await fetch(`${BASE}${path}`, {
        headers: { 'Content-Type': 'application/json', ...init?.headers },
        ...init,
      })

      if (!res.ok) {
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

function filenameFromDisposition(disposition: string | null, fallback: string) {
  if (!disposition) return fallback
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
  if (encoded) return decodeURIComponent(encoded)
  const plain = disposition.match(/filename="?([^"]+)"?/i)?.[1]
  return plain || fallback
}

async function download(path: string, fallbackFilename: string): Promise<void> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) {
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
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'PUT', body: body ? JSON.stringify(body) : undefined }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'PATCH', body: body ? JSON.stringify(body) : undefined }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
  download,
}
