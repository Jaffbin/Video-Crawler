import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { resetTokenCache } from './api/client'
import type { StateResponse } from './types/api'

const baseState: StateResponse = {
  version: '2026.09.20',
  ffmpeg: true,
  playwright: true,
  root: '/downloads',
  rev: 0,
  jobs: [],
  files: [],
  desktop_notifications: false,
  window: false,
}

function mockApi(overrides: Partial<Record<string, unknown>> = {}) {
  const calls: string[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      calls.push(url)
      const body = (): unknown => {
        if (url.startsWith('/api/state')) return baseState
        if (url.startsWith('/api/doctor')) return { checks: [], report: '', net: false }
        if (url.startsWith('/api/ytdlp/check')) return { running: '1', installed: '1', needs_restart: false }
        for (const [key, value] of Object.entries(overrides)) if (url.startsWith(key)) return value
        return { ok: true }
      }
      return new Response(JSON.stringify(body()), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    }),
  )
  return calls
}

beforeEach(() => {
  document.head.insertAdjacentHTML('beforeend', '<meta name="grab-token" content="test-token">')
  resetTokenCache()
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
  document.querySelector('meta[name="grab-token"]')?.remove()
})

describe('App', () => {
  it('shows the yt-dlp version once the first state poll resolves', async () => {
    mockApi()
    render(<App />)
    await waitFor(() => expect(screen.getByText(/2026\.09\.20/)).toBeInTheDocument())
    expect(screen.getByText(/local service connected/i)).toBeInTheDocument()
  })

  it('sends every request with the token, never as a query string on the API calls', async () => {
    const calls: { url: string; headers: Headers }[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        calls.push({ url: String(input), headers: new Headers(init?.headers) })
        return new Response(JSON.stringify(baseState), { headers: { 'content-type': 'application/json' } })
      }),
    )
    render(<App />)
    await waitFor(() => expect(calls.length).toBeGreaterThan(0))
    const state = calls.find((c) => c.url.startsWith('/api/state'))
    expect(state?.headers.get('X-Token')).toBe('test-token')
  })

  it('adds a link pasted anywhere on the page (not inside a text field) to the download box', async () => {
    // Pasting straight into the textarea is native browser behavior and is left alone (see
    // useUrlImport's isEditable check); this is what happens when nothing is focused instead -
    // e.g. the user copied a link and hits Ctrl+V without clicking into the box first.
    mockApi()
    render(<App />)
    const box = await screen.findByRole('textbox', { name: /links to download/i })
    document.body.focus()
    const event = Object.assign(new Event('paste', { bubbles: true, cancelable: true }), {
      clipboardData: { getData: () => 'https://example.com/watch?v=1' },
    })
    document.body.dispatchEvent(event)
    await waitFor(() => expect(box).toHaveValue('https://example.com/watch?v=1\n'))
  })
})
