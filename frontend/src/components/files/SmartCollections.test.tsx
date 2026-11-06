import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { CollectionManager } from './CollectionManager'
import { SmartCollections } from './SmartCollections'
import type { FileItem } from '../../types/api'

const files: FileItem[] = [
  { path: 'clip.mp4', name: 'clip.mp4', size: 20, mtime: 1, tags: ['my tag'], favorite: true },
  { path: 'song.mp3', name: 'song.mp3', size: 20, mtime: 1, tags: ['my tag'] },
]
afterEach(() => vi.unstubAllGlobals())

it('previews all rules and saves a multiword tag as one condition', async () => {
  const requests: unknown[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url, init) => {
      expect(url).toBe('/api/library/smart-collections')
      requests.push(JSON.parse(init.body))
      return new Response(JSON.stringify({ id: 'new' }))
    }),
  )
  const user = userEvent.setup(),
    refresh = vi.fn()
  render(<SmartCollections files={files} collections={[]} onRefresh={refresh} onToast={vi.fn()} />)
  expect(screen.getByRole('button', { name: 'Create smart collection' })).toBeDisabled()
  await user.type(screen.getByRole('textbox', { name: 'Smart collection name' }), 'Study')
  await user.type(screen.getByRole('textbox', { name: 'Tag matches' }), 'my tag')
  expect(screen.getByRole('status')).toHaveTextContent('2 files currently match')
  await user.selectOptions(screen.getByRole('combobox', { name: 'Media type' }), 'video')
  expect(screen.getByRole('status')).toHaveTextContent('1 files currently match')
  await user.selectOptions(screen.getByRole('combobox', { name: 'Favorite status' }), 'false')
  expect(screen.getByRole('status')).toHaveTextContent('0 files currently match')
  await user.click(screen.getByRole('button', { name: 'Create smart collection' }))
  await waitFor(() => expect(refresh).toHaveBeenCalledOnce())
  expect(requests).toEqual([
    { action: 'create', name: 'Study', rules: { tag: 'my tag', kind: 'video', favorite: false } },
  ])
})

it('edits rules whose source or format has no current files and confirms deletion', async () => {
  const requests: unknown[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (_url, init) => {
      requests.push(JSON.parse(init.body))
      return new Response(JSON.stringify({ id: 'old' }))
    }),
  )
  const user = userEvent.setup(),
    refresh = vi.fn()
  render(
    <SmartCollections
      files={files}
      collections={[
        { id: 'old', name: 'Old', rules: { source: 'old.example', format: '.flac', recent_days: 14 } },
      ]}
      onRefresh={refresh}
      onToast={vi.fn()}
    />,
  )
  await user.click(screen.getByRole('button', { name: 'Edit smart collection Old' }))
  expect(screen.getByRole('combobox', { name: 'Source site' })).toHaveValue('old.example')
  expect(screen.getByRole('combobox', { name: 'Format' })).toHaveValue('.flac')
  expect(screen.getByRole('combobox', { name: 'Saved within the last' })).toHaveValue('14')
  await user.click(screen.getByRole('button', { name: 'Save smart collection' }))
  await waitFor(() => expect(refresh).toHaveBeenCalledTimes(1))
  expect(requests[0]).toEqual({
    action: 'update',
    id: 'old',
    name: 'Old',
    rules: { source: 'old.example', format: '.flac', recent_days: 14 },
  })
  await user.click(screen.getByRole('button', { name: 'Delete smart collection Old' }))
  expect(requests).toHaveLength(1)
  await user.click(screen.getByRole('button', { name: 'Confirm delete collection' }))
  await waitFor(() => expect(refresh).toHaveBeenCalledTimes(2))
  expect(requests[1]).toEqual({ action: 'delete', id: 'old' })
})

it('shows write errors and keeps the rule draft available for retry', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(JSON.stringify({ error: 'disk full' }), { status: 409 })),
  )
  const user = userEvent.setup()
  render(<SmartCollections files={files} collections={[]} onRefresh={vi.fn()} onToast={vi.fn()} />)
  await user.type(screen.getByRole('textbox', { name: 'Smart collection name' }), 'Study')
  await user.selectOptions(screen.getByRole('combobox', { name: 'Media type' }), 'video')
  await user.click(screen.getByRole('button', { name: 'Create smart collection' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('disk full')
  expect(screen.getByRole('textbox', { name: 'Smart collection name' })).toHaveValue('Study')
  expect(screen.getByRole('button', { name: 'Create smart collection' })).toBeEnabled()
})

it('opens smart collections inside the existing manager and views a built-in', async () => {
  const user = userEvent.setup(),
    view = vi.fn()
  render(
    <CollectionManager
      collections={[]}
      files={files}
      onRefresh={vi.fn()}
      onToast={vi.fn()}
      onViewSmart={view}
    />,
  )
  await user.click(screen.getByRole('button', { name: 'Manage collections' }))
  await user.click(screen.getByRole('button', { name: 'Smart collections' }))
  const builtins = screen.getByRole('region', { name: 'Built-in smart collections' })
  await user.click(within(builtins).getByRole('button', { name: 'Favorites' }))
  expect(view).toHaveBeenCalledWith('builtin:favorites')
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
})
