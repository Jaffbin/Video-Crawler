import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { useState } from 'react'
import { DEFAULT_OPTIONS } from '../../lib/options'
import { NewDownloadPanel } from './NewDownloadPanel'
import { resetTokenCache } from '../../api/client'

afterEach(() => vi.unstubAllGlobals())

it.each(['skip', 'download'])('asks about saved files before adding tasks (%s)', async (action) => {
  const calls: any[] = []
  resetTokenCache()
  vi.stubGlobal(
    'fetch',
    vi.fn(async (_url, init) => {
      const body = JSON.parse(init.body)
      calls.push(body)
      return new Response(
        JSON.stringify(
          body.existing_action
            ? { ids: action === 'download' ? ['1234abcd'] : [], skipped_existing: action === 'skip' ? 1 : 0 }
            : {
                ids: [],
                existing: [
                  {
                    url: 'https://example.com/video',
                    path: 'old.mp4',
                    name: 'old.mp4',
                    profile_known: true,
                    settings_match: false,
                    profile: { mode: 'mp4', quality: '720' },
                  },
                ],
              },
        ),
      )
    }),
  )
  const onAdded = vi.fn(),
    user = userEvent.setup()
  render(<Panel onAdded={onAdded} />)
  await user.type(screen.getByRole('textbox', { name: /links to download/i }), 'https://example.com/video')
  await user.click(screen.getByRole('button', { name: 'Start download' }))
  const dialog = await screen.findByRole('dialog', { name: 'Already downloaded' })
  expect(onAdded).not.toHaveBeenCalled()
  expect(dialog).toHaveTextContent('720p')
  expect(dialog).toHaveTextContent('Saved settings differ.')
  await user.click(
    within(dialog).getByRole('button', {
      name: action === 'skip' ? 'Use existing files' : 'Download another copy',
    }),
  )
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  expect(calls[1].existing_action).toBe(action)
  expect(onAdded).toHaveBeenCalledTimes(action === 'download' ? 1 : 0)
})

function Panel({
  onAdded = vi.fn(),
  onToast = vi.fn(),
}: {
  onAdded?: () => void
  onToast?: (message: string, error?: boolean) => void
}) {
  const [options, setOptions] = useState(DEFAULT_OPTIONS)
  return (
    <NewDownloadPanel
      options={options}
      onOptionsChange={(patch) => setOptions((current) => ({ ...current, ...patch }))}
      playwright
      onToast={onToast}
      onAdded={onAdded}
    />
  )
}

it('offers understandable MP3 quality presets and sends the chosen bitrate', async () => {
  const requests: any[] = []
  resetTokenCache()
  vi.stubGlobal(
    'fetch',
    vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      requests.push(JSON.parse(String(init?.body || '{}')))
      return new Response(JSON.stringify({ ids: ['1234abcd'] }))
    }),
  )
  const user = userEvent.setup()
  render(<Panel />)
  await user.click(screen.getByRole('radio', { name: 'Audio' }))
  await user.click(screen.getByRole('radio', { name: 'MP3 audio' }))
  expect(screen.getByRole('combobox', { name: 'Audio quality' })).toHaveValue('192')
  await user.selectOptions(screen.getByRole('combobox', { name: 'Audio quality' }), '320')
  expect(screen.getByLabelText('Download summary')).toHaveTextContent(
    'Audio · MP3 · 320 kbps · Highest quality',
  )
  expect(screen.queryByRole('combobox', { name: 'Maximum video quality' })).not.toBeInTheDocument()
  await user.type(screen.getByRole('textbox', { name: /links to download/i }), 'https://example.com/audio')
  await user.click(screen.getByRole('button', { name: 'Start download' }))
  await waitFor(() => expect(requests.at(-1)?.options).toMatchObject({ mode: 'mp3', abr: 320 }))
})

