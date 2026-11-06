import type {
  BackfillMode,
  SubscriptionFilters,
  Subscription,
  SubscriptionPreview,
  SubscriptionsResponse,
  ComponentExtras,
  CookieStatus,
  DoctorResult,
  DownloadOptions,
  ProbeResult,
  StateResponse,
  UpdateStatus,
  YtdlpCheck,
  RecoveryFile,
  SmartRules,
  LibraryCheck,
  LibraryBatchResult,
} from '../types/api'
import { sanitizeOptions } from '../lib/options'
import type { BrowserPreferences, BackupReview } from '../lib/backup'

const PLACEHOLDER = '__GRAB_TOKEN__'
let cachedToken: string | null = null

/**
 * The backend writes this run's random token into <meta name="grab-token">.
 * While developing with `npm run dev`, use ?t=<token> (or VITE_API_TOKEN) instead.
 */
export function getToken(): string {
  if (cachedToken !== null) return cachedToken
  const metaToken = document.querySelector<HTMLMetaElement>('meta[name="grab-token"]')?.content
  const queryToken = new URLSearchParams(location.search).get('t') ?? ''
  const envToken = (import.meta.env.VITE_API_TOKEN as string | undefined) ?? ''
  const token: string = metaToken && metaToken !== PLACEHOLDER ? metaToken : queryToken || envToken
  cachedToken = token
  return token
}

/** Test helper: forget the cached token. */
export function resetTokenCache(): void {
  cachedToken = null
}

