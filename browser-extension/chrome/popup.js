import { checkedPage } from './connection.js'

const $ = (id) => document.getElementById(id)
const t = (key, values = []) => chrome.i18n.getMessage(key, values) || key
document.documentElement.lang = chrome.i18n.getUILanguage()
for (const node of document.querySelectorAll('[data-i18n]'))
  node.textContent = t(node.dataset.i18n)
for (const node of document.querySelectorAll('[data-i18n-aria]'))
  node.setAttribute('aria-label', t(node.dataset.i18nAria))
let pageUrl = ''
let apps = []
let busy = false
let connecting = false
let pending = null

function error(code, detail = '') {
  $('error').textContent = t(code) + (detail ? '\n' + detail : '')
  $('error').hidden = false
}
function update() {
  $('controls').disabled = busy || !!pending
  const selected = apps.some((app) => app.origin === selection())
  $('download').disabled =
    busy || connecting || !!pending || !pageUrl || !selected
  for (const id of [
    'use-existing',
    'download-copy',
    'existing-library',
    'cancel-existing',
  ])
    $(id).disabled = busy
  $('queue').disabled = busy || connecting || !selected
  $('apps').disabled = busy || connecting || !!pending || apps.length < 2
  $('reconnect').disabled = busy || connecting || !!pending
  $('apply-port').disabled = busy || connecting || !!pending
  $('mode').disabled = busy || !!pending
  $('port').disabled = busy || connecting || !!pending
  $('video-quality').hidden = $('mode').value !== 'mp4'
  $('audio-quality').hidden = $('mode').value !== 'mp3'
  $('source-hint').hidden = $('mode').value !== 'original'
}
async function send(message) {
  let response
  try {
    response = await chrome.runtime.sendMessage(message)
  } catch {
    throw { error: 'appUnavailable' }
  }
  if (!response?.ok) throw response || { error: 'appUnavailable' }
  return response
}
function selection() {
  return $('apps').value
}
function destination() {
  const path = apps.find((app) => app.origin === selection())?.root || ''
  $('apps').title = path
  $('save-path').textContent = path
}
async function preferences() {
  try {
    await chrome.storage.local.set({
      mode: $('mode').value,
      quality: $('quality').value,
      abr: Number($('abr').value),
      preferredOrigin: selection(),
      port: $('port').value,
    })
  } catch {
    error('settingsNotSaved')
  }
}
async function discover() {
  connecting = true
  apps = []
  $('apps').replaceChildren()
  destination()
  $('error').hidden = true
  $('connection-status').textContent = t('connecting')
  update()
  try {
    const stored = await chrome.storage.local.get(['preferredOrigin'])
    const result = await send({ type: 'discover', port: $('port').value })
    apps = result.apps
    $('apps').replaceChildren(
      ...apps.map(
        (app) =>
          new Option(
            (app.root.split(/[\\/]/).filter(Boolean).at(-1) || app.root) +
              ' — ' +
              app.root,
            app.origin,
          ),
      ),
    )
    if (apps.some((app) => app.origin === stored.preferredOrigin))
      $('apps').value = stored.preferredOrigin
    else if (apps.length > 1) {
      $('apps').prepend(new Option(t('chooseApp'), ''))
      $('apps').value = ''
    }
    destination()
    $('connection-status').textContent = t(
      apps.length > 1 ? 'multipleApps' : apps.length ? 'connected' : 'openApp',
    )
  } catch (cause) {
    $('connection-status').textContent = t('openApp')
    error(cause.error || 'appUnavailable', cause.detail)
  } finally {
    connecting = false
    update()
  }
}
$('reconnect').addEventListener('click', discover)
$('apply-port').addEventListener('click', async () => {
  await discover()
  if (apps.length) await preferences()
})
$('apps').addEventListener('change', () => {
  destination()
  void preferences()
})
for (const id of ['mode', 'quality', 'abr'])
  $(id).addEventListener('change', () => {
    $('result').hidden = true
    update()
    void preferences()
  })
