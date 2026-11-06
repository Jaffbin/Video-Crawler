import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AudioPlayerController, AUDIO_QUEUE_LIMIT, audioQueueKey, loadAudioQueue } from './audioPlayer'
import { savePlayback } from '../api/client'
import type { FileItem } from '../types/api'

vi.mock('../api/client', () => ({
  fileUrl: (path: string) => '/files/' + path,
  savePlayback: vi.fn(async () => ({ ok: true })),
}))
const files: FileItem[] = ['a.mp3', 'b.m4a', 'c.wav'].map((path) => ({
  path,
  name: path,
  title: path,
  size: 100,
  mtime: 10,
}))
let audio: HTMLAudioElement
let player: AudioPlayerController
let disconnect: () => void
let play: ReturnType<typeof vi.spyOn>
function metadata(duration = 120) {
  Object.defineProperty(audio, 'duration', { value: duration, configurable: true })
  audio.dispatchEvent(new Event('loadedmetadata'))
}
function time(position: number) {
  audio.currentTime = position
  audio.dispatchEvent(new Event('timeupdate'))
}
function end() {
  audio.currentTime = audio.duration
  audio.dispatchEvent(new Event('ended'))
}
beforeEach(() => {
  audio = document.createElement('audio')
  play = vi.spyOn(audio, 'play').mockImplementation(async () => {
    audio.dispatchEvent(new Event('play'))
  })
  vi.spyOn(audio, 'pause').mockImplementation(() => {
    audio.dispatchEvent(new Event('pause'))
  })
  vi.spyOn(audio, 'load').mockImplementation(() => {})
  player = new AudioPlayerController()
  player.setLibrary('/library', files)
  disconnect = player.connect(audio)
})
afterEach(() => {
  disconnect()
  vi.restoreAllMocks()
  vi.clearAllMocks()
})

