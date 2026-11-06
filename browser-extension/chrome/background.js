import {
  AppError,
  checkedOrigin,
  connect,
  enqueue,
  openQueue,
  originForPort,
} from './connection.js'
import { createEntrypoints } from './entrypoints.js'

const connections = new Map()
const entrypoints = createEntrypoints(chrome)
const reportEntryError = () =>
  console.warn('Video Grabber could not open its confirmation panel.')
chrome.runtime.onInstalled.addListener(() => {
  void entrypoints.registerMenus().catch(reportEntryError)
})
chrome.runtime.onStartup.addListener(() => {
  void entrypoints.registerMenus().catch(reportEntryError)
})
chrome.contextMenus.onClicked.addListener((info, tab) => {
  void entrypoints.open(info, tab).catch(reportEntryError)
})

async function discover(customPort) {
  const ports = Array.from({ length: 20 }, (_, index) => 8765 + index)
  if (customPort !== undefined && customPort !== '')
    ports.push(Number(new URL(originForPort(customPort)).port))
  const results = await Promise.allSettled(
    [...new Set(ports)].map((port) => connect(originForPort(port))),
  )
  connections.clear()
  const apps = []
  for (const result of results) {
    if (result.status !== 'fulfilled') continue
    const { origin, root, window, version } = result.value
    connections.set(origin, result.value)
    apps.push({ origin, root, window, version })
  }
  return { apps }
}

async function dispatch(message) {
  if (!message || typeof message !== 'object')
    throw new AppError('invalidRequest')
  if (message.type === 'consume-intent')
    return { intent: await entrypoints.consume(message.id) }
  if (message.type === 'discover') return discover(message.port)
  const origin = checkedOrigin(message.origin)
  const connection = connections.get(origin) || (await connect(origin))
  if (message.type === 'download') {
    if (connection.root !== message.expectedRoot)
      throw new AppError('destinationChanged')
    const result = await enqueue(connection, message)
    connections.set(origin, result.connection)
    return {
      count: result.count,
      duplicates: result.duplicates,
      existing: result.existing,
      skippedExisting: result.skippedExisting,
    }
  }
  if (message.type === 'queue' || message.type === 'library') {
    const fresh = await connect(origin)
    connections.set(origin, fresh)
    const view = message.type === 'library' ? 'library' : 'queue'
    if (!(await openQueue(fresh, fetch, view)))
      await chrome.tabs.create({ url: origin + '/#/' + view })
    return { opened: true }
  }
  throw new AppError('invalidRequest')
}

chrome.runtime.onMessage.addListener((message, sender, reply) => {
  if (
    sender.id !== chrome.runtime.id ||
    !sender.url?.startsWith(chrome.runtime.getURL(''))
  )
    return false
  dispatch(message)
    .then((data) => reply({ ok: true, ...data }))
    .catch((error) => {
      reply({
        ok: false,
        error: error instanceof AppError ? error.code : 'appUnavailable',
        detail: error instanceof AppError ? error.detail : '',
      })
    })
  return true
})
