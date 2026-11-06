import { ClipboardPaste, Download, ListVideo, Loader2 } from 'lucide-react'
import { useState } from 'react'
import { createJobs, type ExistingDownload } from '../../api/client'
import { ExistingDownloads } from './ExistingDownloads'
import { useStatePolling } from '../../hooks/useStatePolling'
import { loadOptions } from '../../lib/options'
import { extractUrls } from '../../lib/urls'
import { showDesktopMain, useDesktopLocale, useQuickAppearance } from '../../lib/desktop'
import { useI18n } from '../../i18n'
import { Button } from '../ui/Button'
import { FormatQualityFields } from './FormatQualityFields'
import type { DownloadOptions } from '../../types/api'

export function QuickDownloadApp() {
  const { state, online } = useStatePolling()
  useQuickAppearance()
  useDesktopLocale()
  return <QuickDownload root={state.root} online={online && !!state.root} />
}

export function QuickDownload({ root, online }: { root: string; online: boolean }) {
  const { t } = useI18n()
  const [text, setText] = useState('')
  const [existing, setExisting] = useState<{
    urls: string[]
    options: DownloadOptions
    items: ExistingDownload[]
  } | null>(null)
  const [options, setOptions] = useState<DownloadOptions>(() => {
    const saved = loadOptions()
    return {
      ...saved,
      mode: saved.mode === 'mp3' || saved.mode === 'original' ? saved.mode : ('mp4' as const),
    }
  })
  const [busy, setBusy] = useState(false)
  const [reading, setReading] = useState(false)
  const [error, setError] = useState('')
  const [added, setAdded] = useState<{ count: number; duplicates: number; existing?: number } | null>(null)
  function changeText(next: string) {
    setText(next)
    setError('')
    setAdded(null)
  }
  async function clipboard() {
    setReading(true)
    setError('')
    try {
      changeText(await navigator.clipboard.readText())
    } catch {
      setError(t('The browser did not allow reading the clipboard. Press Ctrl+V instead.'))
    } finally {
      setReading(false)
    }
  }
  async function start(action?: 'skip' | 'download') {
    const urls = extractUrls(text)
    if (urls.length !== 1) return setError(t('Paste one HTTP or HTTPS link for quick download.'))
    setBusy(true)
    setError('')
    setAdded(null)
    try {
      const connection = loadOptions()
      const request =
        action && existing
          ? existing
          : {
              urls,
              options: {
                ...connection,
                mode: options.mode,
                quality: options.quality,
                abr: options.abr,
                no_playlist: true,
                items: '',
                all_sniffed: false,
                subs: false,
                auto_subs: false,
                embed_subs: false,
                cover: false,
                keep_cover: false,
              },
            }
      const result = await createJobs(request.urls, request.options, action)
      if (result.existing?.length) {
        setExisting({ ...request, items: result.existing })
        return
      }
      setExisting(null)
      setAdded({
        count: result.ids.length,
        duplicates: result.duplicates || 0,
        existing: result.skipped_existing,
      })
      if (result.ids.length || result.duplicates || result.skipped_existing) setText('')
    } catch (cause) {
      setError(cause instanceof Error ? t(cause.message) : t('That did not work'))
    } finally {
      setBusy(false)
    }
  }
  return (
    <main className="quick-download mx-auto flex h-dvh min-h-0 max-w-xl flex-col gap-4 overflow-hidden p-4 sm:p-5">
      <header className="shrink-0">
        <h1 className="text-lg font-semibold">{t('Quick download')}</h1>
        <p className="mt-1 text-xs text-zinc-400">
          {t('Paste a link, choose video or audio, and keep browsing.')}
        </p>
      </header>
      <div className="quick-body grid min-h-0 flex-1 content-start gap-4 overflow-y-auto pr-1">
        <fieldset disabled={busy || reading} className="m-0 grid min-w-0 gap-4 border-0 p-0">
          <label className="control">
            <span>{t('Link to download')}</span>
            <textarea
              className="field min-h-20 resize-y"
              rows={2}
              value={text}
              onChange={(event) => changeText(event.target.value)}
              placeholder="https://…"
            />
          </label>
          <Button className="justify-self-start" onClick={clipboard}>
            <ClipboardPaste aria-hidden size={15} /> {t('Read clipboard')}
          </Button>
          <FormatQualityFields
            options={options}
            onChange={(patch) => {
              setOptions((current) => ({ ...current, ...patch }))
              setAdded(null)
            }}
          />
        </fieldset>
        <div className="rounded-xl bg-white/[.04] p-3 text-xs text-zinc-400">
          <p className="font-medium text-zinc-200">
            {t(
              options.mode === 'mp4'
                ? 'Single video · website cover included when available'
                : 'Single item only · no subtitles or cover',
            )}
          </p>
          <p className="mt-1">{t('Save to')}</p>
          <p className="mt-1 break-all text-zinc-200">{root || t('Connecting…')}</p>
        </div>
      </div>
      {!online && (
        <p role="alert" className="shrink-0 text-sm text-amber-200">
          {t('Connecting to the local app. Downloads will be available when it reconnects.')}
        </p>
      )}
      {error && (
        <p role="alert" className="shrink-0 text-sm text-red-300">
          {error}
        </p>
      )}
      {added && (
        <div role="status" className="grid shrink-0 gap-1 text-sm text-emerald-300">
          {added.count > 0 && <p>{t('Added {count} downloads to the queue', { count: added.count })}</p>}
          {!!added.existing && <p>{t('Used {count} existing downloads', { count: added.existing })}</p>}
          {added.duplicates > 0 && (
            <p>{t('Skipped {count} downloads already in the queue', { count: added.duplicates })}</p>
          )}
          <p className="text-xs text-zinc-400">
            {t('You can close this panel. Downloads continue in the background.')}
          </p>
        </div>
      )}
      <footer className="flex shrink-0 flex-wrap gap-2 pt-1">
        <Button
          variant="primary"
          className="flex-1"
          disabled={busy || reading || !online || !text.trim()}
          onClick={() => void start()}
        >
          {busy ? (
            <Loader2 aria-hidden size={16} className="animate-spin" />
          ) : (
            <Download aria-hidden size={16} />
          )}
          {t('Start download')}
        </Button>
        <Button
          onClick={() => {
            void showDesktopMain('queue').catch(() =>
              setError(t('Could not open the main window. Use the tray menu to try again.')),
            )
          }}
        >
          <ListVideo aria-hidden size={15} /> {t('View queue')}
        </Button>
      </footer>
      <ExistingDownloads
        error={error}
        items={existing?.items || []}
        busy={busy}
        onClose={() => setExisting(null)}
        onChoose={(action) => void start(action)}
        onError={setError}
      />
    </main>
  )
}
