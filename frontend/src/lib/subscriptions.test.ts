import { describe, expect, it } from 'vitest'
import {
  BACKFILL_MAX,
  DEFAULT_BACKFILL_COUNT,
  sanitizeBackfillCount,
  sanitizeBackfillMode,
} from './subscriptions'

describe('sanitizeBackfillCount', () => {
  it('rounds and clamps to the valid range', () => {
    expect(sanitizeBackfillCount(3.7)).toBe(4)
    expect(sanitizeBackfillCount(0)).toBe(1)
    expect(sanitizeBackfillCount(-5)).toBe(1)
    expect(sanitizeBackfillCount(9999)).toBe(BACKFILL_MAX)
  })
  it('falls back to the default for anything that is not a number', () => {
    expect(sanitizeBackfillCount('')).toBe(DEFAULT_BACKFILL_COUNT)
    expect(sanitizeBackfillCount('abc')).toBe(DEFAULT_BACKFILL_COUNT)
    expect(sanitizeBackfillCount(undefined)).toBe(DEFAULT_BACKFILL_COUNT)
  })
})

describe('sanitizeBackfillMode', () => {
  it('only accepts "recent", everything else becomes "none"', () => {
    expect(sanitizeBackfillMode('recent')).toBe('recent')
    expect(sanitizeBackfillMode('none')).toBe('none')
    expect(sanitizeBackfillMode('anything-else')).toBe('none')
    expect(sanitizeBackfillMode(undefined)).toBe('none')
  })
})