it('keeps source audio independent of bitrate and video settings with a separate cover', async () => {
  const requests: any[] = []
  resetTokenCache()
  vi.stubGlobal(
    'fetch',
    vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      requests.push(JSON.parse(String(init?.body || '{}')))
      return new Response(JSON.stringify({ ids: ['1234abcd'] }))
    }),
  )
  const user = userEvent.setup()
  render(<Panel />)
  await user.click(screen.getByRole('radio', { name: 'Audio' }))
  await user.click(screen.getByRole('radio', { name: 'Keep source audio' }))
  expect(screen.queryByRole('combobox', { name: 'Audio quality' })).not.toBeInTheDocument()
  expect(screen.queryByText('Download subtitles')).not.toBeInTheDocument()
  await user.click(screen.getByText('Subtitles and cover', { selector: 'summary' }))
  await user.click(screen.getByRole('checkbox', { name: 'Save a separate cover' }))
  expect(screen.getByLabelText('Download summary')).toHaveTextContent(
    'Source audio · best available · no re-encoding',
  )
  expect(screen.getByLabelText('Download summary')).toHaveTextContent('Separate cover included')
  expect(screen.getByLabelText('Download summary')).not.toHaveTextContent('Cover embedded')
  await user.type(screen.getByRole('textbox', { name: /links to download/i }), 'https://example.com/audio')
  await user.click(screen.getByRole('button', { name: 'Start download' }))
  await waitFor(() => expect(requests.at(-1)?.options).toMatchObject({ mode: 'original', cover: true }))
})

it('preserves a saved custom MP3 bitrate', () => {
  render(
    <NewDownloadPanel
      options={{ ...DEFAULT_OPTIONS, mode: 'mp3', abr: 256 }}
      onOptionsChange={vi.fn()}
      playwright
      onToast={vi.fn()}
      onAdded={vi.fn()}
    />,
  )
  expect(screen.getByRole('combobox', { name: 'Audio quality' })).toHaveValue('256')
  expect(screen.getByLabelText('Download summary')).toHaveTextContent('256 kbps · Custom bitrate')
})

it('keeps preview optional and sends selected playlist entries to the queue', async () => {
  const requests: Array<{ url: string; body: any }> = []
  resetTokenCache()
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      requests.push({ url, body: JSON.parse(String(init?.body || '{}')) })
      return new Response(
        JSON.stringify(
          url === '/api/probe'
            ? {
                kind: 'playlist',
                title: 'Playlist',
                count: 2,
                playlist_entries: [
                  { index: 1, title: 'First' },
                  { index: 2, title: 'Second' },
                ],
              }
            : { ids: ['1234abcd'] },
        ),
        { status: 200 },
      )
    }),
  )
  const user = userEvent.setup()
  render(<Panel />)
  await user.type(screen.getByRole('textbox', { name: /links to download/i }), 'https://example.com/playlist')
  expect(screen.getByRole('button', { name: 'Start download' })).toBeEnabled()
  await user.click(screen.getByRole('button', { name: 'Analyze link' }))
  await user.click(await screen.findByRole('checkbox', { name: '1. First' }))
  await user.click(screen.getByRole('button', { name: 'Clear selection' }))
  expect(screen.getByRole('button', { name: 'Start download' })).toBeDisabled()
  await user.click(screen.getByRole('checkbox', { name: '2. Second' }))
  expect(
    within(screen.getByLabelText('Download summary')).getByText(/1 selected playlist entries/),
  ).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Start download' }))
  await waitFor(() => expect(requests.some((request) => request.url === '/api/jobs')).toBe(true))
  expect(requests.find((request) => request.url === '/api/jobs')?.body.options).toMatchObject({
    items: '2',
    no_playlist: false,
  })
  await user.type(screen.getByRole('textbox', { name: /links to download/i }), 'https://example.com/next')
  await user.click(screen.getByRole('button', { name: 'Start download' }))
  await waitFor(() => expect(requests.filter((request) => request.url === '/api/jobs')).toHaveLength(2))
  expect(requests.filter((request) => request.url === '/api/jobs')[1].body.options.items).toBe('')
})

