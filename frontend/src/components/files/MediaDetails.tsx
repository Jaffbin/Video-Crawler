import { ExternalLink, FolderOpen } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import {
  fileUrl,
  openExternalUrl,
  openFile,
  openFolder,
  saveFileDetails,
  savePlayback,
} from '../../api/client'
import type { ToastFn } from '../../hooks/useToasts'
import { useI18n } from '../../i18n'
import { fileKind } from '../../lib/library'
import { formatBytes, formatDate, formatDuration } from '../../lib/utils'
import type { FileItem, LibraryCollection } from '../../types/api'
import { Button } from '../ui/Button'
import { Modal } from '../ui/Modal'
import type { AudioPlayerController } from '../../lib/audioPlayer'

interface Props {
  audioPlayer?: AudioPlayerController
  file: FileItem
  collections: LibraryCollection[]
  autoPlay: boolean
  windowMode: boolean
  onClose: () => void
  onRefresh: () => void
  onToast: ToastFn
}

export function MediaDetails({
  audioPlayer,
  file,
  collections,
  autoPlay,
  windowMode,
  onClose,
  onRefresh,
  onToast,
}: Props) {
  const { t } = useI18n()
  const kind = fileKind(file)
  const media = useRef<HTMLMediaElement | null>(null)
  useEffect(() => {
    if (kind !== 'video' || !audioPlayer) return
    const pause = () => media.current?.pause()
    window.addEventListener('grab-audio-started', pause)
    return () => window.removeEventListener('grab-audio-started', pause)
  }, [kind, audioPlayer])
  const [tags, setTags] = useState((file.tags || []).join(', '))
  const [note, setNote] = useState(file.note || '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [unsupported, setUnsupported] = useState(false)
  const latest = useRef<{ position: number; duration: number } | null>(null)
  const sent = useRef('')
  const lastSave = useRef(0)
  const tracking = useRef(false)
  const pending = useRef(Promise.resolve())
  const saver = useRef(() => {})
  saver.current = () => {
    const progress = latest.current
    if (!progress) return
    const signature = `${progress.position}/${progress.duration}`
    if (signature === sent.current) return
    sent.current = signature
    pending.current = pending.current.then(async () => {
      try {
        await savePlayback(file.path, progress.position, progress.duration)
        onRefresh()
      } catch (problem) {
        sent.current = ''
        onToast(t(problem instanceof Error ? problem.message : 'Could not save playback progress.'), true)
      }
    })
  }
  useEffect(() => () => saver.current(), [])

  function updateProgress(element: HTMLMediaElement, force = false) {
    if (!tracking.current) return
    if (!Number.isFinite(element.duration) || element.duration <= 0 || element.duration > 7 * 86400) return
    if (!Number.isFinite(element.currentTime)) return
    latest.current = {
      position: Math.max(0, Math.min(element.duration, element.currentTime)),
      duration: element.duration,
    }
    if (force || Date.now() - lastSave.current > 5000) {
      lastSave.current = Date.now()
      saver.current()
    }
  }
  function loaded(element: HTMLMediaElement) {
    const saved = file.playback
    if (saved && !saved.finished && Number.isFinite(element.duration) && saved.position < element.duration) {
      element.currentTime = saved.position
    }
  }
  async function save() {
    setSaving(true)
    setError('')
    try {
      await saveFileDetails(
        file.path,
        tags
          .split(/[,，]/)
          .map((tag) => tag.trim())
          .filter(Boolean),
        note,
      )
      onRefresh()
      onToast(t('Tags and note saved'))
    } catch (problem) {
      setError(t(problem instanceof Error ? problem.message : 'Could not save file details.'))
    } finally {
      setSaving(false)
    }
  }
  const playerProps = {
    controls: true,
    autoPlay,
    preload: 'metadata',
    src: fileUrl(file.path),
    onPlay: () => {
      if (kind === 'video') audioPlayer?.pause()
      tracking.current = true
    },
    onLoadedMetadata: (event: React.SyntheticEvent<HTMLMediaElement>) => loaded(event.currentTarget),
    onTimeUpdate: (event: React.SyntheticEvent<HTMLMediaElement>) => updateProgress(event.currentTarget),
    onPause: (event: React.SyntheticEvent<HTMLMediaElement>) => updateProgress(event.currentTarget, true),
    onSeeked: (event: React.SyntheticEvent<HTMLMediaElement>) => updateProgress(event.currentTarget, true),
    onEnded: (event: React.SyntheticEvent<HTMLMediaElement>) => {
      const element = event.currentTarget
      if (
        tracking.current &&
        Number.isFinite(element.duration) &&
        element.duration > 0 &&
        element.duration <= 7 * 86400
      )
        latest.current = { position: element.duration, duration: element.duration }
      saver.current()
    },
    onError: () => setUnsupported(true),
  }
  return (
    <Modal open onClose={onClose} title={t('Media details')} wide>
      <div className="grid min-w-0 gap-4">
        <h3 className="break-words text-lg font-semibold">{file.title || file.name}</h3>
        {file.complete === false ? (
          <p className="text-sm text-amber-300">{t('Retry the original task to finish processing.')}</p>
        ) : kind === 'image' ? (
          <img
            className="mx-auto max-h-[40vh] max-w-full object-contain"
            src={fileUrl(file.path)}
            alt={file.name}
            onError={() => setUnsupported(true)}
          />
        ) : kind === 'audio' && audioPlayer ? (
          <div className="grid gap-2 rounded-xl bg-white/5 p-3">
            <p className="text-sm text-zinc-400">
              {t('Audio plays in the bottom bar and continues when you close this panel.')}
            </p>
            <div className="flex flex-wrap gap-2">
              <Button onClick={() => audioPlayer.playFile(file)}>{t('Play audio')}</Button>
              <Button
                onClick={() => {
                  const count = audioPlayer.enqueue([file])
                  onToast(
                    t(
                      'Added {count} tracks to playback queue. Existing tracks are kept once; the limit is 500.',
                      { count },
                    ),
                  )
                }}
              >
                {t('Add to playback queue')}
              </Button>
            </div>
          </div>
        ) : kind === 'audio' ? (
          <audio
            {...playerProps}
            ref={(element) => {
              media.current = element
            }}
            className="w-full"
            aria-label={t('Audio preview')}
          />
        ) : (
          <video
            {...playerProps}
            ref={(element) => {
              media.current = element
            }}
            playsInline
            poster={file.thumbnail ? fileUrl(file.thumbnail) : undefined}
            className="max-h-[40vh] w-full rounded-xl bg-black"
            aria-label={t('Video preview')}
          />
        )}
        {unsupported && (
          <p role="alert" className="text-sm text-amber-300">
            {t('This format cannot be previewed here. Open it with your system player or save a copy.')}
          </p>
        )}
        {kind !== 'image' && file.complete !== false && (
          <p className="text-xs text-zinc-400">
            {t('Progress is saved for playback inside this app. External players do not report progress.')}
          </p>
        )}
        {file.playback && (
          <p className="text-sm text-zinc-300">
            {file.playback.finished
              ? t('Finished playback')
              : t('Continue at {time}', { time: formatDuration(file.playback.position) })}
          </p>
        )}
        <div className="flex flex-wrap gap-2">
          {windowMode && (
            <Button onClick={() => openFile(file.path).catch((problem) => onToast(String(problem), true))}>
              {t('Open in system player')}
            </Button>
          )}
          <a className="action-btn" href={fileUrl(file.path)} download={file.name}>
            {t('Download')}
          </a>
          <Button onClick={() => openFolder(file.path).catch((problem) => onToast(String(problem), true))}>
            <FolderOpen aria-hidden size={15} />
            {t('Show in folder')}
          </Button>
          {file.source_url &&
            (windowMode ? (
              <Button
                onClick={() =>
                  openExternalUrl(file.source_url!).catch((problem) => onToast(String(problem), true))
                }
              >
                <ExternalLink aria-hidden size={15} />
                {t('Original page')}
              </Button>
            ) : (
              <a className="action-btn" href={file.source_url} target="_blank" rel="noreferrer">
                {t('Original page')}
              </a>
            ))}
        </div>
        <dl className="media-facts text-sm">
          <dt>{t('Filename')}</dt>
          <dd className="break-all">{file.name}</dd>
          <dt>{t('Source')}</dt>
          <dd>{file.source === 'local' ? t('Local file') : file.source || t('Unknown source')}</dd>
          <dt>{t('File size')}</dt>
          <dd>{formatBytes(file.size)}</dd>
          <dt>{t('Added')}</dt>
          <dd>{formatDate(file.downloaded ?? file.mtime)}</dd>
          <dt>{t('Collection')}</dt>
          <dd>
            {collections
              .filter((collection) => file.collections?.includes(collection.id))
              .map((collection) => collection.name)
              .join(', ') || '—'}
          </dd>
        </dl>
        <label className="control">
          <span>{t('Tags (comma separated)')}</span>
          <input
            className="field"
            value={tags}
            onChange={(event) => setTags(event.target.value)}
            maxLength={850}
          />
        </label>
        <label className="control">
          <span>{t('Note')}</span>
          <textarea
            className="field min-h-24 resize-y"
            value={note}
            onChange={(event) => setNote(event.target.value)}
            maxLength={2000}
          />
        </label>
        <div className="flex flex-wrap justify-end gap-2">
          {kind !== 'image' && (
            <Button
              onClick={() => {
                const position =
                  kind === 'audio' && audioPlayer
                    ? audioPlayer.currentTime(file.path)
                    : media.current?.currentTime
                if (
                  position !== null &&
                  position !== undefined &&
                  note.length < 1980 &&
                  Number.isFinite(position)
                )
                  setNote((current) => (current ? current + '\n' : '') + `[${formatDuration(position)}] `)
              }}
            >
              {t('Insert current time')}
            </Button>
          )}
          <Button variant="primary" disabled={saving} onClick={save}>
            {t(saving ? 'Saving…' : 'Save tags and note')}
          </Button>
        </div>
        {error && (
          <p role="alert" className="text-sm text-red-300">
            {error}
          </p>
        )}
      </div>
    </Modal>
  )
}
