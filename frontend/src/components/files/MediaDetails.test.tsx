import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { MediaDetails } from './MediaDetails'
import { saveFileDetails, savePlayback } from '../../api/client'
import type { FileItem } from '../../types/api'
import { AudioPlayerController } from '../../lib/audioPlayer'

vi.mock('../../api/client', () => ({
  fileUrl: (path: string) => '/files/' + path,
  saveFileDetails: vi.fn(async () => ({ ok: true })),
  savePlayback: vi.fn(async () => ({ ok: true })),
  openFile: vi.fn(async () => {}),
  openFolder: vi.fn(async () => {}),
  openExternalUrl: vi.fn(async () => {}),
}))
afterEach(() => vi.clearAllMocks())
const file: FileItem = {
  name: 'lesson.mp4',
  path: 'lesson.mp4',
  title: 'Audio lesson',
  size: 1000,
  mtime: 100,
  tags: ['Study'],
  note: 'Useful lesson',
  playback: { position: 30, duration: 120, finished: false, updated: 100 },
}
const props = {
  file,
  collections: [],
  autoPlay: false,
  windowMode: false,
  onClose: vi.fn(),
  onRefresh: vi.fn(),
  onToast: vi.fn(),
}

it('edits tags and notes without changing files and retains an unsuccessful draft', async () => {
  const user = userEvent.setup()
  render(<MediaDetails {...props} />)
  await user.clear(screen.getByLabelText('Tags (comma separated)'))
  await user.type(screen.getByLabelText('Tags (comma separated)'), 'Study， Audio')
  await user.clear(screen.getByLabelText('Note'))
  await user.type(screen.getByLabelText('Note'), 'Find the bitrate explanation')
  vi.mocked(saveFileDetails).mockRejectedValueOnce(new Error('disk full'))
  await user.click(screen.getByRole('button', { name: 'Save tags and note' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('disk full')
  expect(screen.getByLabelText('Note')).toHaveValue('Find the bitrate explanation')
  await user.click(screen.getByRole('button', { name: 'Save tags and note' }))
  await waitFor(() =>
    expect(saveFileDetails).toHaveBeenLastCalledWith(
      'lesson.mp4',
      ['Study', 'Audio'],
      'Find the bitrate explanation',
    ),
  )
})

it('resumes supported media and saves progress in order on pause and close', async () => {
  const { unmount } = render(<MediaDetails {...props} />)
  const video = screen.getByLabelText('Video preview') as HTMLVideoElement
  Object.defineProperty(video, 'duration', { value: 120, configurable: true })
  fireEvent.loadedMetadata(video)
  expect(video.currentTime).toBe(30)
  // Merely opening a detail view does not overwrite previous playback progress.
  fireEvent.timeUpdate(video)
  expect(savePlayback).not.toHaveBeenCalled()
  fireEvent.play(video)
  video.currentTime = 45
  fireEvent.timeUpdate(video)
  video.currentTime = 55
  fireEvent.pause(video)
  await waitFor(() => expect(savePlayback).toHaveBeenCalledTimes(2))
  expect(vi.mocked(savePlayback).mock.calls.map((call) => call.slice(1))).toEqual([
    [45, 120],
    [55, 120],
  ])
  video.currentTime = 65
  fireEvent.timeUpdate(video)
  unmount()
  await waitFor(() => expect(savePlayback).toHaveBeenLastCalledWith('lesson.mp4', 65, 120))
})

it('marks playback finished and offers a fallback for unsupported codecs', async () => {
  render(<MediaDetails {...props} />)
  const video = screen.getByLabelText('Video preview') as HTMLVideoElement
  Object.defineProperty(video, 'duration', { value: 120, configurable: true })
  fireEvent.play(video)
  fireEvent.ended(video)
  await waitFor(() => expect(savePlayback).toHaveBeenCalledWith('lesson.mp4', 120, 120))
  fireEvent.error(video)
  expect(screen.getByRole('alert')).toHaveTextContent('system player')
  expect(screen.getByRole('link', { name: 'Download' })).toHaveAttribute('download', file.name)
})

it('pauses the other in-app player when switching between video and persistent audio', () => {
  const audio = new AudioPlayerController()
  const pauseAudio = vi.spyOn(audio, 'pause').mockImplementation(() => {})
  const view = render(<MediaDetails {...props} audioPlayer={audio} />)
  const video = screen.getByLabelText('Video preview') as HTMLVideoElement
  const pauseVideo = vi.spyOn(video, 'pause').mockImplementation(() => {})
  fireEvent.play(video)
  expect(pauseAudio).toHaveBeenCalledOnce()
  window.dispatchEvent(new Event('grab-audio-started'))
  expect(pauseVideo).toHaveBeenCalledOnce()
  view.unmount()
  window.dispatchEvent(new Event('grab-audio-started'))
  expect(pauseVideo).toHaveBeenCalledOnce()
})
