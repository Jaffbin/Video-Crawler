import { afterEach, expect, it } from 'vitest'
import { fileUrl, resetTokenCache } from './client'

afterEach(() => {
  document.head.innerHTML = ''
  resetTokenCache()
})

it('keeps the token out of file links when the app served the page', () => {
  document.head.innerHTML = '<meta name="grab-token" content="abcdefghijklmnopqrstuvwx">'
  resetTokenCache()
  expect(fileUrl('Playlist/Clip #1.mp4')).toBe('/files/Playlist/Clip%20%231.mp4')
})

it('falls back to a token in the link only when there is no page token (dev server)', () => {
  document.head.innerHTML = '<meta name="grab-token" content="__GRAB_TOKEN__">'
  window.history.replaceState(null, '', '/?t=devtoken1234567890')
  resetTokenCache()
  expect(fileUrl('a.mp4')).toBe('/files/a.mp4?t=devtoken1234567890')
  window.history.replaceState(null, '', '/')
})
