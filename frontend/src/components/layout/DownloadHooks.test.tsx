import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { resetTokenCache } from '../../api/client'
import type { HooksStatus } from '../../types/api'
import { DownloadHooks } from './DownloadHooks'

afterEach(() => vi.unstubAllGlobals())

const base: HooksStatus = {
  path: 'C:\\cfg\\hooks.json',
  exists: false,
  enabled: false,
  error: null,
  hooks: {},
  pending: 0,
  recent: [],
}

function serve(get: HooksStatus, opened?: HooksStatus) {
  const requests: Array<{ url: string; method?: string }> = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      requests.push({ url, method: init?.method })
      return new Response(JSON.stringify(init?.method === 'POST' ? opened : get))
    }),
  )
  return requests
}

it('starts off and opens the settings file without offering to edit the program here', async () => {
  resetTokenCache()
  const requests = serve(base, { ...base, exists: true })
  const user = userEvent.setup()
  render(<DownloadHooks />)
  expect(await screen.findByText('Off. Turn it on in the settings file.')).toBeInTheDocument()
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: /what is this\?/i }))
  expect(screen.getByRole('note')).toHaveTextContent(/only be set in the settings file/)
  await user.click(screen.getByRole('button', { name: 'Open settings file' }))
  await waitFor(() => expect(requests.at(-1)).toEqual({ url: '/api/hooks/open-config', method: 'POST' }))
})

it('shows configured programs by name and the latest result', async () => {
  resetTokenCache()
  serve({
    ...base,
    exists: true,
    enabled: true,
    hooks: { download_completed: { command: ['C:\\Scripts\\after.bat', '--fast'], timeout_seconds: 60 } },
    recent: [
      {
        event: 'download_completed',
        job_id: 'a1',
        outcome: 'failed',
        exit_code: 2,
        duration: 0.4,
        detail: 'file not found',
        finished: 1,
      },
    ],
  })
  render(<DownloadHooks />)
  expect(await screen.findByText('On')).toBeInTheDocument()
  expect(screen.getByText('After a download finishes')).toBeInTheDocument()
  expect(screen.getByText('after.bat')).toHaveAttribute('title', 'C:\\Scripts\\after.bat --fast')
  expect(screen.queryByText('After a download fails')).not.toBeInTheDocument()
  expect(screen.getByText('Last run: Ended with an error (code 2)')).toHaveAttribute(
    'title',
    'file not found',
  )
})

it('explains a broken settings file and lists no programs', async () => {
  resetTokenCache()
  serve({ ...base, exists: true, error: 'enabled must be true or false.' })
  render(<DownloadHooks />)
  expect(
    await screen.findByText(
      'The settings file has a problem, so nothing runs: enabled must be true or false.',
    ),
  ).toBeInTheDocument()
  expect(screen.queryByText('After a download finishes')).not.toBeInTheDocument()
})

it('stays hidden when the app does not answer', async () => {
  resetTokenCache()
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => Promise.reject(new Error('offline'))),
  )
  render(<DownloadHooks />)
  await new Promise((resolve) => setTimeout(resolve, 20))
  expect(screen.queryByText('Run a program after downloads')).not.toBeInTheDocument()
})
