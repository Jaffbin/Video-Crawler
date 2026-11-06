import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import {
  AppError,
  originForPort,
  checkedOrigin,
  checkedPage,
  tokenFromPage,
  connect,
  downloadOptions,
  enqueue,
  openQueue,
} from '../chrome/connection.js'

const origin = 'http://127.0.0.1:8765'
const token = 'test-session-token-0123456789'
const connection = { origin, token, root: 'D:/Media', window: true }
const page = () => new Response(`<meta name="grab-token" content="${token}">`)
const state = () =>
  Response.json({
    root: 'D:/Media',
    version: '1',
    jobs: [],
    rev: 0,
    window: true,
  })

test('checks existing downloads before enqueueing and forwards an explicit copy choice', async () => {
  const bodies = []
  const fetcher = async (_url, init) => {
    bodies.push(JSON.parse(init.body))
    return Response.json(
      bodies.length === 1
        ? { ids: [], existing: [{ name: '<video>.mp4' }] }
        : { ids: ['1234abcd'] },
    )
  }
  const input = { url: 'https://example.com/watch', mode: 'mp4' }
  const notice = await enqueue(connection, input, fetcher)
  assert.equal(notice.count, 0)
  assert.equal(notice.existing[0].name, '<video>.mp4')
  assert.equal(bodies[0].check_existing, true)
  const copy = await enqueue(
    connection,
    { ...input, existingAction: 'download' },
    fetcher,
  )
  assert.equal(copy.count, 1)
  assert.equal(bodies[1].existing_action, 'download')
})

test('can open the library through the authenticated desktop bridge', async () => {
  let view
  assert.equal(
    await openQueue(
      connection,
      async (_url, init) => {
        view = JSON.parse(init.body).view
        return Response.json({ opened: true })
      },
      'library',
    ),
    true,
  )
  assert.equal(view, 'library')
})

test('limits app access to loopback HTTP, numeric ports and a root origin', () => {
  assert.equal(originForPort('08765'), origin)
  assert.equal(checkedOrigin(origin), origin)
  for (const value of ['', 0, -1, 65536, '8.5', '8765/a'])
    assert.throws(() => originForPort(value), AppError)
  for (const value of [
    'https://127.0.0.1:8765',
    'http://localhost:8765',
    'http://127.0.0.1.evil.test:8765',
    origin + '/api',
    origin + '/?token=secret',
    origin + '/#foo',
    'http://u:p@127.0.0.1:8765',
  ])
    assert.throws(() => checkedOrigin(value), AppError)
})

test('accepts one normal web URL and rejects internal pages and credential URLs', () => {
  assert.equal(
    checkedPage('https://example.com/watch?v=a&list=b'),
    'https://example.com/watch?v=a&list=b',
  )
  for (const value of [
    '',
    'chrome://settings',
    'file:///C:/file.mp4',
    'javascript:alert(1)',
    'https://user:password@example.com/v',
    'https://example.com/' + 'x'.repeat(8192),
  ])
    assert.throws(() => checkedPage(value), AppError)
})

test('recognizes only the app token metadata and never accepts an unrendered template', () => {
  assert.equal(
    tokenFromPage(`<meta content='${token}' name='grab-token'>`),
    token,
  )
  for (const html of [
    '<meta name="grab-token" content="__GRAB_TOKEN__">',
    `<meta data-name="grab-token" content="${token}">`,
    `<div name="grab-token" content="${token}">`,
  ])
    assert.throws(() => tokenFromPage(html), AppError)
})

test('verifies the app using its existing authenticated API and refuses redirects', async () => {
  const calls = []
  const result = await connect(origin, async (url, init) => {
    calls.push({ url, init })
    return calls.length === 1 ? page() : state()
  })
  assert.equal(result.root, 'D:/Media')
  assert.equal(calls[1].init.headers['X-Token'], token)
  assert(
    calls.every(
      (call) =>
        call.init.redirect === 'error' && call.init.credentials === 'omit',
    ),
  )
  await assert.rejects(
    connect(origin, async () => new Response('unrelated app')),
    (error) => error.code === 'notOurApp',
  )
  let call = 0
  await assert.rejects(
    connect(origin, async () =>
      ++call === 1 ? page() : Response.json({ root: 'D:/Media' }),
    ),
    (error) => error.code === 'notOurApp',
  )
})

test('constrains output choices and always excludes playlists and companions', () => {
  assert.deepEqual(
    downloadOptions({
      mode: 'original',
      abr: 123,
      quality: 'evil',
      no_playlist: false,
      cover: true,
    }),
    {
      mode: 'original',
      quality: 'best',
      abr: 192,
      no_playlist: true,
      items: '',
      subs: false,
      auto_subs: false,
      embed_subs: false,
      cover: false,
      keep_cover: false,
      all_sniffed: false,
    },
  )
  assert.throws(() => downloadOptions({ mode: 'command' }), AppError)
})

test('creates one task and reports an already queued item without storing the credential in the result', async () => {
  const input = {
    url: 'https://example.com/v',
    mode: 'mp3',
    abr: 320,
    quality: 'best',
  }
  const result = await enqueue(connection, input, async (url, init) => {
    assert.equal(url, origin + '/api/jobs')
    const body = JSON.parse(init.body)
    assert.deepEqual(body.urls, [input.url])
    assert.equal(body.options.mode, 'mp3')
    assert.equal(body.options.no_playlist, true)
    return Response.json({ ids: [], duplicates: 1 })
  })
  assert.equal(result.count, 0)
  assert.equal(result.duplicates, 1)
})

