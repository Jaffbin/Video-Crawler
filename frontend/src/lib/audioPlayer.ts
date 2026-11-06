import { fileUrl, savePlayback } from '../api/client'
import type { FileItem } from '../types/api'
import { fileKind } from './library'

export const AUDIO_QUEUE_LIMIT = 500
export const AUDIO_RATES = [0.5, 0.75, 1, 1.25, 1.5, 1.75, 2]
const MAX_DURATION = 7 * 86400
export type RepeatMode = 'off' | 'all' | 'one'
export interface AudioTrack {
  path: string
  name: string
  title: string
  size: number
  mtime: number
  available: boolean
  resume: number
}
export interface AudioState {
  root: string
  tracks: AudioTrack[]
  current: string
  position: number
  duration: number
  playing: boolean
  rate: number
  volume: number
  repeat: RepeatMode
  shuffle: boolean
  error: string
}
export const audioQueueKey = (root: string) => 'grab-audio-queue:' + root
const emptyState = (root = ''): AudioState => ({
  root,
  tracks: [],
  current: '',
  position: 0,
  duration: 0,
  playing: false,
  rate: 1,
  volume: 1,
  repeat: 'off',
  shuffle: false,
  error: '',
})
const validPath = (path: unknown): path is string =>
  typeof path === 'string' &&
  path.length > 0 &&
  path.length <= 2000 &&
  !/[\\:\x00-\x1f]/.test(path) &&
  path.split('/').every((part) => part && !part.startsWith('.'))
const seconds = (value: unknown) =>
  typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= MAX_DURATION ? value : 0
export const playableAudio = (file: FileItem) => fileKind(file) === 'audio' && file.complete !== false

export function loadAudioQueue(root: string): AudioState {
  const state = emptyState(root)
  try {
    const saved = JSON.parse(localStorage.getItem(audioQueueKey(root)) || 'null')
    if (!saved) return state
    if (saved.version !== 1 || !Array.isArray(saved.tracks)) throw new Error('Invalid queue')
    const paths = new Set<string>()
    for (const item of saved.tracks.slice(0, AUDIO_QUEUE_LIMIT)) {
      if (!item || !validPath(item.path) || paths.has(item.path)) continue
      paths.add(item.path)
      state.tracks.push({
        path: item.path,
        name: String(item.name || item.path).slice(0, 2000),
        title: String(item.title || '').slice(0, 1000),
        size: typeof item.size === 'number' && Number.isFinite(item.size) ? item.size : 0,
        mtime: typeof item.mtime === 'number' && Number.isFinite(item.mtime) ? item.mtime : 0,
        available: false,
        resume: seconds(item.resume),
      })
    }
    state.current = paths.has(saved.current) ? saved.current : state.tracks[0]?.path || ''
    state.position = seconds(saved.position)
    state.duration = seconds(saved.duration)
    state.rate = AUDIO_RATES.includes(saved.rate) ? saved.rate : 1
    state.volume =
      typeof saved.volume === 'number' && Number.isFinite(saved.volume)
        ? Math.max(0, Math.min(1, saved.volume))
        : 1
    state.repeat = ['off', 'all', 'one'].includes(saved.repeat) ? saved.repeat : 'off'
    state.shuffle = saved.shuffle === true
  } catch {
    state.error = 'Could not restore the playback queue. You can add audio from Library again.'
  }
  return state
}

/** One audio element for the main app; only the playback UI subscribes to frequent time updates. */
export class AudioPlayerController {
  private state = emptyState()
  private listeners = new Set<() => void>()
  private audio: HTMLAudioElement | null = null
  private files = new Map<string, FileItem>()
  private detach: (() => void) | null = null
  private generation = 0
  private desiredPlaying = false
  private initialized = false
  private tracked = false
  private history: string[] = []
  private remaining: string[] = []
  private lastLocalSave = 0
  private lastServerSave = 0
  private pending = Promise.resolve()
  private sent = ''