describe('audio playback controller', () => {
  it('selecting the current track does not restart it', () => {
    player.playFiles(files)
    metadata()
    time(24)
    player.select('a.mp3')
    expect(player.getSnapshot().position).toBe(24)
    expect(audio.currentTime).toBe(24)
  })
  it('adding an existing track does not restart the shuffle cycle', () => {
    vi.spyOn(Math, 'random').mockReturnValue(0)
    player.playFiles(files)
    player.toggleShuffle()
    metadata()
    end()
    expect(player.getSnapshot().current).toBe('c.wav')
    expect(player.enqueue([files[0]])).toBe(0)
    metadata()
    end()
    expect(player.getSnapshot().current).toBe('b.m4a')
    metadata()
    end()
    expect(player.getSnapshot().playing).toBe(false)
  })
  it('queues only complete library audio, deduplicates and bounds the queue', () => {
    const many = Array.from({ length: 510 }, (_, index) => ({
      ...files[0],
      path: `${index}.mp3`,
      name: `${index}.mp3`,
    }))
    player.setLibrary('/library', [
      ...files,
      ...many,
      { ...files[0], path: 'unfinished.mp3', complete: false },
    ])
    expect(
      player.enqueue([
        ...files,
        files[0],
        { ...files[0], path: 'outside.mp3' },
        { ...files[0], path: 'unfinished.mp3', complete: false },
        { ...files[0], path: 'x.mp4', name: 'x.mp4' },
      ]),
    ).toBe(3)
    expect(play).not.toHaveBeenCalled()
    expect(player.enqueue(many)).toBe(AUDIO_QUEUE_LIMIT - 3)
    expect(player.getSnapshot().tracks).toHaveLength(AUDIO_QUEUE_LIMIT)
    player.playFile(many.at(-1)!)
    expect(player.getSnapshot().error).toContain('full')
  })
  it('continues in order, stops after the last track, and repeats a list or one track', async () => {
    player.playFiles(files)
    metadata()
    expect(player.getSnapshot().playing).toBe(true)
    end()
    expect(player.getSnapshot().current).toBe('b.m4a')
    metadata()
    player.setRepeat('one')
    end()
    expect(player.getSnapshot().current).toBe('b.m4a')
    expect(audio.currentTime).toBe(0)
    player.next()
    expect(player.getSnapshot().current).toBe('c.wav')
    metadata()
    end()
    expect(player.getSnapshot().playing).toBe(true) // repeat one
    player.setRepeat('off')
    end()
    expect(player.getSnapshot().playing).toBe(false)
    player.setRepeat('all')
    player.next()
    expect(player.getSnapshot().current).toBe('a.mp3')
    await Promise.resolve()
    expect(savePlayback).toHaveBeenCalled()
  })
  it('shuffles without repeating until the cycle ends and keeps a previous-track history', () => {
    vi.spyOn(Math, 'random').mockReturnValue(0)
    player.playFiles(files)
    player.toggleShuffle()
    const seen = [player.getSnapshot().current]
    metadata()
    end()
    seen.push(player.getSnapshot().current)
    metadata()
    end()
    seen.push(player.getSnapshot().current)
    expect(new Set(seen).size).toBe(3)
    metadata()
    end()
    expect(player.getSnapshot().playing).toBe(false)
    player.seek(0)
    player.previous()
    expect(player.getSnapshot().current).toBe(seen[1])
  })
  it('seeks with bounds, remembers speed and volume, and preserves pause between sessions', () => {
    player.playFiles(files)
    metadata()
    player.seek(200)
    expect(audio.currentTime).toBe(120)
    player.seek(-15)
    expect(audio.currentTime).toBe(0)
    time(42)
    player.setRate(1.5)
    player.setVolume(0.25)
    player.pause()
    const saved = loadAudioQueue('/library')
    expect(saved).toMatchObject({ current: 'a.mp3', position: 42, rate: 1.5, volume: 0.25, playing: false })
    const resumed = new AudioPlayerController()
    resumed.setLibrary('/library', files)
    const other = document.createElement('audio')
    const resumedPlay = vi.spyOn(other, 'play').mockResolvedValue(undefined)
    vi.spyOn(other, 'pause').mockImplementation(() => {})
    vi.spyOn(other, 'load').mockImplementation(() => {})
    const cleanup = resumed.connect(other)
    Object.defineProperty(other, 'duration', { value: 120 })
    other.dispatchEvent(new Event('loadedmetadata'))
    expect(other.currentTime).toBe(42)
    expect(resumedPlay).not.toHaveBeenCalled()
    expect(resumed.getSnapshot().playing).toBe(false)
    cleanup()
  })
  it('reorders and removes without changing the current source, retaining per-track positions', () => {
    player.playFiles(files)
    metadata()
    time(22)
    player.next()
    metadata()
    const source = audio.src
    player.move('c.wav', 'a.mp3')
    expect(player.getSnapshot().tracks.map((item) => item.path)).toEqual(['c.wav', 'a.mp3', 'b.m4a'])
    expect(audio.src).toBe(source)
    player.select('a.mp3')
    metadata()
    expect(audio.currentTime).toBe(22)
    player.remove('a.mp3')
    expect(player.getSnapshot().current).toBe('b.m4a')
    player.clear()
    expect(player.getSnapshot().tracks).toEqual([])
    expect(audio.hasAttribute('src')).toBe(false)
  })
  it('keeps missing entries, pauses unavailable files, restores availability and isolates libraries', () => {
    player.playFiles(files)
    metadata()
    time(18)
    player.setLibrary('/library', files.slice(1))
    expect(player.getSnapshot()).toMatchObject({ playing: false, current: 'a.mp3', position: 18 })
    expect(player.getSnapshot().tracks[0].available).toBe(false)
    expect(audio.hasAttribute('src')).toBe(false)
    player.setLibrary('/library', files)
    expect(player.getSnapshot().tracks[0].available).toBe(true)
    expect(player.getSnapshot().playing).toBe(false)
    player.setLibrary('/other', [])
    expect(player.getSnapshot().tracks).toEqual([])
    player.setLibrary('/library', files)
    expect(player.getSnapshot().current).toBe('a.mp3')
    expect(player.getSnapshot().position).toBe(18)
    expect(player.getSnapshot().playing).toBe(false)
  })
  it('follows in-app rename and reloads the source at the previous position', () => {
    player.playFiles(files)
    metadata()
    time(35)
    player.rename('a.mp3', 'renamed.mp3')
    metadata()
    expect(player.getSnapshot().current).toBe('renamed.mp3')
    expect(audio.src).toContain('/files/renamed.mp3')
    expect(audio.currentTime).toBe(35)
    expect(player.getSnapshot().playing).toBe(true)
  })
  it('reports unsupported formats and autoplay denial without endlessly skipping tracks', async () => {
    player.enqueue(files)
    play.mockRejectedValueOnce(new DOMException('Permission denied', 'NotAllowedError'))
    player.play()
    await Promise.resolve()
    await Promise.resolve()
    expect(player.getSnapshot().error).toContain('Click Play')
    audio.dispatchEvent(new Event('error'))
    expect(player.getSnapshot().error).toContain('system player')
    expect(player.getSnapshot().current).toBe('a.mp3')
    player.next()
    expect(player.getSnapshot().current).toBe('b.m4a')
  })
  it('handles delayed play resolution and disposal without restarting playback', async () => {
    let finish!: () => void
    play.mockReturnValueOnce(
      new Promise<void>((resolve) => {
        finish = resolve
      }),
    )
    player.playFiles(files)
    player.pause()
    finish()
    await Promise.resolve()
    expect(player.getSnapshot().playing).toBe(false)
    metadata()
    player.play()
    time(38)
    window.dispatchEvent(new Event('pagehide'))
    expect(loadAudioQueue('/library').position).toBe(38)
    disconnect()
    disconnect = () => {}
    expect(audio.hasAttribute('src')).toBe(false)
    expect(player.getSnapshot().playing).toBe(false)
  })
  it('bounds and sanitizes untrusted persisted state, and survives unavailable storage', () => {
    localStorage.setItem(
      audioQueueKey('/bad'),
      JSON.stringify({
        version: 1,
        tracks: [
          null,
          { path: '../a.mp3' },
          { path: 'https://evil/a.mp3' },
          { path: 'ok.mp3' },
          { path: 'ok.mp3' },
        ],
        current: '../a.mp3',
        position: -10,
        duration: '120',
        rate: 99,
        repeat: 'invalid',
        volume: 9,
      }),
    )
    expect(loadAudioQueue('/bad')).toMatchObject({
      current: 'ok.mp3',
      position: 0,
      duration: 0,
      rate: 1,
      repeat: 'off',
      volume: 1,
      playing: false,
    })
    expect(loadAudioQueue('/bad').tracks).toHaveLength(1)
    localStorage.setItem(audioQueueKey('/bad'), '{')
    expect(loadAudioQueue('/bad').error).toContain('restore')
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('Quota')
    })
    player.enqueue(files)
    expect(player.getSnapshot().tracks).toHaveLength(3)
    expect(player.getSnapshot().error).toContain('session')
  })
  it('serializes progress writes with a library binding and retains local progress after failures', async () => {
    vi.mocked(savePlayback).mockRejectedValueOnce(new Error('offline'))
    player.playFiles(files)
    metadata()
    time(20)
    player.pause()
    await Promise.resolve()
    await Promise.resolve()
    expect(savePlayback).toHaveBeenCalledWith('a.mp3', 20, 120, '/library')
    expect(player.getSnapshot().error).toContain('kept locally')
    expect(loadAudioQueue('/library').position).toBe(20)
  })
})
