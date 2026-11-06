import { expect, it } from 'vitest'
import { browseKey, DEFAULT_BROWSE, loadBrowse } from './libraryBrowse'

it('rejects corrupt and invalid saved browsing values', () => {
  localStorage.setItem(browseKey('A'), 'broken')
  expect(loadBrowse('A')).toEqual(DEFAULT_BROWSE)
  localStorage.setItem(
    browseKey('A'),
    JSON.stringify({ query: 2, kind: 'script', sort: 'invalid', page: -1, pageSize: 10000 }),
  )
  expect(loadBrowse('A')).toEqual(DEFAULT_BROWSE)
})
