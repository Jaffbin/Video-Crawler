import { describe, expect, it } from 'vitest'
import { extractUrls, looksLikeTextFile, mergeUrls, readUrls } from './urls'

describe('extractUrls', () => {
  it('finds a plain link', () => {
    expect(extractUrls('see https://example.com/v/1 and https://a.org/x.m3u8')).toEqual([
      'https://example.com/v/1',
      'https://a.org/x.m3u8',
    ])
  })

  it('stops at Chinese punctuation glued to the link (the bug this project hit before)', () => {
    expect(extractUrls('看这个https://example.com/watch?v=1，谢谢')).toEqual([
      'https://example.com/watch?v=1',
    ])
  })

  it('does not cut the link at its first dot', () => {
    expect(extractUrls('https://example.com/a/b.html')).toEqual(['https://example.com/a/b.html'])
  })

  it('trims trailing punctuation used to end a sentence', () => {
    expect(extractUrls('go to https://x.com/a.')).toEqual(['https://x.com/a'])
  })

  it('strips surrounding parentheses and brackets', () => {
    expect(extractUrls('(https://x.com/a) [https://x.com/b]')).toEqual(['https://x.com/a', 'https://x.com/b'])
  })

  it('de-duplicates', () => {
    expect(extractUrls('https://a.io/1 https://a.io/1')).toEqual(['https://a.io/1'])
  })

  it('returns nothing for plain text', () => {
    expect(extractUrls('no links here')).toEqual([])
  })
})

describe('readUrls', () => {
  it('splits by line, trims, and drops blanks and comments', () => {
    expect(readUrls('https://a.com/1\n\n# a comment\n  https://a.com/2  \n')).toEqual([
      'https://a.com/1',
      'https://a.com/2',
    ])
  })
})

describe('mergeUrls', () => {
  it('appends only the links not already present', () => {
    const { text, added } = mergeUrls('https://a.com/1\n', ['https://a.com/1', 'https://a.com/2'])
    expect(readUrls(text)).toEqual(['https://a.com/1', 'https://a.com/2'])
    expect(added).toBe(1)
  })

  it('reports zero when nothing new was found', () => {
    expect(mergeUrls('https://a.com/1\n', ['https://a.com/1'])).toEqual({
      text: 'https://a.com/1\n',
      added: 0,
    })
  })

  it('starts cleanly from an empty box', () => {
    expect(mergeUrls('', ['https://a.com/1']).text).toBe('https://a.com/1\n')
  })
})

describe('looksLikeTextFile', () => {
  it('accepts a text mime type or a known extension', () => {
    expect(looksLikeTextFile({ name: 'links.txt', type: '' })).toBe(true)
    expect(looksLikeTextFile({ name: 'links', type: 'text/plain' })).toBe(true)
    expect(looksLikeTextFile({ name: 'video.mp4', type: 'video/mp4' })).toBe(false)
  })
})
