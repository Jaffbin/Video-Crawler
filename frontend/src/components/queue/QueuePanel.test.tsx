import { describe, expect, it } from 'vitest'
import { matchesFilter, matchesSearch, successStats } from './QueuePanel'
import type { Job } from '../../types/api'

const job = (over: Partial<Job>): Job => ({
  id: '1',
  url: 'https://example.com/v',
  status: 'done',
  stage: '',
  title: 'My Video',
  percent: 100,
  speed: '',
  eta: '',
  item: '',
  error: '',
  files: [],
  mode: 'mp4',
  created: 0,
  finished: 0,
  notes: [],
  ...over,
})

describe('matchesFilter', () => {
  it('active covers queued and running only', () => {
    expect(matchesFilter(job({ status: 'queued' }), 'active')).toBe(true)
    expect(matchesFilter(job({ status: 'running' }), 'active')).toBe(true)
    expect(matchesFilter(job({ status: 'done' }), 'active')).toBe(false)
  })
  it('failed covers error and canceled', () => {
    expect(matchesFilter(job({ status: 'error' }), 'failed')).toBe(true)
    expect(matchesFilter(job({ status: 'canceled' }), 'failed')).toBe(true)
    expect(matchesFilter(job({ status: 'done' }), 'failed')).toBe(false)
  })
  it('all matches everything', () => {
    expect(matchesFilter(job({ status: 'error' }), 'all')).toBe(true)
  })
})

describe('matchesSearch', () => {
  it('matches title or URL, case-insensitively', () => {
    expect(matchesSearch(job({ title: 'Cat Video' }), 'cat')).toBe(true)
    expect(matchesSearch(job({ url: 'https://EXAMPLE.com/x' }), 'example')).toBe(true)
    expect(matchesSearch(job({ title: 'Cat Video' }), 'dog')).toBe(false)
  })
  it('an empty query matches everything', () => {
    expect(matchesSearch(job({ title: 'Anything' }), '  ')).toBe(true)
  })
})

describe('successStats', () => {
  it('uses completed and failed jobs but excludes active and canceled jobs', () => {
    expect(
      successStats([
        job({ status: 'done' }),
        job({ status: 'done' }),
        job({ status: 'error' }),
        job({ status: 'canceled' }),
        job({ status: 'running' }),
      ]),
    ).toEqual({ succeeded: 2, measured: 3, rate: 67 })
  })
  it('does not show a rate before an attempt finishes', () => {
    expect(successStats([job({ status: 'queued' })]).rate).toBeNull()
  })
})
