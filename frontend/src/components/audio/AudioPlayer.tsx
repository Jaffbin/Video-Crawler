import {
  ArrowDown,
  ArrowUp,
  GripVertical,
  ListMusic,
  Pause,
  Play,
  Repeat,
  Shuffle,
  SkipBack,
  SkipForward,
  X,
} from 'lucide-react'
import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from 'react'
import { openFile } from '../../api/client'
import { useI18n } from '../../i18n'
import { AUDIO_RATES, AudioPlayerController, type RepeatMode } from '../../lib/audioPlayer'
import { formatDuration } from '../../lib/utils'
import type { FileItem } from '../../types/api'
import { Button } from '../ui/Button'
import { Modal } from '../ui/Modal'

const AudioContext = createContext<AudioPlayerController | null>(null)

export function AudioPlayerProvider({ children }: { children: ReactNode }) {
  const [controller] = useState(() => new AudioPlayerController())
  const element = useRef<HTMLAudioElement>(null)
  useEffect(() => controller.connect(element.current!), [controller])
  return (
    <AudioContext.Provider value={controller}>
      {children}
      <audio ref={element} preload="metadata" aria-label="Audio playback engine" />
    </AudioContext.Provider>
  )
}

export function useAudioPlayer() {
  const controller = useContext(AudioContext)
  if (!controller) throw new Error('AudioPlayerProvider is required')
  return controller
}

export function useAudioLibrary(root: string, files: FileItem[]) {
  const controller = useAudioPlayer()
  useEffect(() => controller.setLibrary(root, files), [controller, root, files])
  return controller
}

