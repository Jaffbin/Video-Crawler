import type { DownloadOptions } from '../types/api'

export const STORAGE_KEY = 'grab-options'
export const QUALITIES = [2160, 1440, 1080, 720, 480, 360]
export const BITRATES = [320, 256, 192, 128, 96]
export const BROWSERS = ['chrome', 'edge', 'firefox', 'brave', 'chromium', 'opera', 'vivaldi', 'safari']

export const DEFAULT_OPTIONS: DownloadOptions = {
  mode: 'mp4',
  quality: 'best',
  abr: 192,
  subs: false,
  sub_langs: 'zh-Hans,zh-Hant,zh,en',
  auto_subs: false,
  embed_subs: false,
  cover: false,
  keep_cover: false,
  no_playlist: false,
  items: '',
  archive: false,
  cookies_from_browser: '',
  use_cookies_file: false,
  referer: '',
  proxy: '',
  limit_rate: '',
  sleep: 0,
  threads: 4,
  all_sniffed: false,
  js_render: false,
  js_wait: 8,
}

const clamp = (value: unknown, min: number, max: number, fallback: number): number => {
  const n = Number(value)
  return Number.isFinite(n) ? Math.min(Math.max(n, min), max) : fallback
}

/** Whatever is stored or typed, return options the backend will accept. Never produces NaN. */
export function sanitizeOptions(input: Partial<DownloadOptions>): DownloadOptions {
  const o = { ...DEFAULT_OPTIONS, ...input }
  const quality = String(o.quality ?? 'best')
    .toLowerCase()
    .replace(/p$/, '')
  const abr = Number(o.abr)
  return {
    ...o,
    mode: o.mode === 'mp3' ? 'mp3' : 'mp4',
    quality: quality === 'best' || /^\d+$/.test(quality) ? quality : 'best',
    abr: BITRATES.includes(abr) ? abr : DEFAULT_OPTIONS.abr,
    threads: Math.round(clamp(o.threads, 1, 16, DEFAULT_OPTIONS.threads)),
    sleep: clamp(o.sleep, 0, 60, 0),
    js_wait: clamp(o.js_wait, 2, 30, DEFAULT_OPTIONS.js_wait),
    cookies_from_browser: BROWSERS.includes(o.cookies_from_browser) ? o.cookies_from_browser : '',
    use_cookies_file: Boolean(o.use_cookies_file),
  }
}

export function loadOptions(): DownloadOptions {
  try {
    const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}')
    return sanitizeOptions(typeof stored === 'object' && stored ? stored : {})
  } catch {
    return { ...DEFAULT_OPTIONS }
  }
}

export function saveOptions(options: DownloadOptions): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(options))
  } catch {
    /* storage can be unavailable; the options just won't be remembered */
  }
}
