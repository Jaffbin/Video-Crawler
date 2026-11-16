import { FileText, Search } from 'lucide-react'
import { useEffect, useState } from 'react'
import {
  cancelTranscription,
  fileUrl,
  getTranscription,
  searchTranscripts,
  setTranscriptionAutomation,
  setTranscriptionModel,
} from '../../api/client'
import type { ToastFn } from '../../hooks/useToasts'
import { useI18n } from '../../i18n'
import type { FileItem, TranscriptionStatus, TranscriptResult } from '../../types/api'
import { Button } from '../ui/Button'
import { Modal } from '../ui/Modal'

/** Approximate first-use downloads, so people can choose before waiting on a large model. */
const MODEL_SIZES: Record<string, string> = {
  tiny: '75 MB',
  base: '145 MB',
  small: '465 MB',
  medium: '1.5 GB',
  'large-v3-turbo': '1.6 GB',
}

export function timestamp(seconds: number) {
  const total = Math.floor(seconds)
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = String(total % 60).padStart(2, '0')
  return h ? `${h}:${String(m).padStart(2, '0')}:${s}` : `${m}:${s}`
}

/**
 * Search what was said in transcribed audio and video, follow transcription progress and choose
 * the speech model. Results open the media at the moment the words were spoken.
 */
export function Transcripts({ files, onToast }: { files: FileItem[]; onToast: ToastFn }) {
  const { t } = useI18n()
  const [open, setOpen] = useState(false)
  const [status, setStatus] = useState<TranscriptionStatus | null>(null)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<TranscriptResult[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const active = Object.values(status?.items ?? {}).some(
    (item) => item.status === 'queued' || item.status === 'running',
  )

  useEffect(() => {
    if (!open) return
    let stop = false
    const load = () =>
      getTranscription()
        .then((result) => {
          if (!stop) setStatus(result)
        })
        .catch((reason) => {
          if (!stop) setError(t(reason instanceof Error ? reason.message : 'That did not work'))
        })
    void load()
    // Progress changes while a file is transcribed; nothing pushes it, so check every two seconds.
    const timer = active ? window.setInterval(() => void load(), 2000) : undefined
    return () => {
      stop = true
      if (timer) window.clearInterval(timer)
    }
  }, [open, active, t])

  async function run(action: () => Promise<void>) {
    setBusy(true)
    setError('')
    try {
      await action()
    } catch (reason) {
      setError(t(reason instanceof Error ? reason.message : 'That did not work'))
    } finally {
      setBusy(false)
    }
  }

  const names = new Map(files.map((file) => [file.path, file.title || file.name]))
  const working = Object.entries(status?.items ?? {}).filter(
    ([, item]) => item.status === 'queued' || item.status === 'running' || item.status === 'error',
  )

  return (
    <>
      <Button variant="ghost" onClick={() => setOpen(true)}>
        <FileText aria-hidden size={14} />
        {t('Transcripts')}
      </Button>
      <Modal open={open} title={t('Transcripts')} onClose={() => setOpen(false)} wide>
        <div className="grid gap-4">
          {status && !status.available && (
            <p className="rounded-xl bg-amber-500/[.08] px-3 py-2 text-sm text-amber-100">
              {t(status.install_hint)}
            </p>
          )}
          <p className="text-sm text-zinc-400">
            {t(
              'Choose Transcribe in a video or audio file’s More menu. Speech is recognized on this computer, and the transcript is saved next to the file.',
            )}
          </p>
          <form
            className="flex flex-wrap gap-2"
            role="search"
            onSubmit={(event) => {
              event.preventDefault()
              void run(async () => setResults((await searchTranscripts(query)).results))
            }}
          >
            <label className="relative min-w-0 flex-1 basis-56">
              <span className="sr-only">{t('Search what was said')}</span>
              <Search
                aria-hidden
                size={15}
                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500"
              />
              <input
                className="field !pl-9"
                type="search"
                placeholder={t('Search what was said')}
                value={query}
                maxLength={200}
                onChange={(event) => setQuery(event.target.value)}
              />
            </label>
            <Button type="submit" variant="primary" disabled={busy || !query.trim()}>
              {t('Search')}
            </Button>
          </form>
          {results && (
            <section aria-label={t('Search results')} className="grid gap-3">
              {results.length === 0 ? (
                <p className="text-sm text-zinc-400">{t('No transcript mentions this.')}</p>
              ) : (
                results.map((result) => (
                  <article key={result.path} className="grid gap-1 rounded-xl bg-white/[.04] p-3">
                    <h3 className="break-words text-sm font-medium text-zinc-100">{result.title}</h3>
                    <ul className="grid gap-1">
                      {result.hits.map((hit) => (
                        <li key={hit.start} className="flex min-w-0 gap-3 text-sm">
                          <a
                            className="shrink-0 tabular-nums text-sky-300 hover:underline"
                            href={`${fileUrl(result.path)}#t=${hit.start}`}
                            target="_blank"
                            rel="noreferrer"
                            aria-label={t('Play {name} from {time}', {
                              name: result.title,
                              time: timestamp(hit.start),
                            })}
                          >
                            {timestamp(hit.start)}
                          </a>
                          <span className="min-w-0 break-words text-zinc-300">{hit.text}</span>
                        </li>
                      ))}
                    </ul>
                  </article>
                ))
              )}
            </section>
          )}
          {working.length > 0 && (
            <section aria-label={t('Transcription progress')} className="grid gap-2">
              <div className="flex items-center gap-2">
                <h3 className="min-w-0 flex-1 text-sm font-semibold">{t('Transcription progress')}</h3>
                {active && (
                  <Button
                    disabled={busy}
                    onClick={() =>
                      void run(async () => {
                        setStatus(await cancelTranscription())
                        onToast(t('Transcription stopped'))
                      })
                    }
                  >
                    {t('Stop transcribing')}
                  </Button>
                )}
              </div>
              <ul className="grid gap-1 text-sm">
                {working.map(([path, item]) => (
                  <li key={path} className="flex min-w-0 flex-wrap gap-x-2">
                    <span className="min-w-0 flex-1 truncate text-zinc-200">{names.get(path) ?? path}</span>
                    <span className={item.status === 'error' ? 'text-amber-300' : 'text-zinc-400'}>
                      {item.status === 'running'
                        ? t('Transcribing {percent}%', { percent: Math.round(item.percent) })
                        : item.status === 'queued'
                          ? t('Waiting')
                          : item.error}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          )}
          {status && (
            <label className="control">
              <span>{t('Speech model')}</span>
              <select
                className="field"
                value={status.model}
                disabled={busy}
                onChange={(event) => {
                  const model = event.target.value
                  void run(async () => setStatus(await setTranscriptionModel(model)))
                }}
              >
                {status.models.map((model) => (
                  <option key={model} value={model}>
                    {model} ({MODEL_SIZES[model] ?? ''})
                  </option>
                ))}
              </select>
            </label>
          )}
          {status && (
            <p className="-mt-2 text-xs text-zinc-400">
              {t('Larger models are more accurate but slower. The first use downloads the model once.')}
            </p>
          )}
          {status && (
            <fieldset className="grid gap-2" disabled={busy}>
              <legend className="sr-only">{t('Automatic transcription')}</legend>
              <label className="toggle-row">
                <input
                  type="checkbox"
                  checked={status.auto}
                  onChange={(event) => {
                    const auto = event.target.checked
                    void run(async () =>
                      setStatus(await setTranscriptionAutomation(auto, status.reuse_subtitles)),
                    )
                  }}
                />
                <span>{t('Transcribe new video and audio downloads automatically')}</span>
              </label>
              {status.auto && (
                <label className="toggle-row ml-6">
                  <input
                    type="checkbox"
                    checked={status.reuse_subtitles}
                    onChange={(event) => {
                      const reuse = event.target.checked
                      void run(async () => setStatus(await setTranscriptionAutomation(true, reuse)))
                    }}
                  />
                  <span>{t('Use the site’s subtitles instead when a download has them')}</span>
                </label>
              )}
            </fieldset>
          )}
          {error && (
            <p role="alert" className="text-sm text-red-300">
              {error}
            </p>
          )}
        </div>
      </Modal>
    </>
  )
}