it('summarizes output and companions and chooses a folder only on request', async () => {
  const choose = vi.fn(async () => {})
  const user = userEvent.setup()
  const props = {
    options: { ...DEFAULT_OPTIONS, quality: '1080', subs: true, cover: true, keep_cover: true },
    onOptionsChange: vi.fn(),
    playwright: true,
    onToast: vi.fn(),
    onAdded: vi.fn(),
    root: 'D:/Videos',
    onChooseFolder: choose,
  }
  const { rerender } = render(<NewDownloadPanel {...props} />)
  const summary = screen.getByLabelText('Download summary')
  expect(summary).toHaveTextContent('Video · MP4 · up to 1080p')
  expect(summary).toHaveTextContent('Subtitles included · Cover embedded · Separate cover included')
  expect(summary).toHaveTextContent('Save to: D:/Videos')
  expect(choose).not.toHaveBeenCalled()
  await user.click(screen.getByRole('button', { name: 'Change folder' }))
  expect(choose).toHaveBeenCalledOnce()
  rerender(<NewDownloadPanel {...props} folderChangeBlocked />)
  expect(screen.getByRole('button', { name: 'Change folder' })).toBeDisabled()
  rerender(<NewDownloadPanel {...props} options={{ ...props.options, mode: 'image' }} />)
  expect(summary).toHaveTextContent('Direct image · original image format')
  expect(summary).not.toHaveTextContent('Cover embedded')
})

it('does not attach a late preview to an edited link', async () => {
  let resolve!: (value: Response) => void
  vi.stubGlobal(
    'fetch',
    vi.fn(
      () =>
        new Promise<Response>((done) => {
          resolve = done
        }),
    ),
  )
  const user = userEvent.setup()
  render(<Panel />)
  const input = screen.getByRole('textbox', { name: /links to download/i })
  await user.type(input, 'https://example.com/first')
  await user.click(screen.getByRole('button', { name: 'Analyze link' }))
  await user.clear(input)
  await user.type(input, 'https://example.com/second')
  resolve(new Response(JSON.stringify({ kind: 'video', title: 'Wrong preview' }), { status: 200 }))
  await waitFor(() => expect(screen.getByRole('button', { name: 'Analyze link' })).toBeEnabled())
  expect(screen.queryByText('Wrong preview')).not.toBeInTheDocument()
})

it('reports skipped duplicates instead of claiming they were added', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(JSON.stringify({ ids: [], duplicates: 1 }))),
  )
  const onToast = vi.fn()
  const user = userEvent.setup()
  render(<Panel onToast={onToast} />)
  await user.click(screen.getByRole('textbox', { name: /links to download/i }))
  await user.paste('https://example.com/video')
  await user.click(screen.getByRole('button', { name: 'Start download' }))
  expect(onToast).toHaveBeenCalledWith('Skipped 1 downloads already in the queue')
  expect(onToast).not.toHaveBeenCalledWith('Added 1 downloads to the queue')
})

it('switches to cover and image modes, hides media conversion settings and submits the selected mode', async () => {
  const requests: Array<{ mode?: string }> = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      requests.push(JSON.parse(String(init?.body)).options)
      return new Response(JSON.stringify({ ids: ['1234abcd'] }))
    }),
  )
  const user = userEvent.setup()
  render(<Panel />)
  await user.click(screen.getByRole('radio', { name: 'Images' }))
  await user.click(screen.getByRole('radio', { name: 'Video cover' }))
  expect(screen.queryByLabelText('Maximum video quality')).not.toBeInTheDocument()
  expect(screen.queryByText('Download subtitles')).not.toBeInTheDocument()
  expect(screen.queryByText('Download the cover and embed it in the file')).not.toBeInTheDocument()
  expect(screen.getByText('Paste a video page or playlist link to save only its covers.')).toBeInTheDocument()
  await user.click(screen.getByRole('radio', { name: 'Direct image' }))
  await user.click(screen.getByRole('textbox', { name: /links to download/i }))
  await user.paste('https://example.com/photo')
  await user.click(screen.getByRole('button', { name: 'Start download' }))
  expect(requests[0].mode).toBe('image')
})
