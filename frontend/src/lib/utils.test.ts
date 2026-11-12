import { afterEach, expect, it } from 'vitest'
import { formatDate } from './utils'

afterEach(() => document.documentElement.removeAttribute('lang'))

it('formats dates in the interface language instead of the system region', () => {
  const ts = Date.UTC(2026, 9, 16, 12, 0) / 1000
  document.documentElement.lang = 'en'
  expect(formatDate(ts)).toMatch(/Oct 16, 2026/)
  document.documentElement.lang = 'zh-CN'
  expect(formatDate(ts)).toMatch(/2026年10月16日/)
})
