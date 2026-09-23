export type JobStatus = 'queued' | 'running' | 'done' | 'error' | 'canceled'
export type DownloadMode = 'mp4' | 'mp3'

export interface DownloadOptions {
  mode: DownloadMode
  quality: string
  abr: number
  subs: boolean
  sub_langs: string
  auto_subs: boolean
  embed_subs: boolean
  cover: boolean
  keep_cover: boolean
  no_playlist: boolean
  items: string
  archive: boolean
  cookies_from_browser: string
  use_cookies_file: boolean
  referer: string
  proxy: string
  limit_rate: string
  sleep: number
  threads: number
  all_sniffed: boolean
  js_render: boolean
  js_wait: number
}

export interface JobFile {
  name: string
  path: string
}

export interface Job {
  id: string
  url: string
  status: JobStatus
  stage: string
  title: string
  percent: number
  speed: string
  eta: string
  item: string
  error: string
  files: JobFile[]
  mode: DownloadMode
  created: number
  finished: number
  notes: string[]
}

export interface FileItem {
  name: string
  path: string
  size: number
  mtime: number
}

export interface ProbeResult {
  kind?: 'video' | 'playlist' | 'page'
  title?: string
  uploader?: string
  duration?: number
  thumbnail?: string
  heights?: number[]
  extractor?: string
  count?: number
  items?: string[]
  sources?: string[]
  rendered?: boolean
  error?: string
}

export interface StateResponse {
  version: string
  ffmpeg: boolean
  playwright: boolean
  root: string
  rev: number
  jobs: Job[]
  files?: FileItem[]
  /** The backend shows native desktop notifications itself (window mode). */
  desktop_notifications?: boolean
  /** The UI runs inside the desktop window rather than a browser tab. */
  window?: boolean
}

export interface CookieStatus {
  present: boolean
  cookies?: number
  domain_count?: number
  expired?: number
  has_youtube?: boolean
  youtube_login?: boolean
  has_bilibili?: boolean
  bilibili_login?: boolean
}

export type CheckStatus = 'ok' | 'info' | 'warn' | 'error'

export interface DoctorCheck {
  id: string
  label: string
  status: CheckStatus
  detail: string
  fix?: string
  action?: 'install_components' | 'install_default' | ''
}

export interface DoctorResult {
  checks: DoctorCheck[]
  report: string
  net: boolean
}

export interface YtdlpCheck {
  running: string
  installed: string
  latest?: string | null
  newer?: boolean
  needs_restart: boolean
  error?: string
}

export interface UpdateStatus {
  status: 'idle' | 'running' | 'done' | 'error'
  lines: string[]
  before: string
  after: string
  error: string
  extras: string
}

export type ComponentExtras = 'default' | 'default,deno'
