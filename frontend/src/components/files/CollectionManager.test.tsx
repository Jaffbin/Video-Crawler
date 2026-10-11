import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { CollectionManager } from './CollectionManager'

afterEach(() => vi.unstubAllGlobals())

it('creates, renames and confirms deleting a collection without any file operation', async () => {
  const requests: any[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
      expect(String(url)).toBe('/api/library/collections')
      requests.push(JSON.parse(String(init?.body)))
      return new Response(JSON.stringify({ id: 'study' }))
    }),
  )
  const user = userEvent.setup()
  const refresh = vi.fn()
  const props = { onRefresh: refresh, onToast: vi.fn() }
  const { rerender } = render(<CollectionManager {...props} collections={[]} />)
  await user.click(screen.getByRole('button', { name: 'Manage collections' }))
  await user.type(screen.getByRole('textbox', { name: 'Collection name' }), 'Study')
  await user.click(screen.getByRole('button', { name: 'Create collection' }))
  await waitFor(() => expect(refresh).toHaveBeenCalledOnce())
  expect(requests[0]).toEqual({ action: 'create', name: 'Study' })
  rerender(<CollectionManager {...props} collections={[{ id: 'study', name: 'Study' }]} />)
  await user.click(screen.getByRole('button', { name: 'Rename' }))
  await user.clear(screen.getByRole('textbox', { name: 'Collection name' }))
  await user.type(screen.getByRole('textbox', { name: 'Collection name' }), 'Learning')
  await user.click(screen.getByRole('button', { name: 'Save collection name' }))
  await waitFor(() => expect(refresh).toHaveBeenCalledTimes(2))
  expect(requests[1]).toEqual({ action: 'rename', name: 'Learning', id: 'study' })
  rerender(<CollectionManager {...props} collections={[{ id: 'study', name: 'Learning' }]} />)
  await user.click(screen.getByRole('button', { name: 'Delete collection Learning' }))
  expect(requests).toHaveLength(2)
  const dialog = screen.getByRole('dialog')
  expect(dialog).toHaveTextContent('Files and favorites will be kept.')
  await user.click(within(dialog).getByRole('button', { name: 'Confirm delete collection' }))
  await waitFor(() => expect(refresh).toHaveBeenCalledTimes(3))
  expect(requests[2]).toEqual({ action: 'delete', id: 'study' })
})
