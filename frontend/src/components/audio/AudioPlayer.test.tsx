import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { AudioPlayerBar, AudioPlayerProvider, useAudioLibrary } from './AudioPlayer'
import { FileGallery } from '../files/FileGallery'
import type { FileItem } from '../../types/api'
import App from '../../App'
import { StrictMode } from 'react'

vi.mock('../../api/client', async (original) => ({
  ...(await original<typeof import('../../api/client')>()),
  savePlayback: vi.fn(async () => ({ ok: true })),
}))
const files: FileItem[] = ['one.mp3', 'two.wav', 'three.m4a'].map((path, index) => ({
  path,
  name: path,
  size: 100,
  mtime: 10 + index,
}))
const toast = vi.fn()
function Library() {
  const player = useAudioLibrary('library', files)
  return (
    <>
      <FileGallery
        files={files}
        root="library"
        windowMode={false}
        audioPlayer={player}
        onToast={toast}
        onRefresh={() => {}}
      />
      <AudioPlayerBar windowMode={false} />
    </>
  )
}

it('paginates large playback queues instead of mounting every track', async () => {
  const many: FileItem[] = Array.from({ length: 60 }, (_, index) => ({
    path: `audio${index}.wav`,
    name: `audio${index}.wav`,
    size: 100,
    mtime: index,
  }))
  function Many() {
    const player = useAudioLibrary('many', many)
    return (
      <>
        <button onClick={() => player.enqueue(many)}>Add many</button>
        <AudioPlayerBar windowMode={false} />
      </>
    )
  }
  const user = userEvent.setup()
  render(
    <AudioPlayerProvider>
      <Many />
    </AudioPlayerProvider>,
  )
  await user.click(screen.getByRole('button', { name: 'Add many' }))
  await user.click(screen.getByRole('button', { name: 'Open playback queue' }))
  const dialog = screen.getByRole('dialog', { name: 'Playback queue' })
  expect(within(dialog).getAllByRole('listitem')).toHaveLength(25)
  await user.click(within(dialog).getByRole('button', { name: 'Next' }))
  expect(within(dialog).getAllByRole('listitem')).toHaveLength(25)
  await user.click(within(dialog).getByRole('button', { name: 'Next' }))
  expect(within(dialog).getAllByRole('listitem')).toHaveLength(10)
})
beforeEach(() => {
  vi.spyOn(HTMLMediaElement.prototype, 'play').mockImplementation(async function (this: HTMLMediaElement) {
    this.dispatchEvent(new Event('play'))
  })
  vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(function (this: HTMLMediaElement) {
    this.dispatchEvent(new Event('pause'))
  })
  vi.spyOn(HTMLMediaElement.prototype, 'load').mockImplementation(() => {})
})
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  toast.mockClear()
  window.location.hash = ''
})

