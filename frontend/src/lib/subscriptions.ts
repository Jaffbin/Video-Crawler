import type { BackfillMode } from '../types/api'

export const BACKFILL_MAX = 50
export const DEFAULT_BACKFILL_COUNT = 5

/** Clamp whatever a form or a stored value has into something the backend will accept. */
export function sanitizeBackfillCount(value: unknown): number {
  if (value === '' || value === null || value === undefined) return DEFAULT_BACKFILL_COUNT
  const n = Math.round(Number(value))
  if (!Number.isFinite(n)) return DEFAULT_BACKFILL_COUNT
  return Math.min(Math.max(n, 1), BACKFILL_MAX)
}

export function sanitizeBackfillMode(value: unknown): BackfillMode {
  return value === 'recent' ? 'recent' : 'none'
}
