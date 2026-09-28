import { useCallback, useEffect, useState } from 'react'

export type AppView = 'new' | 'queue' | 'auto-download' | 'library'

const STORAGE_KEY = 'video-grabber-view'
const VIEWS = new Set<AppView>(['new', 'queue', 'auto-download', 'library'])

function viewFromHash(): AppView | null {
  const value = window.location.hash.replace(/^#\/?/, '') as AppView
  return VIEWS.has(value) ? value : null
}

function initialView(): AppView {
  const fromHash = viewFromHash()
  if (fromHash) return fromHash
  try {
    const saved = localStorage.getItem(STORAGE_KEY) as AppView | null
    if (saved && VIEWS.has(saved)) return saved
  } catch {
    // Storage can be disabled in hardened WebView/browser configurations.
  }
  return 'new'
}

export function useNavigation() {
  const [view, setView] = useState<AppView>(initialView)

  useEffect(() => {
    const onHashChange = () => {
      const next = viewFromHash()
      if (next) setView(next)
    }
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, view)
    } catch {
      // Navigation still works without persistence.
    }
  }, [view])

  const navigate = useCallback((next: AppView) => {
    if (viewFromHash() === next) {
      setView(next)
      return
    }
    window.location.hash = `/${next}`
  }, [])

  return { view, navigate }
}
