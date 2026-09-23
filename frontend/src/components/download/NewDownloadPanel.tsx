import { ClipboardPaste, Download, FileUp, Loader2, Search } from 'lucide-react'
import { useCallback, useRef, useState } from 'react'
import { createJobs, probe } from '../../api/client'
import type { ToastFn } from '../../hooks/useToasts'
import { useUrlImport } from '../../hooks/useUrlImport'
import { BITRATES, QUALITIES, loadOptions, saveOptions } from '../../lib/options'
import { extractUrls, looksLikeTextFile, mergeUrls, readUrls } from '../../lib/urls'
import type { DownloadOptions, ProbeResult } from '../../types/api'
import { Button } from '../ui/Button'
import { Segmented } from '../ui/Segmented'
import { AdvancedSettings } from './AdvancedSettings'
import { ProbeCard } from './ProbeCard'

interface Props {
  playwright: boolean
  onToast: ToastFn
  /** Called after jobs were created, so the queue can refresh at once. */
  onAdded: () => void
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

export function NewDownloadPanel({ playwright, onToast, onAdded }: Props) {
  const [urls, setUrls] = useState('')
  const [options, setOptions] = useState<DownloadOptions>(loadOptions)
  const [probeResult, setProbeResult] = useState<ProbeResult | null>(null)
  const [busy, setBusy] = useState<'probe' | 'add' | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  const urlsRef = useRef(urls)
  urlsRef.current = urls

  const patch = useCallback((change: Partial<DownloadOptions>) => {
    setOptions((current) => {
      const next = { ...current, ...change }
      saveOptions(next)
      return next
    })
  }, [])

  const addUrls = useCallback(
    (found: string[], source: string) => {
      if (!found.length) return onToast('No links found in that', true)
      const { text, added } = mergeUrls(urlsRef.current, found)
      if (!added) return onToast('Those links are already in the box')
      setUrls(text)
      setProbeResult(null)
      onToast(`Added ${added} link${added === 1 ? '' : 's'} (${source})`)
    },
    [onToast],
  )

  const { dragging } = useUrlImport({ onUrls: addUrls, onProblem: (m) => onToast(m, true) })
  const links = readUrls(urls)
  const mp3 = options.mode === 'mp3'

  async function readClipboard() {
    try {
      addUrls(extractUrls(await navigator.clipboard.readText()), 'from the clipboard')
    } catch {
      onToast('The browser did not allow reading the clipboard. Press Ctrl+V instead.', true)
    }
  }

  async function importFiles(files: FileList | null) {
    if (!files) return
    const found: string[] = []
    for (const file of [...files].slice(0, 20)) {
      if (!looksLikeTextFile(file) || file.size > 2_000_000)
        onToast(`${file.name} was skipped (not a small text file)`, true)
      else found.push(...extractUrls(await file.text()))
    }
    if (files.length) addUrls([...new Set(found)], 'from files')
  }

  async function analyze() {
    if (!links.length) return onToast('Paste at least one link first', true)
    setBusy('probe')
    setProbeResult(null)
    try {
      setProbeResult(await probe(links[0], options))
    } catch (e) {
      setProbeResult({ error: e instanceof Error ? e.message : 'Could not analyze the link' })
    } finally {
      setBusy(null)
    }
  }

  async function start() {
    if (!links.length) return onToast('Paste at least one link first', true)
    setBusy('add')
    try {
      const { ids } = await createJobs(links, options)
      setUrls('')
      setProbeResult(null)
      onToast(`Added ${ids.length} download${ids.length === 1 ? '' : 's'} to the queue`)
      onAdded()
    } catch (e) {
      onToast(e instanceof Error ? e.message : 'Could not add the downloads', true)
    } finally {
      setBusy(null)
    }
  }

  return (
    <section className="card grid content-start gap-4" aria-labelledby="new-download">
      {dragging && (
        <div className="pointer-events-none fixed inset-0 z-40 grid place-items-center bg-emerald-950/85 text-xl font-semibold text-white">
          Drop to add the links inside
        </div>
      )}

      <div className="flex items-center justify-between">
        <div>
          <div className="eyebrow">New download</div>
          <h2 id="new-download" className="mt-1 text-lg font-semibold">
            Paste links to download
          </h2>
        </div>
        <span className="text-xs text-zinc-400">
          {links.length ? `${links.length} link${links.length === 1 ? '' : 's'}` : ''}
        </span>
      </div>

      <div className="grid gap-2">
        <textarea
          className="field min-h-32 resize-y font-mono text-sm leading-6"
          aria-label="Links to download, one per line"
          placeholder={
            'One link per line. Video pages, playlists, mp4 or m3u8 links.\nYou can also press Ctrl+V anywhere, or drop a text file here.'
          }
          spellCheck={false}
          value={urls}
          onChange={(e) => {
            setUrls(e.target.value)
            setProbeResult(null)
          }}
        />
        <div className="flex flex-wrap gap-2">
          <Button variant="ghost" className="!px-2.5 !py-1.5 text-xs" onClick={readClipboard}>
            <ClipboardPaste aria-hidden size={14} /> Read clipboard
          </Button>
          <Button
            variant="ghost"
            className="!px-2.5 !py-1.5 text-xs"
            onClick={() => fileInput.current?.click()}
          >
            <FileUp aria-hidden size={14} /> Import from file
          </Button>
          <input
            ref={fileInput}
            type="file"
            hidden
            multiple
            aria-label="Text files with links"
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
          quality={options.quality}
          onPickQuality={(quality) => patch({ mode: 'mp4', quality })}
        />
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="control">
          <span id="format-label">Format</span>
          <Segmented
            label="Output format"
            value={options.mode}
            onChange={(mode) => patch({ mode })}
            options={[
              { value: 'mp4', label: 'MP4 video' },
              { value: 'mp3', label: 'MP3 audio' },
            ]}
          />
        </div>
        {mp3 ? (
          <label className="control">
            <span>Audio quality</span>
            <select
              className="field"
              value={options.abr}
              onChange={(e) => patch({ abr: Number(e.target.value) })}
            >
              {BITRATES.map((b) => (
                <option key={b} value={b}>
                  {b} kbps
                </option>
              ))}
            </select>
          </label>
        ) : (
          <label className="control">
            <span>Highest video quality</span>
            <select
              className="field"
              value={options.quality}
              onChange={(e) => patch({ quality: e.target.value })}
            >
              <option value="best">Best available</option>
              {QUALITIES.map((q) => (
                <option key={q} value={String(q)}>
                  {q}p
                </option>
              ))}
              {options.quality !== 'best' && !QUALITIES.includes(Number(options.quality)) && (
                <option value={options.quality}>{options.quality}p</option>
              )}
            </select>
          </label>
        )}
      </div>

      <div className="grid gap-2">
        {!mp3 && (
          <>
            <Toggle checked={options.subs} onChange={(v) => patch({ subs: v })}>
              Download subtitles
            </Toggle>
            {options.subs && (
              <div className="ml-3 grid gap-2 border-l border-white/10 pl-3">
                <label className="control">
                  <span>Subtitle languages (comma separated, “all” for every language)</span>
                  <input
                    className="field"
                    value={options.sub_langs}
                    spellCheck={false}
                    onChange={(e) => patch({ sub_langs: e.target.value })}
                  />
                </label>
                <Toggle checked={options.auto_subs} onChange={(v) => patch({ auto_subs: v })}>
                  Use auto-generated subtitles when there are no manual ones
                </Toggle>
                <Toggle checked={options.embed_subs} onChange={(v) => patch({ embed_subs: v })}>
                  Embed into the MP4 (the .srt file is kept too)
                </Toggle>
              </div>
            )}
          </>
        )}
        <Toggle checked={options.cover} onChange={(v) => patch({ cover: v })}>
          Download the cover and embed it in the file
        </Toggle>
        {options.cover && (
          <div className="ml-3 border-l border-white/10 pl-3">
            <Toggle checked={options.keep_cover} onChange={(v) => patch({ keep_cover: v })}>
              Also keep a separate .jpg cover
            </Toggle>
          </div>
        )}
      </div>

      <AdvancedSettings options={options} onChange={patch} onToast={onToast} playwright={playwright} />

      <div className="grid grid-cols-[auto_1fr] gap-2">
        <Button onClick={analyze} disabled={busy !== null || !links.length}>
          {busy === 'probe' ? (
            <Loader2 aria-hidden size={16} className="animate-spin" />
          ) : (
            <Search aria-hidden size={16} />
          )}
          Analyze link
        </Button>
        <Button variant="primary" onClick={start} disabled={busy !== null || !links.length}>
          {busy === 'add' ? (
            <Loader2 aria-hidden size={16} className="animate-spin" />
          ) : (
            <Download aria-hidden size={16} />
          )}
          Start download
        </Button>
      </div>
    </section>
  )
}
