/** Local app protocol. Session credentials stay in service-worker memory only. */
export class AppError extends Error {
  constructor(code, detail = '') {
    super(code)
    this.code = code
    this.detail = detail
  }
}

export function originForPort(value) {
  const text = String(value)
  if (!/^\d{1,5}$/.test(text) || Number(text) < 1 || Number(text) > 65535)
    throw new AppError('invalidPort')
  return `http://127.0.0.1:${Number(text)}`
}

export function checkedOrigin(value) {
  let url
  try {
    url = new URL(value)
  } catch {
    throw new AppError('invalidConnection')
  }
  if (
    url.protocol !== 'http:' ||
    url.hostname !== '127.0.0.1' ||
    url.username ||
    url.password ||
    url.pathname !== '/' ||
    url.search ||
    url.hash
  )
    throw new AppError('invalidConnection')
  return originForPort(url.port || 80)
}

export function checkedPage(value) {
  try {
    const url = new URL(value)
    if (
      value.length > 8192 ||
      !['http:', 'https:'].includes(url.protocol) ||
      url.username ||
      url.password
    )
      throw new Error()
    return url.href
  } catch {
    throw new AppError('unsupportedPage')
  }
}

export function tokenFromPage(html) {
  for (const tag of html.match(/<meta\b[^>]*>/gi) || []) {
    if (!/\sname\s*=\s*["']grab-token["']/i.test(tag)) continue
    const token = tag.match(
      /\scontent\s*=\s*["']([A-Za-z0-9_-]{16,256})["']/i,
    )?.[1]
    if (token) return token
  }
  throw new AppError('notOurApp')
}

async function request(fetcher, url, init = {}, timeout = 2000) {
  try {
    return await fetcher(url, {
      ...init,
      cache: 'no-store',
      credentials: 'omit',
      redirect: 'error',
      signal: AbortSignal.timeout(timeout),
    })
  } catch {
    throw new AppError('appUnavailable')
  }
}

export async function connect(origin, fetcher = fetch) {
  origin = checkedOrigin(origin)
  const page = await request(fetcher, origin + '/')
  if (!page.ok) throw new AppError('notOurApp')
  const token = tokenFromPage(await page.text())
  const response = await request(fetcher, origin + '/api/state?rev=0', {
    headers: { 'X-Token': token },
  })
  if (!response.ok) throw new AppError('appUnavailable')
  let state
  try {
    state = await response.json()
  } catch {
    throw new AppError('notOurApp')
  }
  if (
    typeof state.root !== 'string' ||
    !state.root ||
    typeof state.version !== 'string' ||
    !Array.isArray(state.jobs) ||
    !Number.isFinite(state.rev)
  )
    throw new AppError('notOurApp')
  return {
    origin,
    token,
    root: state.root,
    window: state.window === true,
    version: state.version,
  }
}

export function downloadOptions(input) {
  const mode = ['mp4', 'mp3', 'original'].includes(input.mode)
    ? input.mode
    : null
  if (!mode) throw new AppError('invalidFormat')
  const quality = [
    'best',
    '2160',
    '1440',
    '1080',
    '720',
    '480',
    '360',
  ].includes(String(input.quality))
    ? String(input.quality)
    : 'best'
  const abr = [320, 256, 192, 128, 96].includes(Number(input.abr))
    ? Number(input.abr)
    : 192
  return {
    mode,
    quality,
    abr,
    no_playlist: true,
    items: '',
    subs: false,
    auto_subs: false,
    embed_subs: false,
    cover: false,
    keep_cover: false,
    all_sniffed: false,
  }
}

export async function enqueue(connection, input, fetcher = fetch) {
  const body = JSON.stringify({
    urls: [checkedPage(input.url)],
    options: downloadOptions(input),
    check_existing: true,
    existing_action: ['skip', 'download'].includes(input.existingAction)
      ? input.existingAction
      : undefined,
  })
  const post = async (current) => {
    try {
      return await request(
        fetcher,
        checkedOrigin(current.origin) + '/api/jobs',
        {
          method: 'POST',
          headers: {
            'X-Token': current.token,
            'Content-Type': 'application/json',
          },
          body,
        },
        15000,
      )
    } catch {
      throw new AppError('downloadUnconfirmed')
    }
  }
  let current = connection
  let response = await post(current)
  // An explicit 401 means no task was created. Other failures must never retry a POST automatically.
  if (response.status === 401) {
    current = await connect(current.origin, fetcher)
    if (current.root !== connection.root)
      throw new AppError('destinationChanged')
    response = await post(current)
  }
  let result
  try {
    result = await response.json()
  } catch {
    throw new AppError('downloadUnconfirmed')
  }
  if (!response.ok)
    throw new AppError(
      'downloadFailed',
      typeof result.error === 'string' ? result.error : '',
    )
  if (
    !Array.isArray(result.ids) ||
    !result.ids.every((id) => typeof id === 'string')
  )
    throw new AppError('downloadUnconfirmed')
  return {
    connection: current,
    count: result.ids.length,
    duplicates:
      Number.isInteger(result.duplicates) && result.duplicates > 0
        ? result.duplicates
        : 0,
    existing: Array.isArray(result.existing)
      ? result.existing
          .filter((item) => item && typeof item.name === 'string')
          .map((item) => ({ name: item.name }))
      : [],
    skippedExisting: Number.isInteger(result.skipped_existing)
      ? result.skipped_existing
      : 0,
  }
}

export async function openQueue(connection, fetcher = fetch, view = 'queue') {
  const response = await request(
    fetcher,
    checkedOrigin(connection.origin) + '/api/desktop/show',
    {
      method: 'POST',
      headers: {
        'X-Token': connection.token,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ view: view === 'library' ? 'library' : 'queue' }),
    },
    12000,
  )
  if (response.status === 404) return false // Compatibility with an older running app.
  if (!response.ok) throw new AppError('openQueueFailed')
  const result = await response.json()
  return result.opened === true
}
