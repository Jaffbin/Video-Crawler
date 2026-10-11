import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { FileGallery } from './FileGallery'
import { displayFilename, filterLibrary } from '../../lib/library'
import type { FileItem } from '../../types/api'

const files: FileItem[] = [
  {
    name: 'video.mp4',
    path: 'video.mp4',
    size: 200,
    mtime: 10,
    source: 'example.com',
    source_url: 'https://example.com/video',
  },
  { name: 'audio.mp3', path: 'audio.mp3', size: 100, mtime: 20 },
]
afterEach(() => vi.unstubAllGlobals())

it('filters favorites and collections together and resets both filters', async () => {
  const user = userEvent.setup()
  render(
    <FileGallery
      files={[{ ...files[0], favorite: true, collections: ['study', 'music'] }, files[1]]}
      collections={[
        { id: 'study', name: 'Study' },
        { id: 'music', name: 'Music' },
      ]}
      windowMode={false}
      onRefresh={vi.fn()}
      onToast={vi.fn()}
    />,
  )
  await user.click(screen.getByRole('button', { name: 'Favorites' }))
  expect(screen.queryByText('audio.mp3')).not.toBeInTheDocument()
  await user.selectOptions(screen.getByRole('combobox', { name: 'Collection' }), 'music')
  expect(screen.getByText('video.mp4')).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Reset filters' }))
  expect(screen.getByText('audio.mp3')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Favorites' })).toHaveAttribute('aria-pressed', 'false')
})

it('favorites a file and adds or removes classification without moving it', async () => {
  const requests: any[] = []
  const fetch = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
    requests.push(JSON.parse(String(init?.body || '{}')))
    return new Response(JSON.stringify({ processed: ['video.mp4'], failed: [] }))
  })
  vi.stubGlobal('fetch', fetch)
  const refresh = vi.fn()
  const props = {
    files,
    collections: [{ id: 'study', name: 'Study' }],
    windowMode: false,
    onRefresh: refresh,
    onToast: vi.fn(),
  }
  const user = userEvent.setup()
  const { rerender } = render(<FileGallery {...props} />)
  await user.click(screen.getByRole('button', { name: 'Favorite video.mp4' }))
  await waitFor(() => expect(refresh).toHaveBeenCalledOnce())
  expect(requests[0]).toEqual({ items: ['video.mp4'], favorite: true })
  await user.click(screen.getByRole('button', { name: 'Manage collections for video.mp4' }))
  await user.click(screen.getByRole('button', { name: 'Add to Study' }))
  await waitFor(() => expect(refresh).toHaveBeenCalledTimes(2))
  expect(requests[1]).toEqual({ items: ['video.mp4'], collection_id: 'study' })
  rerender(<FileGallery {...props} files={[{ ...files[0], collections: ['study'] }, files[1]]} />)
  await user.click(screen.getByRole('button', { name: 'Remove from Study' }))
  await waitFor(() => expect(refresh).toHaveBeenCalledTimes(3))
  expect(requests[2]).toEqual({ items: ['video.mp4'], collection_id: 'study', remove: true })
  expect(fetch.mock.calls.every(([url]) => String(url) === '/api/library/organize')).toBe(true)
})

