import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { QuickDownload } from './QuickDownload'
import { DEFAULT_OPTIONS, STORAGE_KEY } from '../../lib/options'
import { resetTokenCache } from '../../api/client'

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  delete window.pywebview
})

it('keeps the quick-download draft when an existing-file notice is canceled', async () => {
  resetTokenCache()
  vi.stubGlobal(
    'fetch',
    vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            ids: [],
            existing: [
              { url: 'https://example.com/video', path: 'old.mp4', name: 'old.mp4', profile_known: false },
            ],
          }),
        ),
    ),
  )
  const user = userEvent.setup()
  render(<QuickDownload root="D:/Media" online />)
  await user.type(screen.getByRole('textbox'), 'https://example.com/video')
  await user.click(screen.getByRole('button', { name: 'Start download' }))
  expect(await screen.findByRole('dialog', { name: 'Already downloaded' })).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Cancel' }))
  expect(screen.getByRole('textbox')).toHaveValue('https://example.com/video')
})

it('shows a failed copy request inside the notice and keeps the draft', async () => {
  resetTokenCache()
  const response = {
    ids: [],
    existing: [{ url: 'https://example.com/video', path: 'old.mp4', name: 'old.mp4', profile_known: false }],
  }
  vi.stubGlobal(
    'fetch',
    vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(response)))
      .mockRejectedValueOnce(new Error('Connection lost')),
  )
  const user = userEvent.setup()
  render(<QuickDownload root="D:/Media" online />)
  await user.type(screen.getByRole('textbox'), 'https://example.com/video')
  await user.click(screen.getByRole('button', { name: 'Start download' }))
  await screen.findByRole('dialog', { name: 'Already downloaded' })
  await user.click(screen.getByRole('button', { name: 'Download another copy' }))
  await waitFor(() => expect(screen.getByRole('dialog')).toHaveTextContent('Connection lost'))
  expect(screen.getByRole('textbox')).toHaveValue('https://example.com/video')
})

it('requires one link and explicitly excludes playlists and companions while reusing connection settings', async () => {
  const requests: any[] = []
  localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({
      ...DEFAULT_OPTIONS,
      proxy: 'http://127.0.0.1:7890',
      cover: true,
      subs: true,
      items: '1-20',
    }),
  )
  resetTokenCache()
  vi.stubGlobal(
    'fetch',
    vi.fn(async (_url, init) => {
      requests.push(JSON.parse(init.body))
      return new Response(JSON.stringify({ ids: ['1234abcd'] }))
    }),
  )
  const user = userEvent.setup()
  render(<QuickDownload root="D:/Media" online />)
  expect(screen.getByText('D:/Media')).toBeInTheDocument()
  await user.type(screen.getByRole('textbox'), 'https://example.com/a https://example.com/b')
  await user.click(screen.getByRole('button', { name: 'Start download' }))
  expect(screen.getByRole('alert')).toHaveTextContent('Paste one HTTP or HTTPS link')
  expect(requests).toHaveLength(0)
  await user.clear(screen.getByRole('textbox'))
  await user.type(screen.getByRole('textbox'), 'https://example.com/watch?v=a&list=b')
  await user.click(screen.getByRole('radio', { name: 'Audio' }))
  await user.selectOptions(screen.getByLabelText('Audio quality'), '320')
  await user.click(screen.getByRole('button', { name: 'Start download' }))
  await screen.findByText('Added 1 downloads to the queue')
  expect(requests[0]).toMatchObject({
    urls: ['https://example.com/watch?v=a&list=b'],
    options: {
      mode: 'mp3',
      abr: 320,
      proxy: 'http://127.0.0.1:7890',
      no_playlist: true,
      items: '',
      cover: false,
      subs: false,
    },
  })
  expect(JSON.parse(localStorage.getItem(STORAGE_KEY)!)).toMatchObject({
    mode: 'mp4',
    cover: true,
    subs: true,
  })
  expect(screen.getByRole('textbox')).toHaveValue('')
})

it('preserves a failed URL for retry, reports duplicates and opens the main queue', async () => {
  const fetch = vi
    .fn()
    .mockRejectedValueOnce(new Error('Network unavailable'))
    .mockResolvedValueOnce(new Response(JSON.stringify({ ids: [], duplicates: 1 })))
  vi.stubGlobal('fetch', fetch)
  const show = vi.fn().mockResolvedValue(undefined)
  window.pywebview = { api: { show_main: show } }
  const user = userEvent.setup()
  render(<QuickDownload root="D:/Media" online />)
  await user.type(screen.getByRole('textbox'), 'https://example.com/a')
  await user.click(screen.getByRole('button', { name: 'Start download' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Network unavailable')
  expect(screen.getByRole('textbox')).toHaveValue('https://example.com/a')
  await user.click(screen.getByRole('button', { name: 'Start download' }))
  await screen.findByText('Skipped 1 downloads already in the queue')
  await user.click(screen.getByRole('button', { name: 'View queue' }))
  expect(show).toHaveBeenCalledWith('queue')
})

it('reads clipboard only after a click and disables submitting while offline', async () => {
  const user = userEvent.setup()
  const read = vi.spyOn(navigator.clipboard, 'readText').mockResolvedValue('https://example.com/audio')
  const props = { root: 'D:/Media', online: false }
  const { rerender } = render(<QuickDownload {...props} />)
  expect(read).not.toHaveBeenCalled()
  await user.click(screen.getByRole('button', { name: 'Read clipboard' }))
  expect(screen.getByRole('textbox')).toHaveValue('https://example.com/audio')
  expect(screen.getByRole('button', { name: 'Start download' })).toBeDisabled()
  rerender(<QuickDownload {...props} online />)
  expect(screen.getByRole('button', { name: 'Start download' })).toBeEnabled()
  read.mockRejectedValue(new Error('Denied'))
  await user.click(screen.getByRole('button', { name: 'Read clipboard' }))
  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Press Ctrl+V instead'))
})