it('plays filtered audio, controls speed and seeks, and lets users reorder and remove queue entries', async () => {
  const user = userEvent.setup()
  render(
    <AudioPlayerProvider>
      <Library />
    </AudioPlayerProvider>,
  )
  await user.click(screen.getByRole('button', { name: /Play filtered audio/ }))
  const bar = screen.getByRole('region', { name: 'Audio player' })
  expect(within(bar).getByRole('button', { name: 'Pause audio' })).toBeInTheDocument()
  const audio = screen.getByLabelText('Audio playback engine') as HTMLAudioElement
  Object.defineProperty(audio, 'duration', { value: 120, configurable: true })
  fireEvent.loadedMetadata(audio)
  await user.selectOptions(screen.getByLabelText('Playback speed'), '1.5')
  expect(audio.playbackRate).toBe(1.5)
  await user.click(screen.getByRole('button', { name: 'Forward 15 seconds' }))
  expect(audio.currentTime).toBe(15)
  await user.click(screen.getByRole('button', { name: 'Repeat off' }))
  expect(screen.getByRole('button', { name: 'Repeat all' })).toHaveAttribute('aria-pressed', 'true')
  await user.click(screen.getByRole('button', { name: 'Shuffle playback' }))
  expect(screen.getByRole('button', { name: 'Shuffle playback' })).toHaveAttribute('aria-pressed', 'true')
  await user.click(screen.getByRole('button', { name: 'Open playback queue' }))
  const dialog = screen.getByRole('dialog', { name: 'Playback queue' })
  const paths = () =>
    within(dialog)
      .getAllByRole('listitem')
      .map((item) => item.textContent)
  expect(paths()[0]).toContain('three.m4a')
  await user.click(within(dialog).getByRole('button', { name: 'Move one.mp3 up' }))
  expect(paths()[1]).toContain('one.mp3')
  const handles = within(dialog).getAllByRole('button', { name: /Drag .* to reorder/ })
  const dataTransfer = { setData: vi.fn(), effectAllowed: '' }
  fireEvent.dragStart(handles[0], { dataTransfer })
  fireEvent.drop(within(dialog).getAllByRole('listitem')[2], { dataTransfer })
  expect(paths()[1]).toContain('three.m4a')
  await user.click(within(dialog).getByRole('button', { name: 'Remove one.mp3 from playback queue' }))
  expect(within(dialog).getAllByRole('listitem')).toHaveLength(2)
  await user.click(within(dialog).getByRole('button', { name: 'Clear playback queue' }))
  expect(screen.queryByRole('region', { name: 'Audio player' })).toBeNull()
})

it('adds selected audio once and audio details reuse the persistent player', async () => {
  const user = userEvent.setup()
  render(
    <AudioPlayerProvider>
      <Library />
    </AudioPlayerProvider>,
  )
  await user.click(screen.getByRole('checkbox', { name: 'Select one.mp3' }))
  await user.click(screen.getByRole('button', { name: 'Add selected audio to queue' }))
  expect(toast).toHaveBeenLastCalledWith(expect.stringContaining('Added 1 tracks'))
  await user.click(screen.getByRole('button', { name: 'Add selected audio to queue' }))
  expect(toast).toHaveBeenLastCalledWith(expect.stringContaining('Added 0 tracks'))
  await user.click(screen.getByRole('button', { name: 'Details for one.mp3' }))
  const details = screen.getByRole('dialog', { name: 'Media details' })
  expect(details.querySelector('audio')).toBeNull()
  await user.click(within(details).getByRole('button', { name: 'Play audio' }))
  await user.click(within(details).getByRole('button', { name: 'Close' }))
  expect(screen.getByRole('button', { name: 'Pause audio' })).toBeInTheDocument()
  expect(document.querySelectorAll('audio')).toHaveLength(1)
})

it('keeps the same audio element and playback when navigating all app screens under StrictMode', async () => {
  window.location.hash = '#/library'
  localStorage.setItem('grab-setup-seen', '1')
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      return new Response(
        JSON.stringify(
          url.startsWith('/api/state')
            ? {
                version: 'fixture',
                ffmpeg: true,
                playwright: false,
                root: 'library',
                rev: 1,
                jobs: [],
                files,
                desktop_notifications: false,
                window: false,
              }
            : url.startsWith('/api/subscriptions')
              ? { subscriptions: [], interval_seconds: 3600 }
              : url.startsWith('/api/doctor')
                ? { checks: [], report: '', net: false }
                : { ok: true },
        ),
        { status: 200 },
      )
    }),
  )
  const user = userEvent.setup()
  render(
    <StrictMode>
      <App />
    </StrictMode>,
  )
  await user.click(await screen.findByRole('button', { name: /Play filtered audio/ }))
  const audio = document.querySelector('audio')
  expect(screen.getByRole('button', { name: 'Pause audio' })).toBeInTheDocument()
  for (const name of ['New download', 'Queue', 'Auto-download', 'Library']) {
    await user.click(screen.getAllByRole('button', { name })[0])
    expect(document.querySelector('audio')).toBe(audio)
    expect(screen.getByRole('button', { name: 'Pause audio' })).toBeInTheDocument()
  }
})
