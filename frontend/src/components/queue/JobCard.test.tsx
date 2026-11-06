import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { JobCard } from './JobCard'
import type { Job } from '../../types/api'

const job: Job = {
  id: '1234abcd',
  url: 'https://example.com/video',
  title: 'Video',
  status: 'error',
  stage: '',
  percent: 0,
  speed: '',
  eta: '',
  item: '',
  error: 'ERROR: technical failure --internal-path',
  mode: 'mp4',
  created: 1,
  finished: 2,
  notes: [],
  files: [],
}
afterEach(() => vi.unstubAllGlobals())

it('keeps the full long title in the title tooltip', () => {
  const title = 'Long video title #收藏 #music '.repeat(30)
  render(<JobCard job={{ ...job, title }} windowMode={false} onChanged={() => {}} onToast={() => {}} />)
  expect(screen.getByRole('heading', { name: title.trim() })).toHaveAttribute('title', title)
})

it('shows a plain error and opens setup help without exposing raw errors', async () => {
  const user = userEvent.setup()
  const help = vi.fn()
  render(
    <JobCard
      job={{ ...job, error_kind: 'ffmpeg' }}
      windowMode={false}
      onChanged={() => {}}
      onToast={() => {}}
      onHelp={help}
    />,
  )
  expect(screen.getByText('Video and audio processing needs attention.')).toBeInTheDocument()
  expect(screen.queryByText(job.error)).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Resolve setup issue' }))
  expect(help).toHaveBeenCalledOnce()
})

it('does not use a browser session until the user chooses and confirms', async () => {
  const fetch = vi.fn(async () => new Response(JSON.stringify({ ids: ['retry'], duplicates: false })))
  vi.stubGlobal('fetch', fetch)
  const user = userEvent.setup()
  const changed = vi.fn()
  render(
    <JobCard
      job={{ ...job, error_kind: 'login' }}
      windowMode={false}
      onChanged={changed}
      onToast={() => {}}
    />,
  )
  await user.click(screen.getByRole('button', { name: 'Use browser sign-in' }))
  expect(fetch).not.toHaveBeenCalled()
  expect(screen.getByRole('button', { name: 'Use this browser and retry' })).toBeDisabled()
  await user.selectOptions(screen.getByLabelText('Browser you signed in with'), 'chrome')
  await user.click(screen.getByRole('button', { name: 'Use this browser and retry' }))
  await waitFor(() => expect(changed).toHaveBeenCalledOnce())
  expect(fetch).toHaveBeenCalledWith(
    '/api/jobs/1234abcd/retry-browser',
    expect.objectContaining({ body: JSON.stringify({ browser: 'chrome' }) }),
  )
})

it.each([
  ['video.mp4', 'Play video'],
  ['audio.mp3', 'Play audio'],
  ['picture.jpg', 'View image'],
])('highlights the correct completed-file action for %s', (name, label) => {
  render(
    <JobCard
      job={{ ...job, status: 'done', error: '', files: [{ name, path: name, complete: true }] }}
      windowMode={false}
      onChanged={() => {}}
      onToast={() => {}}
    />,
  )
  expect(screen.getByText('Your download is ready.')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: label })).toHaveAttribute('target', '_blank')
  expect(screen.getByRole('button', { name: 'Show in folder' })).toBeEnabled()
})

it('opens the download folder for disk errors and preserves technical logs on demand', async () => {
  const fetch = vi.fn(
    async (input: RequestInfo | URL) =>
      new Response(JSON.stringify(String(input).endsWith('/log') ? { lines: ['disk full'] } : { ok: true })),
  )
  vi.stubGlobal('fetch', fetch)
  const user = userEvent.setup()
  render(
    <JobCard
      job={{ ...job, error_kind: 'disk_full' }}
      windowMode={true}
      onChanged={() => {}}
      onToast={() => {}}
    />,
  )
  await user.click(screen.getByRole('button', { name: 'Open download folder' }))
  expect(fetch).toHaveBeenCalledWith('/api/open-folder', expect.anything())
  await user.click(screen.getByRole('button', { name: 'Log' }))
  expect(await screen.findByText(/ERROR: technical failure/)).toBeInTheDocument()
})
