import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { resetTokenCache } from '../../api/client'
import type { ScheduleView } from '../../types/api'
import { ScheduleControl, ScheduleNotice } from './ScheduleControl'

afterEach(() => vi.unstubAllGlobals())

const off: ScheduleView = {
  enabled: false,
  window: null,
  limit: null,
  holding: false,
  next_start: null,
  limit_active: null,
}

it('saves a night window and a busy-hours speed limit', async () => {
  resetTokenCache()
  const posts: unknown[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (_url: string, init?: RequestInit) => {
      posts.push(JSON.parse(String(init?.body)))
      return new Response(JSON.stringify(off))
    }),
  )
  const changed = vi.fn()
  const toast = vi.fn()
  const user = userEvent.setup()
  render(<ScheduleControl schedule={off} onChanged={changed} onToast={toast} />)
  await user.click(screen.getByRole('button', { name: 'Download schedule' }))
  expect(screen.getByLabelText('From')).toBeDisabled() // nothing applies until the schedule is on
  await user.click(screen.getByLabelText('Use a download schedule'))
  expect(screen.getByLabelText('From')).toHaveValue('23:00')
  await user.click(screen.getByLabelText('Limit speed during busy hours'))
  await user.clear(screen.getByLabelText('Speed limit'))
  await user.type(screen.getByLabelText('Speed limit'), '1M')
  await user.click(screen.getByRole('button', { name: 'Save schedule' }))
  await waitFor(() => expect(changed).toHaveBeenCalledOnce())
  expect(posts).toEqual([
    {
      schedule: {
        enabled: true,
        window: { start: '23:00', end: '07:00' },
        limit: { start: '09:00', end: '18:00', rate: '1M' },
      },
    },
  ])
  expect(toast).toHaveBeenCalledWith('Download schedule saved')
})

it('shows why the app rejected a schedule and keeps the dialog open', async () => {
  resetTokenCache()
  vi.stubGlobal(
    'fetch',
    vi.fn(
      async () =>
        new Response(JSON.stringify({ error: 'Choose a download window, a speed limit, or both.' }), {
          status: 400,
        }),
    ),
  )
  const user = userEvent.setup()
  render(<ScheduleControl schedule={off} onChanged={vi.fn()} onToast={vi.fn()} />)
  await user.click(screen.getByRole('button', { name: 'Download schedule' }))
  await user.click(screen.getByLabelText('Use a download schedule'))
  await user.click(screen.getByLabelText('Only start downloads during these hours'))
  await user.click(screen.getByRole('button', { name: 'Save schedule' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Choose a download window')
  expect(screen.getByRole('button', { name: 'Save schedule' })).toBeInTheDocument()
})

it('opens with the saved schedule', async () => {
  const user = userEvent.setup()
  const saved: ScheduleView = {
    ...off,
    enabled: true,
    window: null,
    limit: { start: '08:00', end: '20:00', rate: '500K' },
  }
  render(<ScheduleControl schedule={saved} onChanged={vi.fn()} onToast={vi.fn()} />)
  expect(screen.getByRole('button', { name: /Download schedule/ })).toHaveTextContent('On')
  await user.click(screen.getByRole('button', { name: /Download schedule/ }))
  expect(screen.getByLabelText('Only start downloads during these hours')).not.toBeChecked()
  expect(screen.getByLabelText('Busy from')).toHaveValue('08:00')
  expect(screen.getByLabelText('Speed limit')).toHaveValue('500K')
})

it('tells the user when queued downloads will start or are being limited', () => {
  const start = new Date(2026, 10, 15, 23, 0).getTime() / 1000
  const time = new Date(start * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  const { rerender } = render(
    <ScheduleNotice schedule={{ ...off, enabled: true, holding: true, next_start: start }} />,
  )
  expect(screen.getByRole('status')).toHaveTextContent(
    `Queued downloads wait for the download window and start at ${time}.`,
  )
  rerender(<ScheduleNotice schedule={{ ...off, enabled: true, limit_active: '2M' }} />)
  expect(screen.getByRole('status')).toHaveTextContent('Busy hours: new downloads are limited to 2M/s.')
  rerender(<ScheduleNotice schedule={off} />)
  expect(screen.queryByRole('status')).not.toBeInTheDocument()
})
