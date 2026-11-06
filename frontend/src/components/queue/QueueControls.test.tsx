import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { QueuePanel } from './QueuePanel'
import type { Job } from '../../types/api'

const jobs: Job[] = [
  {
    id: '1234abcd',
    url: 'https://example.com/video',
    title: 'Video',
    status: 'error',
    stage: '',
    percent: 0,
    speed: '',
    eta: '',
    item: '',
    error: 'Failed',
    files: [],
    mode: 'mp4',
    created: 1,
    finished: 2,
    notes: [],
  },
]
afterEach(() => vi.unstubAllGlobals())

it('keeps filtered-out task selections visible for review and clearing', async () => {
  const user = userEvent.setup()
  render(<QueuePanel jobs={jobs} windowMode={false} onChanged={vi.fn()} onToast={vi.fn()} />)
  await user.click(screen.getByRole('checkbox', { name: 'Select visible' }))
  await user.type(screen.getByRole('searchbox', { name: 'Search downloads' }), 'absent')
  expect(screen.getByText('1 selected outside this view')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'View selected' })).toBeEnabled()
  await user.click(screen.getByRole('button', { name: 'Clear selection' }))
  expect(screen.queryByRole('button', { name: 'View selected' })).not.toBeInTheDocument()
})

it('labels unfinished output separately from completed output in a failed job', () => {
  render(
    <QueuePanel
      jobs={[
        {
          ...jobs[0],
          files: [
            { name: 'ready.mp4', path: 'ready.mp4', complete: true },
            { name: 'video.f400.mp4', path: 'video.f400.mp4', complete: false },
          ],
        },
      ]}
      windowMode={false}
      onChanged={() => {}}
      onToast={() => {}}
    />,
  )
  expect(screen.getAllByText('Processing incomplete')).toHaveLength(1)
  expect(screen.getByText('video.f400.mp4').closest('li')).toHaveTextContent('Processing incomplete')
  expect(screen.getByText('ready.mp4').closest('li')).not.toHaveTextContent('Processing incomplete')
})

it('retries the selected task and refreshes after the batch response', async () => {
  const fetch = vi.fn(
    async () => new Response(JSON.stringify({ processed: ['1234abcd'], skipped: [] }), { status: 200 }),
  )
  vi.stubGlobal('fetch', fetch)
  const onChanged = vi.fn()
  const user = userEvent.setup()
  render(<QueuePanel jobs={jobs} windowMode={false} onChanged={onChanged} onToast={() => {}} />)
  expect(screen.getByRole('button', { name: 'Retry selected' })).toBeDisabled()
  await user.click(screen.getByRole('checkbox', { name: 'Select Video' }))
  await user.click(screen.getByRole('button', { name: 'Retry selected' }))
  await waitFor(() => expect(onChanged).toHaveBeenCalledOnce())
  expect(fetch.mock.calls[0]).toEqual([
    '/api/jobs/batch',
    expect.objectContaining({ body: JSON.stringify({ ids: ['1234abcd'], action: 'retry' }) }),
  ])
})

it('resumes a paused queue without restarting current downloads', async () => {
  const fetch = vi.fn(async () => new Response('{}', { status: 200 }))
  vi.stubGlobal('fetch', fetch)
  const user = userEvent.setup()
  render(<QueuePanel jobs={[]} queuePaused windowMode={false} onChanged={() => {}} onToast={() => {}} />)
  expect(screen.getByRole('status')).toHaveTextContent('Running downloads continue')
  await user.click(screen.getByRole('button', { name: 'Resume queue' }))
  expect(fetch.mock.calls[0]).toEqual(['/api/queue', expect.objectContaining({ body: '{"paused":false}' })])
})

it('shows failed entries and explains a duplicate selective retry', async () => {
  const fetch = vi.fn(async () => new Response(JSON.stringify({ ids: [], duplicates: true })))
  vi.stubGlobal('fetch', fetch)
  const onToast = vi.fn()
  const user = userEvent.setup()
  render(
    <QueuePanel
      jobs={[
        {
          ...jobs[0],
          retry_failed_only: true,
          failed_items: [
            { index: 2, title: 'Second entry', url: 'https://example.com/2', error: 'Unavailable' },
          ],
        },
      ]}
      windowMode={false}
      onChanged={() => {}}
      onToast={onToast}
    />,
  )
  expect(screen.getByText('1 failed items')).toBeInTheDocument()
  await user.click(screen.getByText('1 failed items'))
  expect(screen.getByText('2. Second entry')).toBeVisible()
  await user.click(screen.getByRole('button', { name: 'Retry failed items' }))
  expect(onToast).toHaveBeenCalledWith('This download is already in the queue')
  expect(fetch.mock.calls[0]).toEqual(['/api/jobs/1234abcd/retry', expect.anything()])
})
