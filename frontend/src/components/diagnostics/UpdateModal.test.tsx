import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { resetTokenCache } from '../../api/client'
import { UpdateModal } from './UpdateModal'

afterEach(() => vi.unstubAllGlobals())

function serve(previous?: string) {
  const calls: string[] = []
  let installed = '2026.11.10'
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      const path = String(url).split('?')[0]
      calls.push(`${init?.method ?? 'GET'} ${path}`)
      if (path === '/api/ytdlp/rollback') {
        installed = previous ?? installed
        return new Response(JSON.stringify({ ok: true }))
      }
      if (path === '/api/ytdlp/update-status')
        return new Response(
          JSON.stringify({
            status: 'done',
            lines: ['Successfully installed'],
            before: '',
            after: '',
            error: '',
            extras: 'default',
          }),
        )
      return new Response(
        JSON.stringify({
          running: '2026.11.10',
          installed,
          previous: installed === previous ? '' : previous,
          latest: '2026.11.10',
          newer: false,
          needs_restart: installed !== '2026.11.10',
        }),
      )
    }),
  )
  return calls
}

const props = { open: true, onClose: () => {}, onRestart: () => {}, onToast: () => {}, onChecked: () => {} }

it('offers to go back to the version the last update replaced', async () => {
  resetTokenCache()
  const calls = serve('2026.10.01')
  render(<UpdateModal {...props} />)
  expect(
    await screen.findByText('If downloads stopped working after the last update, go back to 2026.10.01.'),
  ).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Go back to 2026.10.01' }))
  await waitFor(
    () => expect(screen.getByText('Update installed. Restart the service to use it.')).toBeInTheDocument(),
    {
      timeout: 4000,
    },
  )
  expect(calls).toContain('POST /api/ytdlp/rollback')
  expect(screen.queryByRole('button', { name: /Go back to/ })).not.toBeInTheDocument()
})

it('shows no rollback when there is nothing to go back to', async () => {
  resetTokenCache()
  serve(undefined)
  render(<UpdateModal {...props} />)
  expect(await screen.findByText(/Latest on PyPI/)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /Go back to/ })).not.toBeInTheDocument()
})

it('tests a newer release, keeps the current version on a regression and can install it anyway', async () => {
  resetTokenCache()
  const posts: Array<Record<string, unknown>> = []
  const statuses = [
    {
      status: 'running',
      phase: 'probing',
      target: '2026.12.01',
      probes: [{ site: 'YouTube', verdict: 'testing' }],
    },
    {
      status: 'tested',
      phase: '',
      target: '2026.12.01',
      verdict: 'regression',
      probes: [
        { site: 'YouTube', verdict: 'regression', current: true, new: false, error: 'Unable to extract' },
        { site: 'Internet Archive', verdict: 'fine', current: true, new: true, error: '' },
      ],
    },
  ]
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      const path = String(url).split('?')[0]
      if (init?.method === 'POST') {
        posts.push({ path, ...JSON.parse(String(init.body || '{}')) })
        return new Response(
          JSON.stringify(path.endsWith('/settings') ? { test_recent_sites: true } : { ok: true }),
        )
      }
      if (path === '/api/ytdlp/update-status') {
        const next = statuses.length > 1 ? statuses.shift() : statuses[0]
        return new Response(
          JSON.stringify({ lines: [], before: '', after: '', error: '', extras: 'default', ...next }),
        )
      }
      return new Response(
        JSON.stringify({
          running: '2026.11.10',
          installed: '2026.11.10',
          latest: '2026.12.01',
          newer: true,
          needs_restart: false,
        }),
      )
    }),
  )
  const user = userEvent.setup()
  render(<UpdateModal {...props} />)
  await user.click(await screen.findByRole('checkbox'))
  await user.click(screen.getByRole('button', { name: 'Test and update yt-dlp' }))
  expect(await screen.findByText('Broken by the new version', {}, { timeout: 4000 })).toBeInTheDocument()
  expect(
    screen.getByText(/broke a site that works now, so your current version was kept/),
  ).toBeInTheDocument()
  expect(screen.getByText('Unable to extract')).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Install 2026.12.01 anyway' }))
  expect(posts).toEqual([
    { path: '/api/ytdlp/settings', test_recent_sites: true },
    { path: '/api/ytdlp/update', extras: 'default', test: true },
    { path: '/api/ytdlp/update', extras: 'default', version: '2026.12.01' },
  ])
})
