export type JobStatus = 'queued' | 'running' | 'done' | 'error' | 'canceled'
export type DownloadMode = 'mp4' | 'mp3' | 'original' | 'cover' | 'image'

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
  complete?: boolean
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
  error_kind?: string
  error_hint?: string
  files: JobFile[]
  mode: DownloadMode
  created: number
  finished: number
  notes: string[]
  failed_items?: Array<{ index: number | null; url: string; title: string; error: string }>
  retry_failed_only?: boolean
}

export interface FileItem {
  name: string
  path: string
  size: number
  mtime: number
  downloaded?: number
  source?: string
  source_url?: string
  title?: string
  kind?: 'video' | 'audio' | 'image'
  complete?: boolean
  can_repair?: boolean
  favorite?: boolean
  collections?: string[]
  tags?: string[]
  note?: string
  thumbnail?: string
  playback?: { position: number; duration: number; finished: boolean; updated: number } | null
}

export interface LibraryCollection {
  id: string
  name: string
}

export interface SmartRules {
  kind?: 'video' | 'audio' | 'image'
  source?: string
  format?: string
  tag?: string
  favorite?: boolean
  recent_days?: number
  playback?: 'unplayed' | 'in_progress' | 'finished'
}

export interface SmartCollection extends LibraryCollection {
  rules: SmartRules
  builtin?: boolean
}

export interface RecoveryFile {
  id: string
  path: string
  removed: number
  size?: number
}

export interface LibraryScan {
  checked: number
  media_count: number
  entry_limit: number
  max_depth: number
  incomplete: boolean
  reasons: Array<'entry_limit' | 'depth_limit' | 'unreadable'>
}

export interface LibraryCheck {
  id: string
  root: string
  status: 'idle' | 'running' | 'cancelling' | 'cancelled' | 'done' | 'error'
  phase: 'inventory' | 'hashing' | 'verifying'
  checked: number
  total: number
  bytes_read: number
  error: string
  result: {
    media: { count: number; bytes: number }
    attachments: { count: number; bytes: number }
    recovery: { count: number; bytes: number }
    duplicate_bytes: number
    duplicates: Array<{
      id: string
      size: number
      files: Array<{ path: string; name: string; favorite: boolean }>
    }>
    missing: Array<{ path: string; title: string }>
    unknown: Array<{ path: string; reason: string }>
    incomplete: boolean
    reasons: string[]
    finished: number
  } | null
}

export interface LibraryBatchResult {
  processed: string[]
  failed: Array<{ item: string; error: string }>
  recovery_ids: string[]
}

export interface ProbeResult {
  kind?: 'video' | 'playlist' | 'page' | 'cover' | 'image'
  image_format?: string
  title?: string
  uploader?: string
  duration?: number
  thumbnail?: string
  heights?: number[]
  extractor?: string
  count?: number
  items?: string[]
  playlist_entries?: Array<{ index: number; title: string; duration?: number | null }>
  size?: { bytes: number | null; approximate: boolean }
  selection?: { mode: DownloadMode; quality: string; abr: number }
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
  queue_paused?: boolean
  queue_order?: string[]
  files?: FileItem[]
  library_scan?: LibraryScan
  collections?: LibraryCollection[]
  smart_collections?: SmartCollection[]
  /** The backend shows native desktop notifications itself (window mode). */
  desktop_notifications?: boolean
  /** Windows completion delivery runs independently of WebView polling. */
  native_notifications?: { enabled: boolean; available: boolean }
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
  setup_stage?: 'checking' | 'media' | 'sites' | 'verifying' | 'ready'
  status: 'idle' | 'running' | 'done' | 'error'
  lines: string[]
  before: string
  after: string
  error: string
  extras: string
}

export type ComponentExtras = 'default' | 'default,deno'

export type BackfillMode = 'none' | 'recent'

export interface SubscriptionFilters {
  include_keywords: string[]
  exclude_keywords: string[]
  exclude_live: boolean
  exclude_shorts: boolean
  min_duration: number
  max_duration: number
}

export interface Subscription {
  id: string
  url: string
  title: string
  enabled: boolean
  backfill: BackfillMode
  backfill_count: number
  filters: SubscriptionFilters
  mode: DownloadMode
  /** The full download settings this subscription uses for every video it queues. */
  options: DownloadOptions
  created: number
  last_checked: number
  last_error: string
  last_error_kind?: string
  total_queued: number
  total_filtered: number
  last_found: number
  last_queued: number
  last_filtered: number
  next_check: number | null
  checking: boolean
}

export interface SubscriptionsResponse {
  subscriptions: Subscription[]
  interval_seconds: number
}

export interface SubscriptionPreview {
  title: string
  total_candidates: number
  would_queue: number
  filtered: number
  items: Array<{
    id: string
    title: string
    url: string
    duration: number | null
    reason: string | null
    eligible: boolean
  }>
}
