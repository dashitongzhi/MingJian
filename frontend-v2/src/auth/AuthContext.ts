import { createContext, useContext } from 'react'

export type AuthContextValue = {
  mode: 'local' | 'remote'
  username: string
  logout: () => Promise<void>
  changePassword: (currentPassword: string, newPassword: string) => Promise<void>
}

export const AuthContext = createContext<AuthContextValue | null>(null)

export function useAuth() {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used inside AuthGate')
  return value
}