  getSnapshot = () => this.state
  subscribe = (listener: () => void) => {
    this.listeners.add(listener)
    return () => {
      this.listeners.delete(listener)
    }
  }
  private update(patch: Partial<AudioState>, persist = false) {
    this.state = { ...this.state, ...patch }
    if (persist) this.persist()
    this.listeners.forEach((listener) => listener())
  }
  private persist() {
    if (!this.state.root) return
    try {
      localStorage.setItem(
        audioQueueKey(this.state.root),
        JSON.stringify({
          version: 1,
          ...this.state,
          playing: undefined,
          error: undefined,
          tracks: this.state.tracks.map(({ available: _available, ...track }) => track),
        }),
      )
    } catch {
      if (this.state.error !== 'Could not save the playback queue. Playback still works in this session.')
        this.update({ error: 'Could not save the playback queue. Playback still works in this session.' })
    }
  }
  private shuffled(paths: string[]) {
    const result = [...paths]
    for (let i = result.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1))
      ;[result[i], result[j]] = [result[j], result[i]]
    }
    return result
  }
  private resetOrder() {
    this.history = []
    this.remaining = this.shuffled(
      this.state.tracks.filter((item) => item.path !== this.state.current).map((item) => item.path),
    )
  }

  setLibrary = (root: string, files: FileItem[]) => {
    if (!root) return
    const changedRoot = root !== this.state.root
    if (changedRoot) {
      this.pause()
      this.state = loadAudioQueue(root)
      this.sent = ''
    }
    this.files = new Map(files.map((file) => [file.path, file]))
    let changed = changedRoot
    const tracks = this.state.tracks.map((track) => {
      const file = this.files.get(track.path)
      const available = !!file && playableAudio(file)
      if (file && available) {
        const title = file.title || file.name
        if (
          track.name === file.name &&
          track.title === title &&
          track.size === file.size &&
          track.mtime === file.mtime &&
          track.available
        )
          return track
        changed = true
        if (
          !changedRoot &&
          track.path === this.state.current &&
          (track.size !== file.size || track.mtime !== file.mtime)
        ) {
          this.pause()
          this.state = { ...this.state, position: 0, duration: 0 }
          this.initialized = false
        }
        return { ...track, name: file.name, title, size: file.size, mtime: file.mtime, available }
      }
      if (available === track.available) return track
      changed = true
      return { ...track, available }
    })
    if (!changed) return
    this.update({ tracks }, true)
    const current = tracks.find((track) => track.path === this.state.current)
    if (current && !current.available) {
      this.pause()
      this.update({ error: 'This audio is unavailable. Restore the file or choose another track.' })
      this.unload()
    } else {
      if (this.state.error === 'This audio is unavailable. Restore the file or choose another track.')
        this.update({ error: '' })
      if (changedRoot || !this.initialized) this.load(false)
    }
    if (changedRoot) this.resetOrder()
  }

  connect = (audio: HTMLAudioElement) => {
    this.audio = audio
    const events: Array<[string, EventListener]> = [
      [
        'loadedmetadata',
        () => {
          const duration = seconds(audio.duration)
          const position = duration && this.state.position < duration ? this.state.position : 0
          audio.currentTime = position
          audio.playbackRate = this.state.rate
          this.update({ duration, position })
        },
      ],
      [
        'play',
        () => {
          this.tracked = true
          this.update({ playing: true })
          window.dispatchEvent(new Event('grab-audio-started'))
        },
      ],
      [
        'pause',
        () => {
          this.capture(true)
          this.update({ playing: false })
        },
      ],
      ['timeupdate', () => this.capture()],
      ['seeked', () => this.capture(true)],
      [
        'ended',
        () => {
          if (!this.state.current) return
          this.tracked = true
          this.capture(true, true)
          this.next(true)
        },
      ],
      [
        'error',
        () => {
          if (!this.initialized) return
          this.desiredPlaying = false
          this.update({
            playing: false,
            error: 'This audio cannot be played here. Try the next track or open it in your system player.',
          })
        },
      ],
    ]
    events.forEach(([name, handler]) => audio.addEventListener(name, handler))
    const pagehide = () => this.flush()
    window.addEventListener('pagehide', pagehide)
    this.detach = () => {
      events.forEach(([name, handler]) => audio.removeEventListener(name, handler))
      window.removeEventListener('pagehide', pagehide)
    }
    this.load(false)
    return () => {
      this.flush()
      this.detach?.()
      this.detach = null
      this.unload()
      this.audio = null
      this.update({ playing: false })
    }
  }
  private unload() {
    this.generation++
    this.desiredPlaying = false
    this.initialized = false
    if (this.audio?.hasAttribute('src')) {
      this.audio.pause()
      this.audio.removeAttribute('src')
      this.audio.load()
    }
  }
  private load(play: boolean) {
    this.unload()
    this.tracked = false
    const track = this.state.tracks.find((item) => item.path === this.state.current)
    if (!this.audio || !track?.available) return
    this.audio.src = fileUrl(track.path)
    this.audio.playbackRate = this.state.rate
    this.audio.volume = this.state.volume
    this.initialized = true
    if (play) this.play()
  }
  play = () => {
    const track = this.state.tracks.find((item) => item.path === this.state.current)
    if (!track?.available) {
      this.update({ error: 'This audio is unavailable. Restore the file or choose another track.' })
      return
    }
    if (!this.initialized) this.load(false)
    if (!this.audio) return
    if (this.state.duration && this.state.position >= this.state.duration) this.seek(0)
    const generation = this.generation
    this.desiredPlaying = true
    this.update({ error: '' })
    void this.audio
      .play()
      .then(() => {
        if (generation === this.generation && !this.desiredPlaying) this.audio?.pause()
      })
      .catch((error: unknown) => {
        if (generation !== this.generation || !this.desiredPlaying) return
        this.desiredPlaying = false
        this.update({
          playing: false,
          error:
            error instanceof DOMException && error.name === 'NotAllowedError'
              ? 'Click Play to allow audio playback.'
              : 'This audio cannot be played here. Try the next track or open it in your system player.',
        })
      })
  }
  pause = () => {
    this.desiredPlaying = false
    this.capture(true)
    if (this.initialized) this.audio?.pause()
    this.update({ playing: false })
  }
  private capture(force = false, ended = false) {
    if (!this.audio || !this.initialized || !this.tracked) return
    const duration = seconds(this.audio.duration)
    if (!duration) return
    const position = ended ? duration : Math.min(duration, seconds(this.audio.currentTime))
    this.update({
      position,
      duration,
      tracks: force
        ? this.state.tracks.map((track) =>
            track.path === this.state.current ? { ...track, resume: ended ? 0 : position } : track,
          )
        : this.state.tracks,
    })
    const now = Date.now()
    if (force || now - this.lastLocalSave > 1000) {
      this.persist()
      this.lastLocalSave = now
    }
    if (force || now - this.lastServerSave > 5000) {
      this.saveProgress()
      this.lastServerSave = now
    }
  }
  private saveProgress() {
    const { root, current, position, duration } = this.state
    if (!current || !duration || !this.tracked) return
    const signature = `${root}/${current}/${position}/${duration}`
    if (this.sent === signature) return
    this.sent = signature
    this.pending = this.pending.then(async () => {
      if (root !== this.state.root) return
      try {
        await savePlayback(current, position, duration, root)
      } catch {
        if (root === this.state.root) {
          this.sent = ''
          this.update({ error: 'Could not save playback progress. Your queue position is kept locally.' })
        }
      }
    })
  }
  flush = () => {
    this.capture(true)
    this.persist()
  }
  seek = (position: number) => {
    if (!Number.isFinite(position) || !this.audio || !this.state.duration) return
    this.audio.currentTime = Math.max(0, Math.min(this.state.duration, position))
    this.update({ position: this.audio.currentTime }, true)
    this.capture(true)
  }
  setRate = (rate: number) => {
    if (!AUDIO_RATES.includes(rate)) return
    if (this.audio) this.audio.playbackRate = rate
    this.update({ rate }, true)
  }
  setVolume = (volume: number) => {
    if (!Number.isFinite(volume)) return
    volume = Math.max(0, Math.min(1, volume))
    if (this.audio) this.audio.volume = volume
    this.update({ volume }, true)
  }
  setRepeat = (repeat: RepeatMode) => {
    if (['off', 'all', 'one'].includes(repeat)) this.update({ repeat }, true)
  }
  toggleShuffle = () => {
    this.update({ shuffle: !this.state.shuffle }, true)
    this.resetOrder()
  }
  enqueue = (files: FileItem[], replace = false) => {
    const tracks = replace ? [] : [...this.state.tracks]
    const paths = new Set(tracks.map((item) => item.path))
    let added = 0
    for (const candidate of files) {
      const file = this.files.get(candidate.path)
      if (!file || !playableAudio(file) || !validPath(file.path) || paths.has(file.path)) continue
      if (tracks.length === AUDIO_QUEUE_LIMIT) break
      paths.add(file.path)
      tracks.push({
        path: file.path,
        name: file.name,
        title: file.title || file.name,
        size: file.size,
        mtime: file.mtime,
        available: true,
        resume: file.playback && !file.playback.finished ? seconds(file.playback.position) : 0,
      })
      added++
    }
    if (!added && !replace) return 0
    if (replace) this.pause()
    const current = replace || !this.state.current ? tracks[0]?.path || '' : this.state.current
    this.update(
      {
        tracks,
        current,
        ...(replace || !this.state.current ? { position: tracks[0]?.resume || 0, duration: 0 } : {}),
      },
      true,
    )
    this.resetOrder()
    if (replace || !this.initialized) this.load(false)
    return added
  }
  playFile = (file: FileItem) => {
    if (!this.state.tracks.some((item) => item.path === file.path) && !this.enqueue([file])) {
      this.update({ error: 'The playback queue is full (500 tracks). Remove some tracks first.' })
      return
    }
    if (this.state.current === file.path) this.play()
    else this.select(file.path)
  }
  playFiles = (files: FileItem[]) => {
    this.enqueue(files, true)
    if (this.state.current) this.play()
  }
  select = (path: string, remember = true) => {
    const track = this.state.tracks.find((item) => item.path === path)
    if (!track?.available) return
    if (path === this.state.current) {
      this.play()
      return
    }
    this.pause()
    if (remember && this.state.current && path !== this.state.current) this.history.push(this.state.current)
    this.history = this.history.slice(-AUDIO_QUEUE_LIMIT)
    this.remaining = this.remaining.filter((item) => item !== path)
    this.sent = ''
    this.update({ current: path, position: track.resume, duration: 0, error: '' }, true)
    this.load(true)
  }
  next = (ended = false) => {
    if (ended && this.state.repeat === 'one') {
      this.seek(0)
      this.play()
      return
    }
    const available = this.state.tracks.filter((item) => item.available)
    let path: string | undefined
    if (this.state.shuffle) {
      this.remaining = this.remaining.filter((item) => available.some((track) => track.path === item))
      if (!this.remaining.length && this.state.repeat === 'all')
        this.remaining = this.shuffled(
          available.filter((item) => item.path !== this.state.current).map((item) => item.path),
        )
      path = this.remaining.shift()
    } else {
      const index = this.state.tracks.findIndex((item) => item.path === this.state.current)
      path = this.state.tracks.slice(index + 1).find((item) => item.available)?.path
      if (!path && this.state.repeat === 'all') path = available[0]?.path
    }
    if (!path && this.state.repeat === 'all' && available.length === 1) path = available[0].path
    if (path) this.select(path)
    else this.pause()
  }
  previous = () => {
    if (this.state.position > 3) {
      this.seek(0)
      return
    }
    const path = this.state.shuffle
      ? this.history.pop()
      : this.state.tracks
          .slice(
            0,
            this.state.tracks.findIndex((item) => item.path === this.state.current),
          )
          .reverse()
          .find((item) => item.available)?.path
    if (path && this.state.tracks.some((item) => item.path === path && item.available)) {
      if (this.state.shuffle && this.state.current) this.remaining.unshift(this.state.current)
      this.select(path, false)
    } else this.seek(0)
  }
  move = (path: string, before: string) => {
    if (path === before) return
    const track = this.state.tracks.find((item) => item.path === path)
    if (!track || !this.state.tracks.some((item) => item.path === before)) return
    const tracks = this.state.tracks.filter((item) => item.path !== path)
    tracks.splice(
      tracks.findIndex((item) => item.path === before),
      0,
      track,
    )
    this.update({ tracks }, true)
  }
  remove = (path: string) => {
    const index = this.state.tracks.findIndex((item) => item.path === path)
    const tracks = this.state.tracks.filter((item) => item.path !== path)
    const playing = this.state.playing
    if (path === this.state.current) this.pause()
    this.update({ tracks }, true)
    this.history = this.history.filter((item) => item !== path)
    this.remaining = this.remaining.filter((item) => item !== path)
    if (path !== this.state.current) return
    const next = tracks.slice(index).find((item) => item.available) || tracks.find((item) => item.available)
    this.update(
      { current: next?.path || tracks[0]?.path || '', position: next?.resume || 0, duration: 0, error: '' },
      true,
    )
    this.load(playing)
  }
  clear = () => {
    this.pause()
    this.update({ tracks: [], current: '', position: 0, duration: 0, error: '' }, true)
    this.resetOrder()
    this.unload()
  }
  rename = (oldPath: string, newPath: string) => {
    if (oldPath === newPath || !this.state.tracks.some((track) => track.path === oldPath)) return
    const file = this.files.get(oldPath)
    if (file) this.files.set(newPath, { ...file, path: newPath, name: newPath.split('/').pop()! })
    const playing = this.state.playing
    const current = this.state.current === oldPath
    if (current) this.pause()
    this.update(
      {
        tracks: this.state.tracks.map((track) =>
          track.path === oldPath ? { ...track, path: newPath, name: newPath.split('/').pop()! } : track,
        ),
        current: current ? newPath : this.state.current,
      },
      true,
    )
    this.history = this.history.map((path) => (path === oldPath ? newPath : path))
    this.remaining = this.remaining.map((path) => (path === oldPath ? newPath : path))
    if (current) this.load(playing)
  }
  currentTime = (path: string) => (path === this.state.current ? this.state.position : null)
}
