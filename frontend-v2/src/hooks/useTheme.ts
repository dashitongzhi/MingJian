import { useEffect, useState } from 'react'

export type AppTheme = 'dark' | 'light'

const STORAGE_KEY = 'mingjian.theme'

function readStoredTheme(): AppTheme {
  if (typeof window === 'undefined') return 'dark'
  return window.localStorage.getItem(STORAGE_KEY) === 'light' ? 'light' : 'dark'
}

export function useTheme() {
  const [theme, setTheme] = useState<AppTheme>(readStoredTheme)

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    document.documentElement.style.colorScheme = theme
    window.localStorage.setItem(STORAGE_KEY, theme)
  }, [theme])

  const toggleTheme = () => setTheme((current) => (current === 'dark' ? 'light' : 'dark'))

  return { theme, toggleTheme }
}
