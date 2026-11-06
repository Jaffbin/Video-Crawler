import type { FileItem, SmartCollection, SmartRules } from '../types/api'
import { fileKind } from './library'

export const BUILTIN_SMART_COLLECTIONS: SmartCollection[] = [
  { id: 'builtin:recent', name: 'Saved in the last 30 days', rules: { recent_days: 30 }, builtin: true },
  { id: 'builtin:unplayed', name: 'Not started in this app', rules: { playback: 'unplayed' }, builtin: true },
  {
    id: 'builtin:continuing',
    name: 'Continue watching / listening',
    rules: { playback: 'in_progress' },
    builtin: true,
  },
  { id: 'builtin:favorites', name: 'Favorites', rules: { favorite: true }, builtin: true },
]

export function matchesSmartCollection(file: FileItem, rules: SmartRules, now = Date.now() / 1000): boolean {
  if (rules.kind && fileKind(file) !== rules.kind) return false
  if (rules.source && (file.source || 'unknown') !== rules.source) return false
  if (rules.format && !file.name.toLowerCase().endsWith(rules.format)) return false
  const tag = rules.tag?.toLowerCase()
  if (tag && !file.tags?.some((value) => value.toLowerCase() === tag)) return false
  if (rules.favorite !== undefined && !!file.favorite !== rules.favorite) return false
  if (rules.recent_days !== undefined) {
    const saved = file.downloaded ?? file.mtime
    if (!Number.isFinite(saved) || saved < now - rules.recent_days * 86400 || saved > now) return false
  }
  if (rules.playback) {
    if (fileKind(file) === 'image' || file.complete === false) return false
    const playback = file.playback
    if (rules.playback === 'unplayed' && playback && (playback.position > 0 || playback.finished))
      return false
    if (rules.playback === 'in_progress' && (!playback || playback.finished || playback.position <= 0))
      return false
    if (rules.playback === 'finished' && !playback?.finished) return false
  }
  return true
}

export function smartName(collection: SmartCollection, t: (key: string) => string): string {
  return collection.builtin ? t(collection.name) : collection.name
}
