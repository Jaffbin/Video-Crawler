import { expect, it } from 'vitest'
import type { FileItem } from '../types/api'
import { BUILTIN_SMART_COLLECTIONS, matchesSmartCollection, smartName } from './smartCollections'

const file: FileItem = {
  path: 'clip.mp4',
  name: 'clip.mp4',
  size: 20,
  mtime: 100,
  kind: 'video',
  source: 'example.com',
  tags: ['My Tag'],
  favorite: true,
}

it('matches all conditions together and preserves false favorites and exact tags', () => {
  const rules = {
    kind: 'video' as const,
    source: 'example.com',
    format: '.mp4',
    tag: 'my tag',
    favorite: true,
  }
  expect(matchesSmartCollection(file, rules)).toBe(true)
  expect(matchesSmartCollection({ ...file, source: 'other.com' }, rules)).toBe(false)
  expect(matchesSmartCollection(file, { tag: 'tag' })).toBe(false)
  expect(matchesSmartCollection(file, { favorite: false })).toBe(false)
  expect(matchesSmartCollection({ ...file, favorite: undefined }, { favorite: false })).toBe(true)
  expect(matchesSmartCollection({ ...file, source: undefined }, { source: 'unknown' })).toBe(true)
  expect(matchesSmartCollection({ ...file, name: 'CLIP.MP4' }, { format: '.mp4' })).toBe(true)
})

it('uses saved dates, falls back to modification dates and handles rolling boundaries', () => {
  const now = 40 * 86400
  expect(matchesSmartCollection({ ...file, downloaded: now - 7 * 86400 }, { recent_days: 7 }, now)).toBe(true)
  expect(matchesSmartCollection({ ...file, downloaded: now - 7 * 86400 - 1 }, { recent_days: 7 }, now)).toBe(
    false,
  )
  expect(matchesSmartCollection({ ...file, mtime: now }, { recent_days: 7 }, now)).toBe(true)
  expect(matchesSmartCollection({ ...file, downloaded: now + 1 }, { recent_days: 7 }, now)).toBe(false)
  expect(matchesSmartCollection({ ...file, mtime: NaN }, { recent_days: 7 }, now)).toBe(false)
  expect(matchesSmartCollection({ ...file, downloaded: now }, { recent_days: 7 }, now + 8 * 86400)).toBe(
    false,
  )
})

it('uses only in-app playback on complete video/audio and keeps states disjoint', () => {
  const playing = { ...file, playback: { position: 0.5, duration: 60, finished: false, updated: 1 } }
  const finished = { ...playing, playback: { ...playing.playback, finished: true } }
  expect(matchesSmartCollection(file, { playback: 'unplayed' })).toBe(true)
  expect(matchesSmartCollection(playing, { playback: 'unplayed' })).toBe(false)
  expect(matchesSmartCollection(playing, { playback: 'in_progress' })).toBe(true)
  expect(matchesSmartCollection(playing, { playback: 'finished' })).toBe(false)
  expect(matchesSmartCollection(finished, { playback: 'finished' })).toBe(true)
  expect(matchesSmartCollection(finished, { playback: 'in_progress' })).toBe(false)
  expect(matchesSmartCollection({ ...file, kind: 'audio', playback: null }, { playback: 'unplayed' })).toBe(
    true,
  )
  expect(matchesSmartCollection({ ...file, complete: false }, { playback: 'unplayed' })).toBe(false)
  expect(matchesSmartCollection({ ...file, kind: 'image' }, { playback: 'unplayed' })).toBe(false)
  expect(
    matchesSmartCollection({ ...file, kind: undefined, name: 'cover.jpg' }, { playback: 'unplayed' }),
  ).toBe(false)
})

it('translates built-ins while preserving custom names as user text', () => {
  expect(new Set(BUILTIN_SMART_COLLECTIONS.map((item) => item.id)).size).toBe(4)
  const translate = (text: string) => `translated:${text}`
  expect(smartName(BUILTIN_SMART_COLLECTIONS[0], translate)).toMatch(/^translated:/)
  expect(smartName({ id: 'custom', name: 'Favorites', rules: { favorite: true } }, translate)).toBe(
    'Favorites',
  )
})
