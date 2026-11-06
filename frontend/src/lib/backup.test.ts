import { beforeEach, expect, it, vi, afterEach } from 'vitest'
import { applyBrowserPreferences, browserPreferences } from './backup'
import { DEFAULT_OPTIONS, STORAGE_KEY } from './options'
import { PRESETS_KEY } from './presets'

beforeEach(() => localStorage.clear())
afterEach(() => vi.restoreAllMocks())

it('exports only output preferences and preserves existing private connection settings on restore', () => {
  localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({ ...DEFAULT_OPTIONS, proxy: 'private', referer: 'private-url' }),
  )
  expect(JSON.stringify(browserPreferences(true))).not.toContain('private')
  applyBrowserPreferences({ download: { ...DEFAULT_OPTIONS, mode: 'mp3' } })
  const saved = JSON.parse(localStorage.getItem(STORAGE_KEY)!)
  expect(saved.mode).toBe('mp3')
  expect(saved.proxy).toBe('private')
})

it('rolls back browser keys if saving fails partway through', () => {
  localStorage.setItem('grab-theme', 'dark')
  const write = Storage.prototype.setItem
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(function (this: Storage, key, value) {
    if (key === PRESETS_KEY) throw new Error('quota fixture')
    write.call(this, key, value)
  })
  expect(() => applyBrowserPreferences({ download: { mode: 'mp3' }, presets: [], theme: 'light' })).toThrow()
  expect(localStorage.getItem(STORAGE_KEY)).toBeNull()
  expect(localStorage.getItem('grab-theme')).toBe('dark')
})
