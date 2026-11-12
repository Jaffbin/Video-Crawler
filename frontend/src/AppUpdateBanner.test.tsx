import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import App from './App'
import { resetTokenCache } from './api/client'

function stubApi(check: Record<string, unknown>, started: string[] = []) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const body = (): unknown => {
        if (url.startsWith('/api/state'))
          return {
            version: '2026.09.20',
            ffmpeg: true,
            playwright: true,
            root: '/downloads',
            rev: 0,
            jobs: [],
            files: [],
            window: false,
          }
        if (url.startsWith('/api/doctor')) return { checks: [], report: '', net: false }
        if (url.startsWith('/api/ytdlp/check')) return check
        if (url.startsWith('/api/ytdlp/update-status'))
          return { status: 'done', lines: [], before: '', after: '', error: '', extras: 'default' }
        if (url.startsWith('/api/ytdlp/update')) {
          started.push(String(init?.body))
          return { ok: true }
        }
        if (url.startsWith('/api/subscriptions')) return { subscriptions: [], interval_seconds: 3600 }
        return { ok: true }
      }
      return new Response(JSON.stringify(body()), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    }),
  )
}

beforeEach(() => {
  window.location.hash = ''
  localStorage.clear()
  document.head.insertAdjacentHTML('beforeend', '<meta name="grab-token" content="test-token">')
  resetTokenCache()
})

afterEach(() => {
  vi.unstubAllGlobals()
  document.querySelector('meta[name="grab-token"]')?.remove()
})

it('shows the update banner from the quiet check on load, without opening the update window first', async () => {
  stubApi({
    running: '2026.09.20',
    installed: '2026.09.20',
    latest: '2026.11.01',
    newer: true,
    needs_restart: false,
  })
  render(<App />)
  expect(await screen.findByText(/yt-dlp 2026\.11\.01 is available/)).toBeInTheDocument()
})

it('starts the update straight from the banner and remembers a dismissal for that version', async () => {
  const started: string[] = []
  stubApi(
    {
      running: '2026.09.20',
      installed: '2026.09.20',
      latest: '2026.11.01',
      newer: true,
      needs_restart: false,
    },
    started,
  )
  const user = userEvent.setup()
  render(<App />)
  await user.click(await screen.findByRole('button', { name: 'Update now' }))
  await waitFor(() => expect(started.length).toBe(1))
  expect(JSON.parse(started[0])).toEqual({ extras: 'default' })
})

it('keeps a dismissed version hidden', async () => {
  localStorage.setItem('grab-update-dismissed', '2026.11.01')
  stubApi({
    running: '2026.09.20',
    installed: '2026.09.20',
    latest: '2026.11.01',
    newer: true,
    needs_restart: false,
  })
  render(<App />)
  await waitFor(() => expect(screen.getByRole('main')).toBeInTheDocument())
  await new Promise((resolve) => setTimeout(resolve, 50))
  expect(screen.queryByText(/is available/)).not.toBeInTheDocument()
})