export function AudioPlayerBar({ windowMode }: { windowMode: boolean }) {
  const player = useAudioPlayer()
  const state = useSyncExternalStore(player.subscribe, player.getSnapshot)
  const { t } = useI18n()
  const [queueOpen, setQueueOpen] = useState(false)
  const [page, setPage] = useState(0)
  const [dragged, setDragged] = useState('')
  const [systemError, setSystemError] = useState('')
  const bar = useRef<HTMLElement>(null)
  const track = state.tracks.find((item) => item.path === state.current)
  const currentPage = Math.min(page, Math.max(0, Math.ceil(state.tracks.length / 25) - 1))

  useEffect(() => {
    const element = bar.current
    if (!element) return
    const update = () =>
      document.documentElement.style.setProperty(
        '--audio-toast-offset',
        `${innerHeight - element.getBoundingClientRect().top}px`,
      )
    update()
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(update)
    observer?.observe(element)
    window.addEventListener('resize', update)
    return () => {
      observer?.disconnect()
      window.removeEventListener('resize', update)
      document.documentElement.style.removeProperty('--audio-toast-offset')
    }
  }, [!!state.tracks.length])
  useEffect(() => {
    setPage(0)
    setSystemError('')
    setQueueOpen(false)
  }, [state.root])
  useEffect(() => {
    if (!state.tracks.length) setQueueOpen(false)
  }, [state.tracks.length])

  if (!state.tracks.length && !state.error) return null
  const repeatNames: Record<RepeatMode, string> = { off: 'Repeat off', all: 'Repeat all', one: 'Repeat one' }
  return (
    <>
      <section ref={bar} className="audio-player-bar" aria-label={t('Audio player')}>
        <div className="audio-player-main">
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold" title={track?.title || track?.name}>
              {track?.title || track?.name || t('Audio player')}
            </p>
            <p className="truncate text-xs text-zinc-400" title={track?.path}>
              {track && !track.available
                ? t('Unavailable')
                : t('{count} tracks in playback queue', { count: state.tracks.length })}
            </p>
          </div>
          <div className="flex items-center justify-center gap-1">
            <button
              className="action-btn"
              aria-label={t('Previous track')}
              disabled={!track}
              onClick={player.previous}
            >
              <SkipBack aria-hidden size={18} />
            </button>
            <button
              className="action-btn"
              aria-label={t('Back 15 seconds')}
              disabled={!state.duration || !track?.available}
              onClick={() => player.seek(state.position - 15)}
            >
              −15
            </button>
            <Button
              variant="primary"
              disabled={!track?.available}
              onClick={state.playing ? player.pause : player.play}
              aria-label={t(state.playing ? 'Pause audio' : 'Play audio')}
            >
              {state.playing ? <Pause aria-hidden size={18} /> : <Play aria-hidden size={18} />}
            </Button>
            <button
              className="action-btn"
              aria-label={t('Forward 15 seconds')}
              disabled={!state.duration || !track?.available}
              onClick={() => player.seek(state.position + 15)}
            >
              +15
            </button>
            <button
              className="action-btn"
              aria-label={t('Next track')}
              disabled={!track}
              onClick={() => player.next()}
            >
              <SkipForward aria-hidden size={18} />
            </button>
          </div>
          <div className="flex flex-wrap items-center justify-end gap-1">
            <button
              className="action-btn"
              aria-label={t('Shuffle playback')}
              aria-pressed={state.shuffle}
              onClick={player.toggleShuffle}
            >
              <Shuffle aria-hidden size={16} />
            </button>
            <button
              className="action-btn"
              aria-label={t(repeatNames[state.repeat])}
              title={t(repeatNames[state.repeat])}
              aria-pressed={state.repeat !== 'off'}
              onClick={() =>
                player.setRepeat(({ off: 'all', all: 'one', one: 'off' } as const)[state.repeat])
              }
            >
              <Repeat aria-hidden size={16} />
              {state.repeat === 'one' && <span>1</span>}
            </button>
            <label>
              <span className="sr-only">{t('Playback speed')}</span>
              <select
                className="audio-player-select"
                value={state.rate}
                onChange={(event) => player.setRate(Number(event.target.value))}
              >
                {AUDIO_RATES.map((rate) => (
                  <option key={rate} value={rate}>
                    {rate}×
                  </option>
                ))}
              </select>
            </label>
            <button
              className="action-btn"
              aria-label={t('Open playback queue')}
              onClick={() => setQueueOpen(true)}
            >
              <ListMusic aria-hidden size={17} />
              <span>{state.tracks.length}</span>
            </button>
          </div>
        </div>
        <div className="audio-player-timeline text-xs text-zinc-400">
          <span>{formatDuration(state.position)}</span>
          <input
            type="range"
            aria-label={t('Audio position')}
            min={0}
            max={state.duration || 1}
            step={0.1}
            value={Math.min(state.position, state.duration || 0)}
            disabled={!state.duration || !track?.available}
            onChange={(event) => player.seek(Number(event.target.value))}
          />
          <span>{formatDuration(state.duration)}</span>
          <label className="audio-player-volume">
            <span>{t('Volume')}</span>
            <input
              type="range"
              aria-label={t('Audio volume')}
              min={0}
              max={1}
              step={0.05}
              value={state.volume}
              onChange={(event) => player.setVolume(Number(event.target.value))}
            />
          </label>
        </div>
        {(state.error || systemError) && (
          <div className="flex min-w-0 flex-wrap items-center gap-2 text-xs text-amber-300">
            <p role="alert" className="min-w-0 flex-1 break-words">
              {t(systemError || state.error)}
            </p>
            {track && windowMode && (
              <Button
                onClick={() => {
                  player.pause()
                  void openFile(track.path).catch(() => setSystemError('Could not open it'))
                }}
              >
                {t('Open in system player')}
              </Button>
            )}
          </div>
        )}
      </section>
      <Modal open={queueOpen} title={t('Playback queue')} onClose={() => setQueueOpen(false)} wide>
        <div className="grid min-w-0 gap-3">
          <p className="text-sm text-zinc-400">
            {t('Drag to reorder, or use the move buttons. Removing a track only changes this queue.')}
          </p>
          <p className="text-xs text-zinc-400">
            {t(
              'The queue and position are remembered for this library. Playback resumes only when you press Play.',
            )}
          </p>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-sm">
              {t('{count} tracks in playback queue', { count: state.tracks.length })} · {currentPage + 1}/
              {Math.max(1, Math.ceil(state.tracks.length / 25))}
            </span>
            <Button disabled={!state.tracks.length} onClick={player.clear}>
              {t('Clear playback queue')}
            </Button>
          </div>
          {!state.tracks.length && <p>{t('Add audio from Library to start listening.')}</p>}
          <ol className="grid min-w-0 gap-2">
            {state.tracks.slice(currentPage * 25, (currentPage + 1) * 25).map((item, offset) => {
              const index = currentPage * 25 + offset
              return (
                <li
                  className="flex min-w-0 items-center gap-2 rounded-xl border border-white/10 p-2"
                  key={item.path}
                  onDragOver={(event) => {
                    if (dragged) event.preventDefault()
                  }}
                  onDrop={(event) => {
                    event.preventDefault()
                    if (dragged) player.move(dragged, item.path)
                    setDragged('')
                  }}
                >
                  <span
                    draggable
                    tabIndex={0}
                    role="button"
                    aria-label={t('Drag {name} to reorder', { name: item.name })}
                    className="cursor-grab text-zinc-400"
                    title={t('Use move buttons for keyboard reordering')}
                    onDragStart={(event) => {
                      setDragged(item.path)
                      event.dataTransfer.setData('text/plain', item.path)
                      event.dataTransfer.effectAllowed = 'move'
                    }}
                    onDragEnd={() => setDragged('')}
                  >
                    <GripVertical aria-hidden size={18} />
                  </span>
                  <div className="min-w-0 flex-1">
                    <button
                      className="block max-w-full truncate text-left text-sm"
                      disabled={!item.available}
                      aria-current={item.path === state.current ? 'true' : undefined}
                      title={item.title}
                      onClick={() => player.select(item.path)}
                    >
                      {item.title || item.name}
                    </button>
                    <p className="truncate text-xs text-zinc-400" title={item.path}>
                      {item.available ? item.path : t('Unavailable') + ' · ' + item.path}
                    </p>
                  </div>
                  <div className="flex shrink-0 gap-1">
                    <button
                      className="action-btn"
                      aria-label={t('Move {name} up', { name: item.name })}
                      disabled={index === 0}
                      onClick={() => player.move(item.path, state.tracks[index - 1].path)}
                    >
                      <ArrowUp aria-hidden size={15} />
                    </button>
                    <button
                      className="action-btn"
                      aria-label={t('Move {name} down', { name: item.name })}
                      disabled={index === state.tracks.length - 1}
                      onClick={() => player.move(state.tracks[index + 1].path, item.path)}
                    >
                      <ArrowDown aria-hidden size={15} />
                    </button>
                    <button
                      className="action-btn"
                      aria-label={t('Remove {name} from playback queue', { name: item.name })}
                      onClick={() => player.remove(item.path)}
                    >
                      <X aria-hidden size={15} />
                    </button>
                  </div>
                </li>
              )
            })}
          </ol>
          {state.tracks.length > 25 && (
            <div className="flex gap-2">
              <Button disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}>
                {t('Previous')}
              </Button>
              <Button
                disabled={(currentPage + 1) * 25 >= state.tracks.length}
                onClick={() => setPage(currentPage + 1)}
              >
                {t('Next')}
              </Button>
            </div>
          )}
        </div>
      </Modal>
    </>
  )
}