async function download(existingAction) {
  if (busy || connecting || !pageUrl || !apps.length) return
  busy = true
  $('result').hidden = true
  $('error').hidden = true
  update()
  try {
    const request =
      existingAction && pending
        ? pending
        : {
            type: 'download',
            origin: selection(),
            expectedRoot: apps.find((app) => app.origin === selection())?.root,
            url: pageUrl,
            mode: $('mode').value,
            quality: $('quality').value,
            abr: Number($('abr').value),
          }
    const result = await send({ ...request, existingAction })
    if (result.existing?.length) {
      pending = request
      $('existing-names').replaceChildren(
        ...result.existing.map((item) => {
          const entry = document.createElement('li')
          entry.textContent = item.name
          return entry
        }),
      )
      $('existing').hidden = false
      return
    }
    pending = null
    $('existing').hidden = true
    $('result').textContent = result.count
      ? t('added')
      : result.skippedExisting
        ? t('useExisting')
        : t('duplicate')
    $('result').hidden = false
    await preferences()
  } catch (cause) {
    error(cause.error || 'downloadUnconfirmed', cause.detail)
  } finally {
    busy = false
    update()
  }
}
$('download-form').addEventListener('submit', (event) => {
  event.preventDefault()
  if (!pending) void download()
})
$('use-existing').addEventListener('click', () => void download('skip'))
$('download-copy').addEventListener('click', () => void download('download'))
$('cancel-existing').addEventListener('click', () => {
  pending = null
  $('existing').hidden = true
  update()
})
$('existing-library').addEventListener('click', async () => {
  try {
    await send({ type: 'library', origin: selection() })
  } catch (cause) {
    error(cause.error || 'openQueueFailed')
  }
})
$('queue').addEventListener('click', async () => {
  busy = true
  $('error').hidden = true
  update()
  try {
    await send({ type: 'queue', origin: selection() })
  } catch (cause) {
    error(cause.error || 'openQueueFailed', cause.detail)
  } finally {
    busy = false
    update()
  }
})
$('shortcuts').addEventListener('click', () => {
  void chrome.tabs
    .create({ url: 'chrome://extensions/shortcuts' })
    .catch(() => error('shortcutSettingsUnavailable'))
})

async function initialize() {
  try {
    const saved = await chrome.storage.local.get([
      'mode',
      'quality',
      'abr',
      'port',
    ])
    if (['mp4', 'mp3', 'original'].includes(saved.mode))
      $('mode').value = saved.mode
    if (
      ['best', '2160', '1440', '1080', '720', '480', '360'].includes(
        saved.quality,
      )
    )
      $('quality').value = saved.quality
    if ([320, 192, 128].includes(saved.abr)) $('abr').value = String(saved.abr)
    if (saved.port) $('port').value = saved.port
    try {
      const intentId = new URLSearchParams(location.search).get('intent')
      if (intentId !== null) {
        const { intent } = await send({ type: 'consume-intent', id: intentId })
        if (intent.error) throw { error: intent.error }
        pageUrl = checkedPage(intent.url)
        $('page-title').textContent =
          intent.kind === 'link'
            ? t('selectedLink')
            : intent.title || t('currentPage')
      } else {
        const [tab] = await chrome.tabs.query({
          active: true,
          currentWindow: true,
        })
        $('page-title').textContent = tab?.title || t('currentPage')
        pageUrl = checkedPage(tab?.url || '')
      }
      $('page-title').title = $('page-title').textContent
    } catch (cause) {
      $('page-error').textContent = t(cause.error || 'unsupportedPage')
      $('page-error').hidden = false
    }
    $('page-url').value = pageUrl
    $('page-url').title = pageUrl
    update()
    try {
      const commands = await chrome.commands.getAll()
      const shortcut = commands.find(
        (command) => command.name === '_execute_action',
      )?.shortcut
      $('shortcut-hint').textContent = shortcut
        ? t('shortcutHint', [shortcut])
        : t('shortcutNotAssigned')
    } catch {
      $('shortcut-hint').textContent = t('shortcutNotAssigned')
    }
    await discover()
  } catch {
    error('appUnavailable')
    update()
  }
}
void initialize()