test('refreshes an expired credential only after explicit 401, then retries once', async () => {
  const calls = []
  const responses = [
    Response.json({ error: 'Unauthorized' }, { status: 401 }),
    page(),
    state(),
    Response.json({ ids: ['abcd1234'] }),
  ]
  const result = await enqueue(
    { ...connection, token: 'old-token' },
    { url: 'https://example.com/v', mode: 'mp4' },
    async (url, init) => {
      calls.push({ url, init })
      return responses.shift()
    },
  )
  assert.equal(result.count, 1)
  assert.equal(calls.length, 4)
  assert.equal(calls[3].init.headers['X-Token'], token)
})

test('does not retry a possibly delivered download after a network error or failed response', async () => {
  let calls = 0
  await assert.rejects(
    enqueue(
      connection,
      { url: 'https://example.com/v', mode: 'mp4' },
      async () => {
        calls++
        throw new Error('connection lost')
      },
    ),
    (error) => error.code === 'downloadUnconfirmed',
  )
  assert.equal(calls, 1)
  calls = 0
  await assert.rejects(
    enqueue(
      connection,
      { url: 'https://example.com/v', mode: 'mp4' },
      async () => {
        calls++
        return Response.json({ error: 'Queue unavailable' }, { status: 503 })
      },
    ),
    (error) =>
      error.code === 'downloadFailed' && error.detail === 'Queue unavailable',
  )
  assert.equal(calls, 1)
})

test('requires confirmation when a restarted app points at a different save folder', async () => {
  let calls = 0
  const replies = [
    Response.json({}, { status: 401 }),
    page(),
    Response.json({ root: 'D:/Other', version: '1', jobs: [], rev: 0 }),
  ]
  await assert.rejects(
    enqueue(
      connection,
      { url: 'https://example.com/v', mode: 'mp4' },
      async () => {
        calls++
        return replies.shift()
      },
    ),
    (error) => error.code === 'destinationChanged',
  )
  assert.equal(calls, 3)
})

test('opens the desktop queue when supported and falls back for older apps', async () => {
  assert.equal(
    await openQueue(connection, async (url, init) => {
      assert.equal(url, origin + '/api/desktop/show')
      assert.deepEqual(JSON.parse(init.body), { view: 'queue' })
      return Response.json({ opened: true })
    }),
    true,
  )
  assert.equal(
    await openQueue(connection, async () => new Response('', { status: 404 })),
    false,
  )
})

test('keeps extension permissions narrow and translations complete', () => {
  const root = new URL('../chrome/', import.meta.url)
  const manifest = JSON.parse(readFileSync(new URL('manifest.json', root)))
  assert.deepEqual(manifest.permissions, [
    'activeTab',
    'storage',
    'contextMenus',
  ])
  assert.equal(
    manifest.commands._execute_action.suggested_key.default,
    'Alt+Shift+V',
  )
  assert.deepEqual(manifest.host_permissions, ['http://127.0.0.1/*'])
  assert.equal(manifest.content_scripts, undefined)
  const english = JSON.parse(
    readFileSync(new URL('_locales/en/messages.json', root)),
  )
  for (const locale of ['zh_CN', 'zh_TW', 'ja']) {
    const messages = JSON.parse(
      readFileSync(new URL(`_locales/${locale}/messages.json`, root)),
    )
    assert.deepEqual(Object.keys(messages).sort(), Object.keys(english).sort())
    assert(
      Object.values(messages).every(
        (value) => typeof value.message === 'string' && value.message,
      ),
    )
  }
})

test('a restarted worker checks the popup destination before posting and rejects non-extension senders', async () => {
  const previousChrome = globalThis.chrome
  const previousFetch = globalThis.fetch
  let listener
  const calls = []
  globalThis.chrome = {
    runtime: {
      id: 'test-extension',
      getURL: (path) => 'chrome-extension://test-extension/' + path,
      onMessage: {
        addListener: (value) => {
          listener = value
        },
      },
      onInstalled: { addListener() {} },
      onStartup: { addListener() {} },
    },
    contextMenus: { onClicked: { addListener() {} } },
  }
  globalThis.fetch = async (url, init) => {
    calls.push({ url, init })
    return calls.length === 1
      ? page()
      : Response.json({ root: 'D:/Other', version: '1', jobs: [], rev: 0 })
  }
  try {
    await import('../chrome/background.js')
    assert.equal(
      listener(
        { type: 'download' },
        { id: 'test-extension', url: 'https://example.com/' },
        () => {},
      ),
      false,
    )
    assert.equal(calls.length, 0)
    const reply = await new Promise((resolve) =>
      listener(
        {
          type: 'download',
          origin,
          expectedRoot: 'D:/Media',
          url: 'https://example.com/v',
          mode: 'mp4',
        },
        {
          id: 'test-extension',
          url: 'chrome-extension://test-extension/popup.html',
        },
        resolve,
      ),
    )
    assert.equal(reply.error, 'destinationChanged')
    assert.equal(calls.length, 2)
    assert(calls.every((call) => !call.init.method))
    assert(!JSON.stringify(reply).includes(token))
  } finally {
    globalThis.chrome = previousChrome
    globalThis.fetch = previousFetch
  }
})
