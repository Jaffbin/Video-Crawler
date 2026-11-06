import type { DownloadOptions } from '../types/api'
import { DEFAULT_OPTIONS, sanitizeOptions } from './options'

export const PRESETS_KEY = 'grab-download-presets'
export const OUTPUT_KEYS = [
  'mode',
  'quality',
  'abr',
  'subs',
  'sub_langs',
  'auto_subs',
  'embed_subs',
  'cover',
  'keep_cover',
] as const
export type OutputOptions = Pick<DownloadOptions, (typeof OUTPUT_KEYS)[number]>
export interface DownloadPreset {
  id: string
  name: string
  options: OutputOptions
}
export function outputOptions(input: Partial<DownloadOptions>): OutputOptions {
  const options = sanitizeOptions(input)
  return Object.fromEntries(OUTPUT_KEYS.map((key) => [key, options[key]])) as unknown as OutputOptions
}
export const BUILTIN_PRESETS: DownloadPreset[] = [
  { id: 'video', name: 'Everyday video', options: outputOptions({ ...DEFAULT_OPTIONS, quality: '1080' }) },
  {
    id: 'mp3',
    name: 'High-quality MP3',
    options: outputOptions({ ...DEFAULT_OPTIONS, mode: 'mp3', abr: 320 }),
  },
  {
    id: 'source',
    name: 'Keep source audio',
    options: outputOptions({ ...DEFAULT_OPTIONS, mode: 'original' }),
  },
  { id: 'cover', name: 'Cover only', options: outputOptions({ ...DEFAULT_OPTIONS, mode: 'cover' }) },
]
export function readPresets(): DownloadPreset[] {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(PRESETS_KEY) || '[]')
    if (!Array.isArray(value)) return []
    const names = new Set<string>(),
      ids = new Set<string>()
    return value
      .filter((item) => {
        if (
          !item ||
          typeof item.name !== 'string' ||
          !item.name.trim() ||
          item.name.length > 60 ||
          /[\x00-\x1f]/.test(item.name) ||
          !/^[a-f0-9]{32}$/.test(item.id) ||
          !item.options ||
          typeof item.options !== 'object'
        )
          return false
        const name = item.name.trim().toLowerCase()
        if (names.has(name) || ids.has(item.id)) return false
        names.add(name)
        ids.add(item.id)
        return true
      })
      .slice(0, 50)
      .map((item) => ({ id: item.id, name: item.name.trim(), options: outputOptions(item.options) }))
  } catch {
    return []
  }
}
export function writePresets(presets: DownloadPreset[]) {
  localStorage.setItem(PRESETS_KEY, JSON.stringify(presets))
  window.dispatchEvent(new Event('grab-presets-changed'))
}
