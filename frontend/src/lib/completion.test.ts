import { describe, expect, it } from 'vitest'
import { completionMessage } from './completion'

describe('completionMessage', () => {
  it('names the file for a single success', () => {
    expect(completionMessage({ ok: 1, bad: 0, title: 'My Video' })).toBe('Download complete: My Video')
  })
  it('counts several successes', () => {
    expect(completionMessage({ ok: 3, bad: 0, title: '' })).toBe('3 downloads completed')
  })
  it('reports mixed results, matching the backend toast wording', () => {
    expect(completionMessage({ ok: 2, bad: 1, title: '' })).toBe('Completed 2, failed 1')
  })
})
