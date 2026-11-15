import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { resetTokenCache } from '../../api/client'
import type { FileItem, TranscriptionStatus } from '../../types/api'
import { Transcripts, timestamp } from './Transcripts'

afterEach(() => vi.unstubAllGlobals())

const files = [{ name: 'talk.mp4', path: 'talk.mp4', size: 1, mtime: 1, title: 'Keynote' }] as FileItem[]

function status(overrides: Partial<TranscriptionStatus> = {}): TranscriptionStatus {
  return {
    available: true,
    install_hint: 'Install transcription support: pip install -e ".[ai]", then restart Video Grabber.',
    model: 'small',
    models: ['tiny', 'base', 'small', 'medium', 'large-v3-turbo'],
    items: {},
    pending: 0,
    current: null,
    ...overrides,
  }
}

function serve(current: TranscriptionStatus) {
  const requests: Array<{ url: string; body?: unknown }> = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      requests.push({ url, body: init?.body ? JSON.parse(String(init.body)) : undefined })
      if (url.startsWith('/api/transcripts/search'))
        return new Response(
          JSON.stringify({
            query: 'python',
            results: [
              {
                path: 'talk.mp4',
                name: 'talk.mp4',
                title: 'Keynote',
                kind: 'video',
                hits: [{ start: 754.2, text: '今天讲 Python' }],
              },
            ],
          }),
        )
      if (init?.method === 'POST') {
        const body = JSON.parse(String(init.body))
        if (body.action === 'model') current = { ...current, model: body.model }
        if (body.action === 'cancel') current = { ...current, items: {} }
      }
      return new Response(JSON.stringify(current))
    }),
  )
  return requests
}

it('formats timestamps for short and long media', () => {
  expect(timestamp(5)).toBe('0:05')
  expect(timestamp(754.9)).toBe('12:34')
  expect(timestamp(3725)).toBe('1:02:05')
})

it('finds what was said and links to that moment', async () => {
  resetTokenCache()
  const requests = serve(status())
  const user = userEvent.setup()
  render(<Transcripts files={files} onToast={vi.fn()} />)
  await user.click(screen.getByRole('button', { name: 'Transcripts' }))
  await user.type(await screen.findByRole('searchbox', { name: 'Search what was said' }), 'python')
  await user.click(screen.getByRole('button', { name: 'Search' }))
  const link = await screen.findByRole('link', { name: 'Play Keynote from 12:34' })
  expect(link).toHaveAttribute('href', expect.stringMatching(/talk\.mp4#t=754\.2$/))
  expect(screen.getByText('今天讲 Python')).toBeInTheDocument()
  expect(requests.some((request) => request.url === '/api/transcripts/search?q=python')).toBe(true)
})

it('shows progress, stops transcription and changes the model', async () => {
  resetTokenCache()
  const requests = serve(
    status({
      items: {
        'talk.mp4': { status: 'running', percent: 42.4, error: '', language: '' },
        'gone.mp4': { status: 'error', percent: 0, error: 'Missing file', language: '' },
      },
    }),
  )
  const toast = vi.fn()
  const user = userEvent.setup()
  render(<Transcripts files={files} onToast={toast} />)
  await user.click(screen.getByRole('button', { name: 'Transcripts' }))
  expect(await screen.findByText('Transcribing 42%')).toBeInTheDocument()
  expect(screen.getByText('Keynote')).toBeInTheDocument()
  expect(screen.getByText('Missing file')).toBeInTheDocument()
  await user.selectOptions(screen.getByLabelText('Speech model'), 'base')
  await waitFor(() => expect(requests.at(-1)?.body).toEqual({ action: 'model', model: 'base' }))
  await user.click(screen.getByRole('button', { name: 'Stop transcribing' }))
  await waitFor(() => expect(toast).toHaveBeenCalledWith('Transcription stopped'))
  expect(screen.queryByText('Transcribing 42%')).not.toBeInTheDocument()
})

it('explains how to install transcription support when it is missing', async () => {
  resetTokenCache()
  serve(status({ available: false }))
  const user = userEvent.setup()
  render(<Transcripts files={files} onToast={vi.fn()} />)
  await user.click(screen.getByRole('button', { name: 'Transcripts' }))
  expect(await screen.findByText(/pip install -e "\.\[ai\]"/)).toBeInTheDocument()
})
