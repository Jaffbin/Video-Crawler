import { ClipboardPaste, Download, FileUp, FolderOpen, Loader2, Search } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { createJobs, probe, type ExistingDownload } from '../../api/client'
import { ExistingDownloads } from './ExistingDownloads'
import type { ToastFn } from '../../hooks/useToasts'
import { useUrlImport } from '../../hooks/useUrlImport'
import { extractUrls, looksLikeTextFile, mergeUrls, readUrls } from '../../lib/urls'
import type { DownloadOptions, ProbeResult } from '../../types/api'
import { Button } from '../ui/Button'
import { AdvancedSettings } from './AdvancedSettings'
import { FormatQualityFields } from './FormatQualityFields'
import { ProbeCard } from './ProbeCard'
import { useI18n } from '../../i18n'
import { audioQualityLabel } from '../../lib/options'
import { DownloadPresets } from './DownloadPresets'

interface Props {
  focusLinks?: number
  /** Download settings, owned by App so the subscription form always sees the same values. */
  options: DownloadOptions
  onOptionsChange: (patch: Partial<DownloadOptions>) => void
  playwright: boolean
  onToast: ToastFn
  /** Called after jobs were created, so the queue can refresh at once. */
  onAdded: () => void
  root?: string
  onChooseFolder?: () => Promise<void>
  changingFolder?: boolean
  folderChangeBlocked?: boolean
}

const Toggle = ({
  checked,
  onChange,
  disabled,
  children,
}: {
  checked: boolean
  onChange: (v: boolean) => void
  disabled?: boolean
  children: React.ReactNode
}) => (
  <label className="toggle-row">
    <input
      type="checkbox"
      checked={checked}
      disabled={disabled}
      onChange={(e) => onChange(e.target.checked)}
    />
    <span>{children}</span>
  </label>
)

