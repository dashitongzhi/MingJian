export const AUTH_TOKEN_KEYS = ['mingjian_access_token', 'planagent_access_token', 'auth_token']
export const REFRESH_TOKEN_KEYS = ['mingjian_refresh_token', 'planagent_refresh_token', 'refresh_token']

export function readAuthToken() {
  if (typeof window === 'undefined') return ''
  for (const key of AUTH_TOKEN_KEYS) {
    const token = window.localStorage.getItem(key)
    if (token) return token
  }
  return ''
}

export function readRefreshToken() {
  if (typeof window === 'undefined') return ''
  for (const key of REFRESH_TOKEN_KEYS) {
    const token = window.localStorage.getItem(key)
    if (token) return token
  }
  return ''
}

export function storeAuthTokens(accessToken: string, refreshToken: string) {
  if (typeof window === 'undefined') return
  for (const key of AUTH_TOKEN_KEYS) window.localStorage.setItem(key, accessToken)
  for (const key of REFRESH_TOKEN_KEYS) window.localStorage.setItem(key, refreshToken)
}

export function clearAuthTokens() {
  if (typeof window === 'undefined') return
  for (const key of [...AUTH_TOKEN_KEYS, ...REFRESH_TOKEN_KEYS]) {
    window.localStorage.removeItem(key)
  }
}
