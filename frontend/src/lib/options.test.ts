import { describe, expect, it } from 'vitest'
import {
  DEFAULT_OPTIONS,
  describeOptions,
  loadOptions,
  sanitizeOptions,
  saveOptions,
  STORAGE_KEY,
} from './options'

describe('sanitizeOptions', () => {
  it('never lets an unknown bitrate reach the backend as NaN', () => {
    // This was a real bug in the ChatGPT-generated UI: its <select> had no `value`, so this reached the backend as NaN.
    expect(sanitizeOptions({ abr: NaN }).abr).toBe(DEFAULT_OPTIONS.abr)
    expect(sanitizeOptions({ abr: 12 }).abr).toBe(DEFAULT_OPTIONS.abr)
    expect(sanitizeOptions({ abr: 320 }).abr).toBe(320)
  })

  it('normalizes a quality of "1080p" to "1080", and rejects nonsense', () => {
    expect(sanitizeOptions({ quality: '1080p' }).quality).toBe('1080')
    expect(sanitizeOptions({ quality: 'ultra' }).quality).toBe('best')
  })

  it('clamps numeric ranges instead of passing something out of range', () => {
    expect(sanitizeOptions({ threads: 999 }).threads).toBe(16)
    expect(sanitizeOptions({ threads: 0 }).threads).toBe(1)
    expect(sanitizeOptions({ sleep: -5 }).sleep).toBe(0)
    expect(sanitizeOptions({ sleep: 99 }).sleep).toBe(60)
  })

  it('only allows a known browser name for cookies_from_browser', () => {
    expect(sanitizeOptions({ cookies_from_browser: 'chrome' }).cookies_from_browser).toBe('chrome')
    expect(sanitizeOptions({ cookies_from_browser: '../../etc' }).cookies_from_browser).toBe('')
  })

  it('fills in anything missing from the defaults', () => {
    expect(sanitizeOptions({})).toEqual(DEFAULT_OPTIONS)
  })
})

describe('loadOptions / saveOptions', () => {
  it('round-trips through localStorage', () => {
    saveOptions({ ...DEFAULT_OPTIONS, mode: 'mp3', abr: 128 })
    expect(loadOptions()).toEqual({ ...DEFAULT_OPTIONS, mode: 'mp3', abr: 128 })
  })

  it('falls back to defaults when storage has garbage', () => {
    localStorage.setItem(STORAGE_KEY, 'not json')
    expect(loadOptions()).toEqual(DEFAULT_OPTIONS)
  })
})

describe('describeOptions', () => {
  const base = { mode: 'mp4' as const, quality: 'best', abr: 192, subs: false, cover: false }

  it('describes video downloads with the quality cap', () => {
    expect(describeOptions(base)).toBe('MP4 · best quality')
    expect(describeOptions({ ...base, quality: '1080' })).toBe('MP4 · up to 1080p')
  })
  it('describes audio downloads with the bitrate and ignores the video quality', () => {
    expect(describeOptions({ ...base, mode: 'mp3', abr: 320, quality: '720' })).toBe('MP3 · 320 kbps')
  })
  it('mentions subtitles only for video, and the cover for both', () => {
    expect(describeOptions({ ...base, subs: true, cover: true })).toBe(
      'MP4 · best quality · subtitles · cover',
    )
    expect(describeOptions({ ...base, mode: 'mp3', subs: true, cover: true })).toBe('MP3 · 192 kbps · cover')
  })
})