export function NewDownloadPanel({
  focusLinks = 0,
  options,
  onOptionsChange: patch,
  playwright,
  onToast,
  onAdded,
  root,
  onChooseFolder,
  changingFolder = false,
  folderChangeBlocked = false,
}: Props) {
  const { t } = useI18n()
  const [urls, setUrls] = useState('')
  const [existing, setExisting] = useState<{
    urls: string[]
    options: DownloadOptions
    items: ExistingDownload[]
  } | null>(null)
  const linkField = useRef<HTMLTextAreaElement>(null)
  useEffect(() => {
    if (focusLinks) linkField.current?.focus()
  }, [focusLinks])
  const [probeResult, setProbeResult] = useState<ProbeResult | null>(null)
  const [selectedPlaylist, setSelectedPlaylist] = useState<number[] | null>(null)
  const probeRequest = useRef(0)
  const [busy, setBusy] = useState<'probe' | 'add' | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  const urlsRef = useRef(urls)
  urlsRef.current = urls

  const clearPreview = useCallback(() => {
    setProbeResult(null)
    setSelectedPlaylist(null)
  }, [])
  useEffect(() => {
    window.addEventListener('grab-preferences-restored', clearPreview)
    return () => window.removeEventListener('grab-preferences-restored', clearPreview)
  }, [clearPreview])

  const addUrls = useCallback(
    (found: string[], source: string) => {
      if (!found.length) return onToast(t('No links found in that'), true)
      const { text, added } = mergeUrls(urlsRef.current, found)
      if (!added) return onToast(t('Those links are already in the box'))
      setUrls(text)
      clearPreview()
      onToast(t('Added {count} links ({source})', { count: added, source }))
    },
    [onToast, t, clearPreview],
  )

  const { dragging } = useUrlImport({ onUrls: addUrls, onProblem: (m) => onToast(m, true) })
  const links = readUrls(urls)
  const selectedOptions =
    selectedPlaylist === null
      ? options
      : { ...options, items: selectedPlaylist.join(','), no_playlist: false }
  const mp3 = options.mode === 'mp3' || options.mode === 'original'
  const originalAudio = options.mode === 'original'
  const picture = options.mode === 'cover' || options.mode === 'image'
  const availableHeights = [...new Set(probeResult?.heights ?? [])]
    .filter((height) => Number.isFinite(height) && height > 0)
    .sort((a, b) => b - a)
  const outputSummary = picture
    ? t(
        options.mode === 'cover'
          ? 'Video cover · original image format'
          : 'Direct image · original image format',
      )
    : originalAudio
      ? t('Source audio · best available · no re-encoding')
      : mp3
        ? t('Audio · MP3 · {bitrate} kbps', { bitrate: options.abr }) +
          ' · ' +
          t(audioQualityLabel(options.abr))
        : t(
            options.quality === 'best'
              ? 'Video · MP4 · best available quality'
              : 'Video · MP4 · up to {quality}p',
            { quality: options.quality },
          )
  const playlistSummary =
    selectedPlaylist !== null
      ? t('{count} selected playlist entries', { count: selectedPlaylist.length })
      : selectedOptions.no_playlist
        ? t('Single video only; playlist disabled')
        : selectedOptions.items.trim()
          ? t('Playlist entries: {items}', { items: selectedOptions.items })
          : probeResult?.kind === 'playlist'
            ? t('All playlist entries')
            : t('If a link is a playlist, all entries will download')

  async function readClipboard() {
    try {
      addUrls(extractUrls(await navigator.clipboard.readText()), t('from the clipboard'))
    } catch {
      onToast(t('The browser did not allow reading the clipboard. Press Ctrl+V instead.'), true)
    }
  }

  async function importFiles(files: FileList | null) {
    if (!files) return
    const found: string[] = []
    for (const file of [...files].slice(0, 20)) {
      if (!looksLikeTextFile(file) || file.size > 2_000_000)
        onToast(t('{name} was skipped (not a small text file)', { name: file.name }), true)
      else found.push(...extractUrls(await file.text()))
    }
    if (files.length) addUrls([...new Set(found)], t('from files'))
  }

  async function analyze() {
    if (!links.length) return onToast(t('Paste at least one link first'), true)
    setBusy('probe')
    setProbeResult(null)
    setSelectedPlaylist(null)
    const request = ++probeRequest.current
    const input = urlsRef.current
    try {
      const result = await probe(links[0], options)
      if (request === probeRequest.current && input === urlsRef.current) setProbeResult(result)
    } catch (e) {
      if (request === probeRequest.current && input === urlsRef.current)
        setProbeResult({ error: e instanceof Error ? e.message : t('Could not analyze the link') })
    } finally {
      if (request === probeRequest.current) setBusy(null)
    }
  }

  async function start(action?: 'skip' | 'download') {
    if (!links.length) return onToast(t('Paste at least one link first'), true)
    if (selectedPlaylist?.length === 0) return onToast(t('Select at least one playlist entry.'), true)
    setBusy('add')
    try {
      const request = action && existing ? existing : { urls: links, options: selectedOptions }
      const {
        ids,
        duplicates = 0,
        existing: matches,
        skipped_existing = 0,
      } = await createJobs(request.urls, request.options, action)
      if (matches?.length) {
        setExisting({ ...request, items: matches })
        return
      }
      setExisting(null)
      setUrls('')
      clearPreview()
      if (ids.length) onToast(t('Added {count} downloads to the queue', { count: ids.length }))
      if (duplicates) onToast(t('Skipped {count} downloads already in the queue', { count: duplicates }))
      if (skipped_existing) onToast(t('Used {count} existing downloads', { count: skipped_existing }))
      if (ids.length || duplicates) onAdded()
    } catch (e) {
      onToast(e instanceof Error ? e.message : t('Could not add the downloads'), true)
    } finally {
      setBusy(null)
    }
  }

  return (
    <section className="card download-panel" aria-labelledby="new-download">
      {dragging && (
        <div className="pointer-events-none fixed inset-0 z-40 grid place-items-center bg-emerald-950/85 text-xl font-semibold text-[#fff]">
          {t('Drop to add the links inside')}
        </div>
      )}

      <div className="flex items-center justify-between">
        <div>
          <div className="eyebrow">{t('New download')}</div>
          <h2 id="new-download" className="mt-1 text-lg font-semibold">
            {t('Paste links to download')}
          </h2>
        </div>
        <span className="text-xs text-zinc-400">
          {links.length ? t('{count} links', { count: links.length }) : ''}
        </span>
      </div>

      <div className="download-workspace">
        <div className="download-inputs">
          <ol
            className="download-steps grid grid-cols-3 gap-2 text-xs text-zinc-400"
            aria-label={t('Download steps')}
          >
            {[t('Paste a link'), t('Preview (optional)'), t('Download and follow the queue')].map(
              (step, index) => (
                <li key={step} className="rounded-xl bg-white/[.025] p-3">
                  <span className="mr-2 text-emerald-300">{index + 1}</span>
                  {step}
                </li>
              ),
            )}
          </ol>

          <div className="grid gap-2">
            <textarea
              ref={linkField}
              className="field download-links resize-y font-mono text-sm leading-6"
              aria-label={t('Links to download, one per line')}
              placeholder={`${t('One link per line. Video pages, playlists, mp4 or m3u8 links.')}\n${t('You can also press Ctrl+V anywhere, or drop a text file here.')}`}
              spellCheck={false}
              value={urls}
              disabled={busy === 'add'}
              onChange={(e) => {
                setUrls(e.target.value)
                clearPreview()
              }}
            />
            <div className="flex flex-wrap gap-2">
              <Button variant="ghost" className="!px-2.5 !py-1.5 text-xs" onClick={readClipboard}>
                <ClipboardPaste aria-hidden size={14} /> {t('Read clipboard')}
              </Button>
              <Button
                variant="ghost"
                className="!px-2.5 !py-1.5 text-xs"
                onClick={() => fileInput.current?.click()}
              >
                <FileUp aria-hidden size={14} /> {t('Import from file')}
              </Button>
              <input
                ref={fileInput}
                type="file"
                hidden
                multiple
                aria-label={t('Text files with links')}
                accept=".txt,.csv,.md,.list,.url,.webloc,.json,.html,.htm,text/*"
                onChange={(e) => {
                  void importFiles(e.target.files)
                  e.target.value = ''
                }}
              />
            </div>
          </div>

          {probeResult && (
            <ProbeCard
              probe={probeResult}
              options={selectedOptions}
              selectedItems={selectedPlaylist}
              onPickItems={
                links.length === 1
                  ? (indices) => {
                      setSelectedPlaylist(indices)
                    }
                  : undefined
              }
              quality={options.quality}
              onPickQuality={(quality) => {
                if (options.mode !== 'mp4') {
                  patch({ mode: 'mp4', quality })
                  onToast(t('Switched to MP4 to use video quality'))
                  return
                }

                patch({ quality })
              }}
            />
          )}

          {links.length > 1 && (
            <p className="text-xs text-zinc-400">
              {t('Preview analyzes the first link; Start download adds all links.')}
            </p>
          )}
        </div>
        <div className="download-settings">
          <DownloadPresets
            options={options}
            disabled={busy !== null}
            onApply={(value) => {
              patch(value)
              clearPreview()
            }}
          />
          <FormatQualityFields
            options={selectedOptions}
            onChange={(change) => {
              if (busy === 'add') return
              if (change.mode) {
                probeRequest.current++
                setBusy(null)
                clearPreview()
              }
              patch(change)
            }}
            availableHeights={availableHeights}
            analyzed={!!probeResult}
            showAnalyzeHint
            allowImages
          />

          {picture && (
            <p className="text-xs text-zinc-400">
              {t(
                options.mode === 'cover'
                  ? 'Paste a video page or playlist link to save only its covers.'
                  : 'Paste direct image URLs, one per line. JPG, PNG, WebP, GIF and AVIF; up to 100 MiB each. Article pages and albums are not supported.',
              )}
            </p>
          )}

          {!picture && (
            <details className="download-extras">
              <summary>{t('Subtitles and cover')}</summary>
              <div className="mt-3 grid gap-2">
                {!mp3 && (
                  <>
                    <Toggle checked={options.subs} onChange={(v) => patch({ subs: v })}>
                      {t('Download subtitles')}
                    </Toggle>
                    {options.subs && (
                      <div className="ml-3 grid gap-2 border-l border-white/10 pl-3">
                        <label className="control">
                          <span>{t('Subtitle languages (comma separated, “all” for every language)')}</span>
                          <input
                            className="field"
                            value={options.sub_langs}
                            spellCheck={false}
                            onChange={(e) => patch({ sub_langs: e.target.value })}
                          />
                        </label>
                        <Toggle checked={options.auto_subs} onChange={(v) => patch({ auto_subs: v })}>
                          {t('Use auto-generated subtitles when there are no manual ones')}
                        </Toggle>
                        <Toggle checked={options.embed_subs} onChange={(v) => patch({ embed_subs: v })}>
                          {t('Embed into the MP4 (the .srt file is kept too)')}
                        </Toggle>
                      </div>
                    )}
                  </>
                )}
                {!mp3 && (
                  <p className="text-xs text-zinc-400">
                    {t('Website cover saved for Library and embedded when available.')}
                  </p>
                )}
                {mp3 && (
                  <Toggle checked={options.cover} onChange={(v) => patch({ cover: v })}>
                    {t(
                      originalAudio ? 'Save a separate cover' : 'Download the cover and embed it in the file',
                    )}
                  </Toggle>
                )}
                {mp3 && options.cover && !originalAudio && (
                  <div className="ml-3 border-l border-white/10 pl-3">
                    <Toggle checked={options.keep_cover} onChange={(v) => patch({ keep_cover: v })}>
                      {t('Also keep a separate .jpg cover')}
                    </Toggle>
                  </div>
                )}
              </div>
            </details>
          )}

          <AdvancedSettings
            options={options}
            onChange={(change) => {
              if ('items' in change) {
                setSelectedPlaylist(null)
              }
              if ('no_playlist' in change) {
                setSelectedPlaylist(null)
                setProbeResult(null)
              }
              patch(change)
            }}
            onToast={onToast}
            playwright={playwright}
          />
          {selectedPlaylist?.length === 0 && (
            <p role="alert" className="text-xs text-amber-200">
              {t('Select at least one playlist entry.')}
            </p>
          )}
        </div>
      </div>

      <div className="download-footer">
        <div className="download-summary min-w-0 text-sm" aria-label={t('Download summary')}>
          <p className="font-medium">
            {t('You will save')}: {outputSummary}
          </p>
          {!picture && (
            <p className="mt-1 text-zinc-400">
              {[
                options.subs && !mp3 ? t('Subtitles included') : '',
                !mp3 || (options.cover && !originalAudio) ? t('Cover embedded') : '',
                !mp3 || (options.cover && (options.keep_cover || originalAudio))
                  ? t('Separate cover included')
                  : '',
              ]
                .filter(Boolean)
                .join(' · ')}
            </p>
          )}
          {links.length > 0 && (
            <p className="mt-1 text-zinc-400">
              {t('{count} links', { count: links.length })}
              {options.mode !== 'image' && ` · ${playlistSummary}`}
            </p>
          )}
          {root && (
            <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-white/10 pt-3">
              <FolderOpen aria-hidden size={15} />
              <span className="min-w-0 flex-1 truncate" title={root}>
                {t('Save to')}: {root}
              </span>
              {onChooseFolder && (
                <Button
                  disabled={changingFolder || folderChangeBlocked || busy !== null}
                  onClick={onChooseFolder}
                >
                  {t(changingFolder ? 'Choosing folder…' : 'Change folder')}
                </Button>
              )}
            </div>
          )}
          {root && (
            <details className="mt-1 text-xs text-zinc-400">
              <summary className="cursor-pointer">{t('About save folders')}</summary>
              <p className="mt-1">
                {t(
                  folderChangeBlocked
                    ? 'Finish or cancel queued downloads to change the save folder.'
                    : 'Changing folders restarts the app. Library, Queue history and Auto-download settings belong to each folder. Existing files stay where they are.',
                )}
              </p>
            </details>
          )}
        </div>
        <div className="download-actions grid grid-cols-2 gap-2">
          <Button onClick={analyze} disabled={changingFolder || busy !== null || !links.length}>
            {busy === 'probe' ? (
              <Loader2 aria-hidden size={16} className="animate-spin" />
            ) : (
              <Search aria-hidden size={16} />
            )}
            {t('Analyze link')}
          </Button>
          <Button
            variant="primary"
            onClick={() => void start()}
            disabled={changingFolder || busy !== null || !links.length || selectedPlaylist?.length === 0}
          >
            {busy === 'add' ? (
              <Loader2 aria-hidden size={16} className="animate-spin" />
            ) : (
              <Download aria-hidden size={16} />
            )}
            {t('Start download')}
          </Button>
        </div>
      </div>
      <ExistingDownloads
        items={existing?.items || []}
        busy={busy === 'add'}
        onClose={() => setExisting(null)}
        onChoose={(action) => void start(action)}
        onError={(message) => onToast(message, true)}
      />
    </section>
  )
}
