import type {
  ComponentExtras,
  CookieStatus,
  DoctorResult,
  DownloadOptions,
  ProbeResult,
  StateResponse,
  UpdateStatus,
  YtdlpCheck,
} from '../types/api'
import { sanitizeOptions } from '../lib/options'

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

export const getState = (rev: number) => api<StateResponse>(`/api/state?rev=${rev}`)
export const probe = (url: string, options: DownloadOptions) =>
  post<ProbeResult>('/api/probe', { url, options: sanitizeOptions(options) })
export const createJobs = (urls: string[], options: DownloadOptions) =>
  post<{ ids: string[] }>('/api/jobs', { urls, options: sanitizeOptions(options) })
export const jobAction = (id: string, action: 'cancel' | 'retry' | 'remove') =>
  post<{ ok?: boolean; ids?: string[] }>(`/api/jobs/${id}/${action}`)
export const clearJobs = () => post<{ ok: boolean }>('/api/clear')
export const getLog = (id: string) => api<{ lines: string[] }>(`/api/jobs/${id}/log`)
/** Show a file (selected, where the OS supports it) or the download folder. */
export const openFolder = (path?: string) => post<{ ok: boolean }>('/api/open-folder', { path })
/** Open a file with the operating system's default app. */
export const openFile = (path: string) => post<{ ok: boolean }>('/api/open-file', { path })
export const getCookies = () => api<CookieStatus>('/api/cookies')
export const uploadCookies = (text: string) => post<CookieStatus>('/api/cookies', { text })
export const deleteCookies = () => post<CookieStatus>('/api/cookies/delete')
export const getDoctor = (net = false, force = true) =>
  api<DoctorResult>(`/api/doctor?${net ? 'net=1&' : ''}${force ? 'force=1' : ''}`)
export const checkYtdlp = (force = false) => api<YtdlpCheck>(`/api/ytdlp/check${force ? '?force=1' : ''}`)
export const startYtdlpUpdate = (extras: ComponentExtras = 'default') =>
  post<{ ok: boolean }>('/api/ytdlp/update', { extras })
export const getUpdateStatus = () => api<UpdateStatus>('/api/ytdlp/update-status')
export const restart = () => post<{ ok: boolean }>('/api/restart')
/** Asks the backend to show a native OS notification (window mode only; see StateResponse.desktop_notifications). */
export const notifyDesktop = (title: string, body: string) =>
  post<{ ok: boolean }>('/api/notify', { title, body })
