import { useEffect } from 'react'
import { useI18n } from '../i18n'
import { applyTheme, readTheme } from '../hooks/useTheme'

interface DesktopApi {
  sync_locale?: (locale: string) => Promise<void>
  show_main?: (view: string) => Promise<void>
  hide_quick?: () => Promise<void>
  close_settings?: () => Promise<{
    behavior: 'ask' | 'background' | 'exit'
    tray_ready: boolean
    pending_downloads?: number
  }>
  set_close_behavior?: (behavior: 'ask' | 'background' | 'exit') => Promise<unknown>
  close_action?: (action: 'cancel' | 'background' | 'exit', remember?: boolean) => Promise<void>
}

declare global {
  interface Window {
    pywebview?: { api: DesktopApi }
  }
}

export function useDesktopLocale() {
  const { locale } = useI18n()
  useEffect(() => {
    const sync = () => {
      void window.pywebview?.api.sync_locale?.(locale).catch(() => undefined)
    }
    sync()
    window.addEventListener('pywebviewready', sync)
    return () => window.removeEventListener('pywebviewready', sync)
  }, [locale])
}

export function useQuickAppearance() {
  const { setLocale } = useI18n()
  useEffect(() => {
    const sync = (event: StorageEvent) => {
      if (event.key === 'grab-theme' || event.key === null) applyTheme(readTheme())
      if (event.key === 'grab-locale' && ['en', 'zh-CN', 'zh-TW', 'ja'].includes(event.newValue || '')) {
        setLocale(event.newValue as 'en' | 'zh-CN' | 'zh-TW' | 'ja')
      }
    }
    window.addEventListener('storage', sync)
    return () => window.removeEventListener('storage', sync)
  }, [setLocale])
}

export async function showDesktopMain(view: 'new' | 'queue' | 'library') {
  if (window.pywebview?.api.show_main) await window.pywebview.api.show_main(view)
  else window.location.assign('/#/' + view)
}
