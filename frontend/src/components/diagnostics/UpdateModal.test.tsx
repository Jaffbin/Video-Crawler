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
