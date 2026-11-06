import { useLayoutEffect, useRef, useState } from 'react'
import { flushSync } from 'react-dom'
import { transitionTheme } from '../lib/themeTransition'

export type Theme = 'light' | 'dark'
const STORAGE_KEY = 'grab-theme'

export function readTheme(): Theme {
  try {
    return localStorage.getItem(STORAGE_KEY) === 'light' ? 'light' : 'dark'
  } catch {
    return 'dark'
  }
}

export function applyTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme
}

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(readTheme)
  const requested = useRef(theme)
  const cancel = useRef<(() => void) | undefined>(undefined)
  useLayoutEffect(() => () => cancel.current?.(), [])
  useLayoutEffect(() => {
    applyTheme(theme)
    try {
      localStorage.setItem(STORAGE_KEY, theme)
    } catch {
      // Theme switching still works when browser storage is unavailable.
    }
  }, [theme])
  const toggleTheme = (button?: HTMLElement) => {
    const next = requested.current === 'dark' ? 'light' : 'dark'
    requested.current = next
    cancel.current?.()
    cancel.current = transitionTheme(next, () => flushSync(() => setTheme(next)), button)
  }
  const restoreTheme = () => {
    cancel.current?.()
    const next = readTheme()
    requested.current = next
    setTheme(next)
  }
  return { theme, toggleTheme, restoreTheme }
}
