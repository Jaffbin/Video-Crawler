import { DEFAULT_OPTIONS, loadOptions, sanitizeOptions, STORAGE_KEY } from './options'
import { outputOptions, PRESETS_KEY, readPresets, type DownloadPreset, type OutputOptions } from './presets'

export interface BrowserPreferences {
  download?: Partial<OutputOptions>
  presets?: DownloadPreset[]
  theme?: 'light' | 'dark'
  locale?: 'en' | 'zh-CN' | 'zh-TW' | 'ja'
}
export interface BackupReview {
  counts: {
    files: number
    collections: number
    smart_collections?: number
    presets: number
    settings: number
    conflicts: number
  }
  skipped: { path: string; reason: 'size' | 'missing' }[]
  review_token: string
  browser: BrowserPreferences
}
export function browserPreferences(forExport = false): BrowserPreferences {
  const result: BrowserPreferences = { presets: readPresets() }
  if (forExport || localStorage.getItem(STORAGE_KEY) !== null) result.download = outputOptions(loadOptions())
  const theme = localStorage.getItem('grab-theme'),
    locale = localStorage.getItem('grab-locale')
  if (theme === 'dark' || theme === 'light') result.theme = theme
  if (locale && ['en', 'zh-CN', 'zh-TW', 'ja'].includes(locale))
    result.locale = locale as BrowserPreferences['locale']
  return result
}
export function applyBrowserPreferences(value: BrowserPreferences) {
  const changes: Record<string, string> = {}
  if (value.download)
    changes[STORAGE_KEY] = JSON.stringify(
      sanitizeOptions({ ...DEFAULT_OPTIONS, ...loadOptions(), ...outputOptions(value.download) }),
    )
  if (value.presets) changes[PRESETS_KEY] = JSON.stringify(value.presets)
  if (value.theme) changes['grab-theme'] = value.theme
  if (value.locale) changes['grab-locale'] = value.locale
  const before = Object.fromEntries(Object.keys(changes).map((key) => [key, localStorage.getItem(key)]))
  try {
    for (const [key, content] of Object.entries(changes)) localStorage.setItem(key, content)
  } catch (error) {
    for (const [key, content] of Object.entries(before)) {
      if (content === null) localStorage.removeItem(key)
      else localStorage.setItem(key, content)
    }
    throw error
  }
  window.dispatchEvent(new Event('grab-presets-changed'))
  window.dispatchEvent(new Event('grab-preferences-restored'))
}