it('retains the previous favorite state and reports a failed save', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(JSON.stringify({ error: 'disk full' }), { status: 409 })),
  )
  const user = userEvent.setup()
  const refresh = vi.fn()
  render(<FileGallery files={files} windowMode={false} onRefresh={refresh} onToast={vi.fn()} />)
  await user.click(screen.getByRole('button', { name: 'Favorite video.mp4' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('disk full')
  expect(screen.getByRole('button', { name: 'Favorite video.mp4' })).toHaveAttribute('aria-pressed', 'false')
  expect(refresh).not.toHaveBeenCalled()
})

it('favorites selected files and keeps failed items selected for retry', async () => {
  const fetch = vi.fn(
    async (_input: RequestInfo | URL, _init?: RequestInit) =>
      new Response(
        JSON.stringify({
          processed: ['video.mp4'],
          failed: [{ item: 'audio.mp3', error: 'missing' }],
        }),
      ),
  )
  vi.stubGlobal('fetch', fetch)
  const user = userEvent.setup()
  const refresh = vi.fn()
  render(<FileGallery files={files} windowMode={false} onRefresh={refresh} onToast={vi.fn()} />)
  await user.click(screen.getByRole('button', { name: 'Select this page' }))
  await user.click(screen.getByRole('button', { name: 'Favorite selected' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Some files could not be changed')
  expect(JSON.parse(String(fetch.mock.calls[0][1]?.body))).toEqual({
    items: ['video.mp4', 'audio.mp3'],
    favorite: true,
  })
  expect(screen.getByRole('checkbox', { name: 'Select video.mp4' })).not.toBeChecked()
  expect(screen.getByRole('checkbox', { name: 'Select audio.mp3' })).toBeChecked()
  expect(refresh).toHaveBeenCalledOnce()
})

it('offers undo for a single move and restores using its recovery ID', async () => {
  const fetch = vi.fn(
    async (input: RequestInfo | URL) =>
      new Response(
        JSON.stringify(
          String(input) === '/api/library/trash'
            ? { id: 'recovery-one' }
            : { processed: ['recovery-one'], failed: [] },
        ),
      ),
  )
  vi.stubGlobal('fetch', fetch)
  const toast = vi.fn()
  const refresh = vi.fn()
  const user = userEvent.setup()
  render(<FileGallery files={files} windowMode={false} onRefresh={refresh} onToast={toast} />)
  await user.click(screen.getByRole('button', { name: 'Move video.mp4 to recovery' }))
  await user.click(
    within(screen.getByRole('dialog', { name: 'Move to recovery' })).getByRole('button', {
      name: 'Move to recovery',
    }),
  )
  await waitFor(() => expect(toast).toHaveBeenCalled())
  const action = toast.mock.calls[0][2]
  expect(action.label).toBe('Undo')
  expect(fetch).toHaveBeenCalledTimes(1)
  await action.onClick()
  expect(fetch).toHaveBeenLastCalledWith(
    '/api/library/batch',
    expect.objectContaining({ body: JSON.stringify({ items: ['recovery-one'], action: 'restore' }) }),
  )
  expect(refresh).toHaveBeenCalledTimes(2)
})

it('offers batch undo only for successful moves and retains only failed restores for retry', async () => {
  let restores = 0
  const fetch = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
    const body = JSON.parse(String(init?.body))
    const result =
      body.action === 'trash'
        ? { processed: ['video.mp4', 'audio.mp3'], failed: [], recovery_ids: ['one', 'two'] }
        : ++restores === 1
          ? { processed: ['one'], failed: [{ item: 'two', error: 'locked' }] }
          : { processed: ['two'], failed: [] }
    return new Response(JSON.stringify(result))
  })
  vi.stubGlobal('fetch', fetch)
  const toast = vi.fn()
  const user = userEvent.setup()
  render(<FileGallery files={files} windowMode={false} onRefresh={() => {}} onToast={toast} />)
  await user.click(screen.getByRole('button', { name: 'Select this page' }))
  await user.click(screen.getByRole('button', { name: 'Move selected to recovery' }))
  await user.click(screen.getByRole('button', { name: 'Confirm move' }))
  await waitFor(() => expect(toast).toHaveBeenCalled())
  const action = toast.mock.calls[0][2]
  await expect(action.onClick()).rejects.toThrow('Could not undo')
  await action.onClick()
  expect(fetch).toHaveBeenLastCalledWith(
    '/api/library/batch',
    expect.objectContaining({ body: JSON.stringify({ items: ['two'], action: 'restore' }) }),
  )
})

it('confirms batch moves and retains failed selections for retry', async () => {
  const fetch = vi.fn(
    async () =>
      new Response(
        JSON.stringify({ processed: ['video.mp4'], failed: [{ item: 'audio.mp3', error: 'locked' }] }),
        { status: 200 },
      ),
  )
  vi.stubGlobal('fetch', fetch)
  const user = userEvent.setup()
  render(<FileGallery files={files} windowMode={false} onRefresh={() => {}} onToast={() => {}} />)
  await user.click(screen.getByRole('button', { name: 'Select this page' }))
  await user.click(screen.getByRole('button', { name: 'Move selected to recovery' }))
  expect(fetch).not.toHaveBeenCalled()
  await user.click(screen.getByRole('button', { name: 'Confirm move' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Some files could not be changed')
  expect(screen.getByRole('checkbox', { name: 'Select video.mp4' })).not.toBeChecked()
  expect(screen.getByRole('checkbox', { name: 'Select audio.mp3' })).toBeChecked()
  expect(fetch).toHaveBeenCalledWith(
    '/api/library/batch',
    expect.objectContaining({ body: JSON.stringify({ items: ['video.mp4', 'audio.mp3'], action: 'trash' }) }),
  )
})

it('splits large selections into bounded batches and preserves unfinished work after a request fails', async () => {
  const many = Array.from({ length: 205 }, (_, i) => ({
    name: `video-${i}.mp4`,
    path: `video-${i}.mp4`,
    size: 1,
    mtime: 1000 - i,
  }))
  let calls = 0
  const fetch = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
    calls++
    const items = JSON.parse(String(init?.body)).items as string[]
    return new Response(
      JSON.stringify(calls === 1 ? { processed: items, failed: [] } : { error: 'File locked' }),
      { status: calls === 1 ? 200 : 409 },
    )
  })
  vi.stubGlobal('fetch', fetch)
  render(<FileGallery files={many} windowMode={false} onRefresh={() => {}} onToast={() => {}} />)
  const selection = within(screen.getByRole('group', { name: 'Library selection' }))
  const pagination = within(screen.getByRole('group', { name: 'Library pagination' }))
  fireEvent.change(screen.getByLabelText('Files per page'), { target: { value: '100' } })
  fireEvent.click(selection.getByRole('button', { name: 'Select this page' }))
  fireEvent.click(pagination.getByRole('button', { name: 'Next' }))
  fireEvent.click(selection.getByRole('button', { name: 'Select this page' }))
  fireEvent.click(pagination.getByRole('button', { name: 'Next' }))
  fireEvent.click(selection.getByRole('button', { name: 'Select this page' }))
  fireEvent.click(selection.getByRole('button', { name: 'Move selected to recovery' }))
  fireEvent.click(screen.getByRole('button', { name: 'Confirm move' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Some files could not be changed')
  expect(fetch).toHaveBeenCalledTimes(2)
  expect(JSON.parse(String(fetch.mock.calls[0][1]?.body)).items).toHaveLength(200)
  expect(JSON.parse(String(fetch.mock.calls[1][1]?.body)).items).toHaveLength(5)
  expect(screen.getByRole('checkbox', { name: 'Select video-200.mp4' })).toBeChecked()
})

it('confirms bulk permanent deletion and shows space including companions', async () => {
  const fetch = vi.fn(
    async (input: RequestInfo | URL) =>
      new Response(
        JSON.stringify(
          String(input) === '/api/library/trash'
            ? {
                items: [
                  { id: 'a', path: 'video.mp4', removed: 10, size: 300 },
                  { id: 'b', path: 'audio.mp3', removed: 10, size: 100 },
                ],
              }
            : { processed: ['a', 'b'], failed: [] },
        ),
        { status: 200 },
      ),
  )
  vi.stubGlobal('fetch', fetch)
  const user = userEvent.setup()
  render(<FileGallery files={[]} windowMode={false} onRefresh={() => {}} onToast={() => {}} />)
  await user.click(screen.getByRole('button', { name: 'Recovery' }))
  await user.click(await screen.findByRole('button', { name: 'Select all' }))
  await user.click(screen.getByRole('button', { name: 'Delete selected permanently' }))
  expect(screen.getByText('Space to free', { exact: false })).toHaveTextContent('400 B')
  expect(fetch).toHaveBeenCalledTimes(1)
  await user.click(screen.getByRole('button', { name: 'Confirm permanent deletion' }))
  expect(await screen.findByText('No recovery files.')).toBeInTheDocument()
})

it('restores selected recovery files together', async () => {
  const fetch = vi.fn(
    async (input: RequestInfo | URL) =>
      new Response(
        JSON.stringify(
          String(input) === '/api/library/trash'
            ? { items: [{ id: 'a', path: 'video.mp4', removed: 10 }] }
            : { processed: ['a'], failed: [] },
        ),
        { status: 200 },
      ),
  )
  vi.stubGlobal('fetch', fetch)
  const user = userEvent.setup()
  render(<FileGallery files={[]} windowMode={false} onRefresh={() => {}} onToast={() => {}} />)
  await user.click(screen.getByRole('button', { name: 'Recovery' }))
  await user.click(await screen.findByRole('button', { name: 'Select all' }))
  await user.click(screen.getByRole('button', { name: 'Restore selected' }))
  expect(await screen.findByText('No recovery files.')).toBeInTheDocument()
  expect(fetch).toHaveBeenLastCalledWith(
    '/api/library/batch',
    expect.objectContaining({ body: JSON.stringify({ items: ['a'], action: 'restore' }) }),
  )
})

it('adds local repair to Queue with one click', async () => {
  const fetch = vi.fn(
    async () => new Response(JSON.stringify({ ids: ['repair'], duplicates: false }), { status: 200 }),
  )
  vi.stubGlobal('fetch', fetch)
  const user = userEvent.setup()
  const toast = vi.fn()
  render(
    <FileGallery
      files={[{ ...files[0], complete: false, can_repair: true }]}
      windowMode={false}
      onRefresh={() => {}}
      onToast={toast}
    />,
  )
  await user.click(screen.getByRole('button', { name: 'Repair' }))
  await waitFor(() =>
    expect(toast).toHaveBeenCalledWith(
      'Repair added to Queue. Your original files are kept until it succeeds.',
    ),
  )
  expect(fetch).toHaveBeenCalledWith(
    '/api/library/repair',
    expect.objectContaining({ body: JSON.stringify({ path: 'video.mp4' }) }),
  )
})

it('shortens visible filenames without changing file URLs or download names', () => {
  const name = '越想克制卻講越多！？Vivi不講魔性口頭禪就不會說話了！【Hololive中文】[WCgcSFC1GsU].mp4'
  render(
    <FileGallery
      files={[{ ...files[0], name, path: name }]}
      windowMode={false}
      onRefresh={() => {}}
      onToast={() => {}}
    />,
  )
  expect(screen.queryByText('From date')).not.toBeInTheDocument()
  expect(screen.queryByText('To date')).not.toBeInTheDocument()
  expect(screen.getByText(displayFilename(name))).toHaveAttribute('title', name)
  expect(screen.getByRole('link', { name: 'Download' })).toHaveAttribute('download', name)
  expect(displayFilename('short.mp4')).toBe('short.mp4')
  expect(displayFilename('😀😀😀😀😀.mp4', 3)).toBe('😀😀😀... .mp4')
})

it('requires confirmation to purge recovery files and allows cancellation', async () => {
  const fetch = vi.fn(
    async (input: RequestInfo | URL) =>
      new Response(
        JSON.stringify(
          String(input) === '/api/library/trash'
            ? { items: [{ id: 'abc', path: 'video.mp4', removed: 10 }] }
            : { ok: true },
        ),
        { status: 200 },
      ),
  )
  vi.stubGlobal('fetch', fetch)
  const user = userEvent.setup()
  const onRefresh = vi.fn()
  render(<FileGallery files={[]} windowMode={false} onRefresh={onRefresh} onToast={() => {}} />)
  await user.click(screen.getByRole('button', { name: 'Recovery' }))
  await user.click(await screen.findByRole('button', { name: 'Delete permanently' }))
  expect(fetch).toHaveBeenCalledTimes(1)
  await user.click(screen.getByRole('button', { name: 'Cancel' }))
  expect(fetch).toHaveBeenCalledTimes(1)
  await user.click(screen.getByRole('button', { name: 'Delete permanently' }))
  await user.click(screen.getByRole('button', { name: 'Confirm permanent deletion' }))
  await waitFor(() => expect(onRefresh).toHaveBeenCalledOnce())
  expect(fetch).toHaveBeenLastCalledWith(
    '/api/library/purge',
    expect.objectContaining({ body: JSON.stringify({ id: 'abc' }) }),
  )
  expect(screen.getByText('No recovery files.')).toBeInTheDocument()
})

it('retains recovery deletion confirmation on failure for retry', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(
      async (input: RequestInfo | URL) =>
        new Response(
          JSON.stringify(
            String(input) === '/api/library/trash'
              ? { items: [{ id: 'abc', path: 'video.mp4', removed: 10 }] }
              : { error: 'File locked' },
          ),
          { status: String(input) === '/api/library/trash' ? 200 : 409 },
        ),
    ),
  )
  const user = userEvent.setup()
  render(<FileGallery files={[]} windowMode={false} onRefresh={() => {}} onToast={() => {}} />)
  await user.click(screen.getByRole('button', { name: 'Recovery' }))
  await user.click(await screen.findByRole('button', { name: 'Delete permanently' }))
  await user.click(screen.getByRole('button', { name: 'Confirm permanent deletion' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('File locked')
  expect(screen.getByRole('button', { name: 'Confirm permanent deletion' })).toBeEnabled()
})

it('labels unfinished streams while preserving file actions', () => {
  const partial: FileItem = {
    name: 'video.f400.mp4',
    path: 'video.f400.mp4',
    size: 200,
    mtime: 10,
    complete: false,
  }
  render(
    <FileGallery files={[partial, files[1]]} windowMode={false} onRefresh={() => {}} onToast={() => {}} />,
  )
  expect(screen.getByText(/Processing incomplete/)).toHaveTextContent(
    'Retry the original task to finish processing.',
  )
  const row = screen.getByText(partial.name).closest('li')!
  expect(within(row).getByRole('link', { name: 'Download' })).toHaveAttribute('download', partial.name)
  expect(screen.getAllByRole('listitem')).toHaveLength(2)
})

it('combines source, format, date and sort filters without mutating the list', () => {
  expect(filterLibrary(files, '', 'unknown', '.mp3', '', '', 'newest').map((file) => file.name)).toEqual([
    'audio.mp3',
  ])
  expect(filterLibrary(files, 'video', 'example.com', '.mp4', '', '', 'name')).toHaveLength(1)
  expect(filterLibrary(files, '', '', '', '2026-01-01', '', 'newest')).toEqual([])
  expect(filterLibrary(files, '', '', '', '', '', 'largest')[0].name).toBe('video.mp4')
  expect(files[0].name).toBe('video.mp4')
})

it('keeps a rename conflict visible and sends no move until confirmation', async () => {
  const fetch = vi.fn(
    async () =>
      new Response(JSON.stringify({ error: 'A file with that name already exists' }), { status: 409 }),
  )
  vi.stubGlobal('fetch', fetch)
  const user = userEvent.setup()
  const onRefresh = vi.fn()
  render(<FileGallery files={files} windowMode={false} onRefresh={onRefresh} onToast={() => {}} />)
  expect(screen.getByRole('link', { name: 'Open original page' })).toHaveAttribute(
    'href',
    'https://example.com/video',
  )
  await user.click(screen.getByRole('button', { name: 'Rename video.mp4' }))
  const input = screen.getByRole('textbox', { name: /filename/i })
  await user.clear(input)
  await user.type(input, 'occupied.mp4')
  await user.click(screen.getByRole('button', { name: 'Save' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('already exists')
  expect(onRefresh).not.toHaveBeenCalled()
  await user.click(screen.getByRole('button', { name: 'Cancel' }))
  await user.click(screen.getByRole('button', { name: 'Move video.mp4 to recovery' }))
  expect(fetch).toHaveBeenCalledTimes(1)
  expect(screen.getByRole('dialog', { name: 'Move to recovery' })).toBeInTheDocument()
})

it('restores a recovery item and refreshes the files', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(
      async (input: RequestInfo | URL) =>
        new Response(
          JSON.stringify(
            String(input) === '/api/library/trash'
              ? { items: [{ id: 'abc', path: 'video.mp4', removed: 10 }] }
              : { path: 'video.mp4' },
          ),
          { status: 200 },
        ),
    ),
  )
  const user = userEvent.setup()
  const onRefresh = vi.fn()
  render(<FileGallery files={[]} windowMode={false} onRefresh={onRefresh} onToast={() => {}} />)
  await user.click(screen.getByRole('button', { name: 'Recovery' }))
  await user.click(await screen.findByRole('button', { name: 'Restore' }))
  await waitFor(() => expect(onRefresh).toHaveBeenCalledOnce())
  expect(screen.getByText('No recovery files.')).toBeInTheDocument()
})

it('paginates the complete filtered list and resets when changing page size or query', async () => {
  const many = Array.from({ length: 61 }, (_, i) => ({
    name: `video-${i}.mp4`,
    path: `video-${i}.mp4`,
    size: 10,
    mtime: 100 - i,
  }))
  const user = userEvent.setup()
  render(<FileGallery files={many} windowMode={false} onRefresh={() => {}} onToast={() => {}} />)
  expect(screen.getAllByRole('listitem')).toHaveLength(50)
  expect(screen.getByText('Showing 1–50 of 61')).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Next' }))
  expect(screen.getAllByRole('listitem')).toHaveLength(11)
  expect(screen.getByText('Showing 51–61 of 61')).toBeInTheDocument()
  await user.selectOptions(screen.getByLabelText('Files per page'), '25')
  expect(screen.getAllByRole('listitem')).toHaveLength(25)
  expect(screen.getByText('Showing 1–25 of 61')).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Next' }))
  await user.type(screen.getByRole('searchbox'), 'video-60')
  expect(screen.getAllByRole('listitem')).toHaveLength(1)
  expect(screen.getByText('Showing 1–1 of 1')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled()
})

it('shows why a scan is incomplete instead of implying that all files are searchable', () => {
  render(
    <FileGallery
      files={files}
      windowMode={false}
      onRefresh={() => {}}
      onToast={() => {}}
      scan={{
        checked: 20000,
        media_count: 2,
        entry_limit: 20000,
        max_depth: 4,
        incomplete: true,
        reasons: ['entry_limit', 'depth_limit', 'unreadable'],
      }}
    />,
  )
  expect(screen.getByRole('status')).toHaveTextContent('Search and filters cover discovered files only')
  expect(screen.getByRole('status')).toHaveTextContent('Scan limit reached (20000 entries)')
  expect(screen.getByRole('status')).toHaveTextContent('4 directory levels')
  expect(screen.getByRole('status')).toHaveTextContent('Check permissions and refresh')
})

it('filters pictures, loads lazy thumbnails and opens a recoverable image preview', async () => {
  const image: FileItem = { name: 'photo.png', path: 'images/photo.png', kind: 'image', size: 30, mtime: 30 }
  const user = userEvent.setup()
  render(<FileGallery files={[...files, image]} windowMode={false} onRefresh={() => {}} onToast={() => {}} />)
  const thumbnail = screen.getByRole('button', { name: 'Preview photo.png' }).querySelector('img')!
  expect(thumbnail).toHaveAttribute('loading', 'lazy')
  expect(thumbnail.src).toContain('/files/images/photo.png')
  await user.selectOptions(screen.getByLabelText('Media type'), 'image')
  expect(screen.getAllByRole('listitem')).toHaveLength(1)
  expect(screen.queryByRole('link', { name: 'Play' })).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Preview photo.png' }))
  const dialog = screen.getByRole('dialog', { name: 'Image preview' })
  const fullImage = within(dialog).getByRole('img', { name: 'photo.png' })
  await user.click(within(dialog).getByRole('button', { name: 'Original size' }))
  expect(within(dialog).getByRole('button', { name: 'Fit to window' })).toBeInTheDocument()
  fireEvent.error(fullImage)
  expect(within(dialog).getByRole('alert')).toHaveTextContent('Open the original file instead')
  expect(within(dialog).getByRole('link', { name: 'Download' })).toHaveAttribute('download', 'photo.png')
  await user.keyboard('{Escape}')
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
})
