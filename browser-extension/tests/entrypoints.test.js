import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  createEntrypoints,
  MENU_LINK,
  MENU_PAGE,
} from '../chrome/entrypoints.js'

function fixture() {
  const stored = {},
    popups = [],
    tabs = [],
    menus = []
  const api = {
    runtime: { getURL: (path) => 'chrome-extension://fixture/' + path },
    i18n: { getMessage: (key) => key },
    storage: {
      session: {
        get: async (key) =>
          key === null ? { ...stored } : { [key]: stored[key] },
        set: async (values) => Object.assign(stored, values),
        remove: async (keys) => {
          for (const key of Array.isArray(keys) ? keys : [keys])
            delete stored[key]
        },
      },
    },
    action: {
      setPopup: async (value) => popups.push(value),
      openPopup: async () => {},
    },
    tabs: { create: async (value) => tabs.push(value) },
    contextMenus: {
      removeAll: async () => {},
      create: (value) => menus.push(value),
    },
  }
  return { api, stored, popups, tabs, menus }
}
const tab = {
  id: 3,
  windowId: 2,
  url: 'https://example.com/page',
  title: 'Example',
}

test('creates separate web-page and link menus with HTTP-only scope', async () => {
  const f = fixture(),
    entries = createEntrypoints(f.api)
  await entries.registerMenus()
  assert.deepEqual(
    f.menus.map((menu) => menu.contexts),
    [['page'], ['link']],
  )
  assert.deepEqual(f.menus[1].targetUrlPatterns, ['http://*/*', 'https://*/*'])
})

test('a clicked link reaches confirmation once without being replaced by the active tab', async () => {
  const f = fixture(),
    entries = createEntrypoints(f.api, () => 100)
  await entries.open(
    { menuItemId: MENU_LINK, linkUrl: 'https://example.com/linked' },
    tab,
  )
  const popup = f.popups[0].popup,
    id = new URLSearchParams(popup.split('?')[1]).get('intent')
  const value = await entries.consume(id)
  assert.equal(value.url, 'https://example.com/linked')
  assert.equal(value.kind, 'link')
  assert.deepEqual(f.stored, {})
  assert.equal(f.popups.at(-1).popup, 'popup.html')
  await assert.rejects(
    entries.consume(id),
    (error) => error.code === 'selectionExpired',
  )
  assert.equal(f.tabs.length, 0)
})

test('fallback opens a confirmation page with an opaque ID and no URL in its address', async () => {
  const f = fixture()
  f.api.action.openPopup = async () => {
    throw Error('popup unavailable')
  }
  const entries = createEntrypoints(f.api)
  await entries.open(
    { menuItemId: MENU_PAGE, pageUrl: 'https://unrelated.invalid' },
    tab,
  )
  assert.equal(f.tabs.length, 1)
  assert(!f.tabs[0].url.includes('example.com'))
  const id = new URL(f.tabs[0].url).searchParams.get('intent')
  assert.equal((await entries.consume(id)).url, tab.url)
})

test('expired and concurrent requests cannot reuse an intent; different tabs keep separate selections', async () => {
  const f = fixture()
  let now = 100
  const entries = createEntrypoints(f.api, () => now)
  await entries.open(
    { menuItemId: MENU_LINK, linkUrl: 'https://example.com/one' },
    tab,
  )
  await entries.open(
    { menuItemId: MENU_LINK, linkUrl: 'https://example.com/two' },
    { ...tab, id: 4 },
  )
  const ids = Object.keys(f.stored).map((key) => key.split(':')[1])
  const results = await Promise.allSettled([
    entries.consume(ids[0]),
    entries.consume(ids[0]),
  ])
  assert.equal(
    results.filter((value) => value.status === 'fulfilled').length,
    1,
  )
  now += 120001
  await assert.rejects(
    entries.consume(ids[1]),
    (error) => error.code === 'selectionExpired',
  )
  assert.deepEqual(f.stored, {})
})

test('credential and non-web URLs cannot become download targets, and abandoned intents are bounded', async () => {
  const f = fixture(),
    entries = createEntrypoints(f.api)
  for (const url of [
    'javascript:alert(1)',
    'https://user:password@example.com',
  ]) {
    await entries.open({ menuItemId: MENU_LINK, linkUrl: url }, tab)
    const key = Object.keys(f.stored)[0]
    assert.deepEqual(await entries.consume(key.split(':')[1]), {
      error: 'unsupportedPage',
    })
  }
  for (let i = 0; i < 25; i++)
    await entries.open({ menuItemId: MENU_PAGE }, tab)
  assert.equal(Object.keys(f.stored).length, 20)
})
