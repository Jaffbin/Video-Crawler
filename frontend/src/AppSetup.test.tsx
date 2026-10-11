import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import App from './App'
import { resetTokenCache } from './api/client'

const restart = vi.hoisted(() => vi.fn(async () => {}))
vi.mock('./hooks/useRestart', () => ({ useRestart: () => ({ restartService: restart, restarting: false }) }))

afterEach(() => {
  vi.unstubAllGlobals()
  document.querySelector('meta[name="grab-token"]')?.remove()
  restart.mockClear()
})

it.each(['changed', 'canceled', 'failed'])(
  'changes the save folder and restarts only when needed (%s)',
  async (outcome) => {
    localStorage.clear()
    localStorage.setItem('grab-setup-seen', '1')
    window.location.hash = ''
    document.head.insertAdjacentHTML('beforeend', '<meta name="grab-token" content="test-token">')
    resetTokenCache()
    const calls: string[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input)
        calls.push(url)
        let body: unknown = { ok: true }
        let status = 200
        if (url.startsWith('/api/state'))
          body = {
            version: '1',
            ffmpeg: true,
            playwright: true,
            root: 'D:/Videos',
            rev: 0,
            jobs: [],
            files: [],
            window: false,
          }
        else if (url.startsWith('/api/doctor')) body = { checks: [], report: '', net: false }
        else if (url.startsWith('/api/subscriptions')) body = { subscriptions: [], interval_seconds: 3600 }
        else if (url.startsWith('/api/ytdlp/check'))
          body = { running: '1', installed: '1', needs_restart: false }
        else if (url === '/api/download-folder/select') {
          body =
            outcome === 'failed'
              ? { error: 'The app cannot save to this folder. Choose another folder.' }
              : { canceled: outcome === 'canceled', restart_required: outcome === 'changed', root: 'D:/New' }
          status = outcome === 'failed' ? 409 : 200
        }
        return new Response(JSON.stringify(body), { status })
      }),
    )
    const user = userEvent.setup()
    render(<App />)
    await screen.findByText('Save to: D:/Videos')
    expect(calls).not.toContain('/api/download-folder/select')
    await user.click(screen.getByRole('button', { name: 'Change folder' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Change folder' })).toBeEnabled())
    if (outcome === 'changed') expect(restart).toHaveBeenCalledOnce()
    else expect(restart).not.toHaveBeenCalled()
    if (outcome === 'failed')
      expect(
        await screen.findByText('The app cannot save to this folder. Choose another folder.'),
      ).toBeInTheDocument()
  },
)

it.each([false, true])(
  'prepares explicitly and restarts only after successful preparation (failure=%s)',
  async (failure) => {
    localStorage.clear()
    window.location.hash = ''
    document.head.insertAdjacentHTML('beforeend', '<meta name="grab-token" content="test-token">')
    resetTokenCache()
    let prepared = false
    const fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      let body: unknown = { ok: true }
      if (url.startsWith('/api/state'))
        body = {
          version: '1',
          ffmpeg: false,
          playwright: true,
          root: '/downloads',
          rev: 0,
          jobs: [],
          files: [],
          window: false,
        }
      else if (url.startsWith('/api/doctor'))
        body = {
          checks:
            prepared && !failure
              ? []
              : [{ id: 'ffmpeg', label: 'ffmpeg', status: 'error', detail: 'Missing' }],
          report: '',
          net: false,
        }
      else if (url.startsWith('/api/subscriptions')) body = { subscriptions: [], interval_seconds: 3600 }
      else if (url.startsWith('/api/ytdlp/check'))
        body = { running: '1', installed: '1', needs_restart: false }
      else if (url === '/api/setup') {
        if (init?.method === 'POST') prepared = true
        body = { ready: prepared && !failure, can_install: true, restart_required: prepared && !failure }
      } else if (url.startsWith('/api/ytdlp/update'))
        body = { status: failure ? 'error' : 'done', error: failure ? 'Installation failed' : '' }
      return new Response(JSON.stringify(body), { status: 200 })
    })
    vi.stubGlobal('fetch', fetch)
    const user = userEvent.setup()
    render(<App />)
    const guide = await screen.findByRole('dialog', { name: 'Welcome to Video Grabber' })
    expect(prepared).toBe(false)
    await user.click(within(guide).getByRole('button', { name: 'Prepare download features' }))
    if (failure) {
      expect(await screen.findByRole('alert')).toHaveTextContent('Preparation failed')
      expect(restart).not.toHaveBeenCalled()
    } else {
      await waitFor(() => expect(restart).toHaveBeenCalledOnce())
    }
    expect(prepared).toBe(true)
  },
)
