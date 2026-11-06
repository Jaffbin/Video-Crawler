import { AppError, checkedPage } from './connection.js'

export const MENU_PAGE = 'video-grabber-page'
export const MENU_LINK = 'video-grabber-link'
const PREFIX = 'download-intent:'
const MAX_AGE = 2 * 60 * 1000

/** All entry points lead to the same confirmation UI; no download is submitted here. */
export function createEntrypoints(api, now = Date.now) {
  const consuming = new Set()

  async function consume(id) {
    if (!/^[a-f0-9]{32}$/.test(id || '') || consuming.has(id))
      throw new AppError('selectionExpired')
    consuming.add(id)
    try {
      const key = PREFIX + id
      const stored = await api.storage.session.get(key)
      await api.storage.session.remove(key)
      const value = stored[key]
      if (
        !value ||
        !Number.isFinite(value.created) ||
        now() - value.created > MAX_AGE ||
        value.created > now()
      )
        throw new AppError('selectionExpired')
      if (value.error) return { error: 'unsupportedPage' }
      return {
        url: checkedPage(value.url),
        title: value.title,
        kind: value.kind,
      }
    } finally {
      consuming.delete(id)
    }
  }

  async function open(info, tab) {
    if (
      ![MENU_PAGE, MENU_LINK].includes(info.menuItemId) ||
      !Number.isInteger(tab?.id) ||
      !Number.isInteger(tab.windowId)
    )
      throw new AppError('invalidRequest')
    const kind = info.menuItemId === MENU_LINK ? 'link' : 'page'
    let value
    try {
      value = {
        url: checkedPage(
          kind === 'link' ? info.linkUrl : tab.url || info.pageUrl,
        ),
        title: kind === 'page' ? String(tab.title || '').slice(0, 500) : '',
        kind,
      }
    } catch {
      value = { error: 'unsupportedPage' }
    }
    const all = await api.storage.session.get(null)
    const entries = Object.entries(all)
      .filter(([key]) => key.startsWith(PREFIX))
      .sort((a, b) => (b[1]?.created || 0) - (a[1]?.created || 0))
    const obsolete = entries
      .filter(
        ([, item], index) =>
          index >= 19 || now() - (item?.created || 0) > MAX_AGE,
      )
      .map(([key]) => key)
    if (obsolete.length) await api.storage.session.remove(obsolete)
    const id = crypto.randomUUID().replaceAll('-', '')
    await api.storage.session.set({
      [PREFIX + id]: { ...value, created: now() },
    })
    const popup = 'popup.html?intent=' + id
    try {
      // A per-tab popup associates the clicked link with this invocation, not the next active tab.
      await api.action.setPopup({ tabId: tab.id, popup })
      await api.action.openPopup({ windowId: tab.windowId })
    } catch {
      // Older Chrome versions and unsupported window types still get an explicit confirmation page.
      await api.tabs.create({
        url: api.runtime.getURL(popup),
        windowId: tab.windowId,
      })
    } finally {
      await api.action.setPopup({ tabId: tab.id, popup: 'popup.html' })
    }
  }

  async function registerMenus() {
    await api.contextMenus.removeAll()
    api.contextMenus.create({
      id: MENU_PAGE,
      title: api.i18n.getMessage('sendPage'),
      contexts: ['page'],
      documentUrlPatterns: ['http://*/*', 'https://*/*'],
    })
    api.contextMenus.create({
      id: MENU_LINK,
      title: api.i18n.getMessage('sendLink'),
      contexts: ['link'],
      targetUrlPatterns: ['http://*/*', 'https://*/*'],
    })
  }
  return { open, consume, registerMenus }
}
