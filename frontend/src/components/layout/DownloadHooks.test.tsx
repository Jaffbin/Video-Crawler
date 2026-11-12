import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { resetTokenCache } from '../../api/client'
import type { HookRun, HooksStatus } from '../../types/api'
import { DownloadHooks } from './DownloadHooks'

afterEach(() => vi.unstubAllGlobals())

const base: HooksStatus = {
  path: 'C:\\cfg\\hooks.json',
  exists: false,
  enabled: false,
  error: null,
  hooks: {},
  notifications: [],
  language: 'en',
  pending: 0,
  recent: [],
}

function run(overrides: Partial<HookRun>): HookRun {
  return {
    event: 'download_completed',
    job_id: 'a1',
    kind: 'program',
    target: 'after.bat',
    outcome: 'ok',
    exit_code: 0,
    duration: 0.4,
    detail: '',
    finished: 1,
    ...overrides,
  }
}

function serve(get: HooksStatus, posts: Record<string, unknown> = {}) {
  const requests: Array<{ url: string; method?: string }> = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      requests.push({ url, method: init?.method })
      return new Response(JSON.stringify(init?.method === 'POST' ? posts[url] : get))
    }),
  )
  return requests
}

it('starts off and opens the settings file without offering to edit anything here', async () => {
  resetTokenCache()
  const requests = serve(base, { '/api/hooks/open-config': { ...base, exists: true } })
  const user = userEvent.setup()
  render(<DownloadHooks />)
  expect(await screen.findByText('Off. Turn it on in the settings file.')).toBeInTheDocument()
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Send a test notification' })).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: /what is this\?/i }))
  expect(screen.getByRole('note')).toHaveTextContent(/only be set in the settings file/)
  await user.click(screen.getByRole('button', { name: 'Open settings file' }))
  await waitFor(() => expect(requests.at(-1)).toEqual({ url: '/api/hooks/open-config', method: 'POST' }))
})

it('shows programs and notification targets with the latest result of each', async () => {
  resetTokenCache()
  serve({
    ...base,
    exists: true,
    enabled: true,
    hooks: {
      download_completed: { command: ['C:\\Scripts\\after.bat', '--fast'], timeout_seconds: 60 },
    },
    notifications: [
      { type: 'discord', target: 'discord.com', events: ['download_completed', 'download_failed'] },
      { type: 'ntfy', target: 'ntfy.sh', events: ['download_failed'] },
    ],
    recent: [
      run({ kind: 'notification', target: 'ntfy (ntfy.sh)', outcome: 'failed', exit_code: null }),
      run({ outcome: 'failed', exit_code: 2, detail: 'file not found' }),
    ],
  })
  render(<DownloadHooks />)
  expect(await screen.findByText('On')).toBeInTheDocument()
  expect(screen.getByText('after.bat')).toHaveAttribute('title', 'C:\\Scripts\\after.bat --fast')
  expect(screen.getByText('Discord (discord.com)')).toBeInTheDocument()
  expect(screen.getByText(/ntfy \(ntfy\.sh\)/, { selector: 'dd' })).toHaveTextContent(
    'ntfy (ntfy.sh), failed downloads only',
  )
  expect(screen.getByText('Last run: Ended with an error (code 2)')).toHaveAttribute(
    'title',
    'file not found',
  )
  expect(screen.getByText('Last notification to ntfy (ntfy.sh): Not sent')).toBeInTheDocument()
})

it('sends a test notification while turned off and lists channels that failed', async () => {
  resetTokenCache()
  const status: HooksStatus = {
    ...base,
    exists: true,
    notifications: [
      { type: 'discord', target: 'discord.com', events: ['download_completed'] },
      { type: 'telegram', target: 'api.telegram.org', events: ['download_completed'] },
    ],
  }
  const requests = serve(status, {
    '/api/hooks/test-notifications': {
      results: [
        { target: 'Discord (discord.com)', ok: true, detail: '' },
        { target: 'Telegram (api.telegram.org)', ok: false, detail: 'The service answered HTTP 401.' },
      ],
      status,
    },
  })
  const user = userEvent.setup()
  render(<DownloadHooks />)
  expect(await screen.findByText('Off. Turn it on in the settings file.')).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Send a test notification' }))
  expect(await screen.findByRole('status')).toHaveTextContent('Test sent to 1 of 2.')
  expect(screen.getByText('Telegram (api.telegram.org): The service answered HTTP 401.')).toBeInTheDocument()
  expect(requests.at(-1)).toEqual({ url: '/api/hooks/test-notifications', method: 'POST' })
})

it('explains a broken settings file and offers no test', async () => {
  resetTokenCache()
  serve({
    ...base,
    exists: true,
    error: 'notifications[0].url must start with https://.',
    notifications: [],
  })
  render(<DownloadHooks />)
  expect(
    await screen.findByText(
      'The settings file has a problem, so nothing runs: notifications[0].url must start with https://.',
    ),
  ).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Send a test notification' })).not.toBeInTheDocument()
})

it('stays hidden when the app does not answer', async () => {
  resetTokenCache()
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => Promise.reject(new Error('offline'))),
  )
  render(<DownloadHooks />)
  await new Promise((resolve) => setTimeout(resolve, 20))
  expect(screen.queryByText('After downloads')).not.toBeInTheDocument()
})