/** Links (<a href>) cannot send headers, so the token travels in the query string. */
export function fileUrl(path: string): string {
  const encoded = path.split('/').map(encodeURIComponent).join('/')
  return `/files/${encoded}?t=${encodeURIComponent(getToken())}`
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  headers.set('X-Token', getToken())
  if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  const res = await fetch(path, { ...init, headers })
  const text = await res.text()
  let data: { error?: string } = {}
  try {
    data = text ? JSON.parse(text) : {}
  } catch {
    data = { error: text }
  }
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`)
  return data as T
}

const post = <T>(path: string, body: unknown = {}) =>
  api<T>(path, { method: 'POST', body: JSON.stringify(body) })

export const exportBackup = (preferences: BrowserPreferences) =>
  post<unknown>('/api/backup/export', { preferences })
export const previewBackup = (backup: unknown, current: BrowserPreferences) =>
  post<BackupReview>('/api/backup/preview', { backup, current })
export const restoreBackup = (backup: unknown, current: BrowserPreferences, review_token: string) =>
  post<BackupReview>('/api/backup/restore', { backup, current, review_token })

export const getState = (rev: number) => api<StateResponse>(`/api/state?rev=${rev}`)
export const probe = (url: string, options: DownloadOptions) =>
  post<ProbeResult>('/api/probe', { url, options: sanitizeOptions(options) })
export interface ExistingDownload {
  settings_match?: boolean
  profile?: { mode?: string; quality?: string; abr?: number }
  url: string
  path: string
  name: string
  profile_known: boolean
}
export const createJobs = (urls: string[], options: DownloadOptions, existingAction?: 'skip' | 'download') =>
  post<{ ids: string[]; duplicates?: number; existing?: ExistingDownload[]; skipped_existing?: number }>(
    '/api/jobs',
    { urls, options: sanitizeOptions(options), check_existing: true, existing_action: existingAction },
  )
export const jobAction = (id: string, action: 'cancel' | 'retry' | 'remove') =>
  post<{ ok?: boolean; ids?: string[]; duplicates?: boolean }>(`/api/jobs/${id}/${action}`)
export const clearJobs = () => post<{ ok: boolean }>('/api/clear')
export const batchJobs = (ids: string[], action: 'cancel' | 'retry' | 'remove') =>
  post<{ processed: string[]; skipped: string[] }>('/api/jobs/batch', { ids, action })
export const pauseQueue = (paused: boolean) => post<{ paused: boolean }>('/api/queue', { paused })
export const moveJob = (id: string, direction: 'up' | 'down') =>
  post<{ ok: boolean }>(`/api/jobs/${id}/move-${direction}`)
export const renameFile = (path: string, name: string) =>
  post<{ path: string }>('/api/library/rename', { path, name })
export const trashFile = (path: string) => post<{ id: string }>('/api/library/trash', { path })
export const organizeFiles = (
  items: string[],
  patch: { favorite?: boolean; collection_id?: string; remove?: boolean },
) =>
  post<{ processed: string[]; failed: Array<{ item: string; error: string }> }>('/api/library/organize', {
    items,
    ...patch,
  })
export const changeCollection = (action: 'create' | 'rename' | 'delete', name?: string, id?: string) =>
  post<{ id: string }>('/api/library/collections', { action, name, id })
export const changeSmartCollection = (
  action: 'create' | 'update' | 'delete',
  name?: string,
  id?: string,
  rules?: SmartRules,
) => post<{ id: string }>('/api/library/smart-collections', { action, name, id, rules })
export const getLibraryCheck = () => api<LibraryCheck>('/api/library/organizer')
export const libraryCheckAction = (action: 'start' | 'cancel') =>
  post<LibraryCheck>('/api/library/organizer', { action })
export const recycleCheckedDuplicates = (scan_id: string, items: string[]) =>
  post<LibraryBatchResult>('/api/library/organizer/recycle', { scan_id, items })
export const saveFileDetails = (path: string, tags: string[], note: string) =>
  post<{ ok: boolean }>('/api/library/details', { path, tags, note })
export const savePlayback = (path: string, position: number, duration: number, root?: string) =>
  api<{ ok: boolean }>('/api/library/playback', {
    method: 'POST',
    keepalive: true,
    body: JSON.stringify({ path, position, duration, root }),
  })

export function importLibraryFile(file: File, signal: AbortSignal, onProgress: (percent: number) => void) {
  return new Promise<{ path: string; duplicate: boolean }>((resolve, reject) => {
    const request = new XMLHttpRequest()
    const cancel = () => request.abort()
    const finish = () => signal.removeEventListener('abort', cancel)
    request.open('POST', `/api/library/import?name=${encodeURIComponent(file.name)}`)
    request.setRequestHeader('X-Token', getToken())
    request.setRequestHeader('Content-Type', 'application/octet-stream')
    request.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(Math.round((event.loaded / event.total) * 100))
    }
    request.onload = () => {
      finish()
      try {
        const body = JSON.parse(request.responseText)
        if (request.status < 200 || request.status >= 300)
          throw new Error(body.error || 'Could not import this file.')
        resolve(body)
      } catch (error) {
        reject(error)
      }
    }
    request.onerror = () => {
      finish()
      reject(new Error('Could not import this file. Please try again.'))
    }
    request.onabort = () => {
      finish()
      reject(new DOMException('Import canceled', 'AbortError'))
    }
    if (signal.aborted) return reject(new DOMException('Import canceled', 'AbortError'))
    signal.addEventListener('abort', cancel, { once: true })
    request.send(file)
  })
}
export const getRecoveryFiles = () => api<{ items: RecoveryFile[] }>('/api/library/trash')
export const restoreFile = (id: string) => post<{ path: string }>('/api/library/restore', { id })
export const purgeFile = (id: string) => post<{ ok: boolean }>('/api/library/purge', { id })
export const batchLibrary = (items: string[], action: 'trash' | 'restore' | 'purge') =>
  post<{ processed: string[]; failed: Array<{ item: string; error: string }>; recovery_ids?: string[] }>(
    '/api/library/batch',
    {
      items,
      action,
    },
  )
export const repairFile = (path: string) =>
  post<{ ids: string[]; duplicates: boolean }>('/api/library/repair', { path })
export const getLog = (id: string) => api<{ lines: string[] }>(`/api/jobs/${id}/log`)
/** Show a file (selected, where the OS supports it) or the download folder. */
export const openFolder = (path?: string) => post<{ ok: boolean }>('/api/open-folder', { path })
export const selectDownloadFolder = () =>
  post<{ canceled: boolean; restart_required: boolean; root: string }>('/api/download-folder/select')
/** Open a file with the operating system's default app. */
export const openFile = (path: string) => post<{ ok: boolean }>('/api/open-file', { path })
export const openExternalUrl = async (url: string) => {
  const result = await post<{ ok: boolean }>('/api/open-url', { url })
  if (!result.ok) throw new Error('Could not open it')
}
export const getCookies = () => api<CookieStatus>('/api/cookies')
export const uploadCookies = (text: string) => post<CookieStatus>('/api/cookies', { text })
export const deleteCookies = () => post<CookieStatus>('/api/cookies/delete')
export const getDoctor = (net = false, force = true) =>
  api<DoctorResult>(`/api/doctor?${net ? 'net=1&' : ''}${force ? 'force=1' : ''}`)
export const getSetupStatus = () =>
  api<{
    ready: boolean
    blocked: boolean
    can_install: boolean
    restart_required: boolean
    issues: string[]
  }>('/api/setup')
export const prepareSetup = () => post<{ ok: boolean }>('/api/setup')
export const retryWithBrowser = (id: string, browser: string) =>
  post<{ ids: string[]; duplicates: boolean }>(`/api/jobs/${id}/retry-browser`, { browser })
export const checkYtdlp = (force = false) => api<YtdlpCheck>(`/api/ytdlp/check${force ? '?force=1' : ''}`)
export const startYtdlpUpdate = (extras: ComponentExtras = 'default') =>
  post<{ ok: boolean }>('/api/ytdlp/update', { extras })
export const getUpdateStatus = () => api<UpdateStatus>('/api/ytdlp/update-status')
export const restart = () => post<{ ok: boolean }>('/api/restart')
/** Asks the backend to show a native OS notification (window mode only; see StateResponse.desktop_notifications). */
export const notifyDesktop = (title: string, body: string) =>
  post<{ ok: boolean }>('/api/notify', { title, body })
export const setNativeNotifications = (enabled: boolean) =>
  post<{ ok: boolean }>('/api/desktop/notifications', { enabled })

export const getSubscriptions = () => api<SubscriptionsResponse>('/api/subscriptions')
export const addSubscription = (
  url: string,
  options: DownloadOptions,
  backfill: BackfillMode,
  backfillCount: number,
  filters: SubscriptionFilters,
) =>
  post<Subscription>('/api/subscriptions', {
    url,
    options: sanitizeOptions(options),
    backfill,
    backfill_count: backfillCount,
    filters,
  })
export const updateSubscription = (
  id: string,
  patch: Partial<Pick<Subscription, 'enabled' | 'backfill' | 'backfill_count' | 'filters'>> & {
    options?: DownloadOptions
  },
) =>
  post<Subscription>(`/api/subscriptions/${id}/update`, {
    ...patch,
    // The backend replaces the whole settings object, so it must always be complete and valid.
    ...(patch.options ? { options: sanitizeOptions(patch.options) } : {}),
  })
export const checkSubscriptionNow = (id: string) =>
  post<{ ok: boolean }>(`/api/subscriptions/${id}/check-now`)
export const previewSubscription = (id: string, filters: SubscriptionFilters) =>
  post<SubscriptionPreview>(`/api/subscriptions/${id}/preview`, { filters })
export const removeSubscription = (id: string) => post<{ ok: boolean }>(`/api/subscriptions/${id}/remove`)
