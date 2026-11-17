import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { resetTokenCache } from '../../api/client'
import { MediaExportSettings } from './MediaExportSettings'

afterEach(() => vi.unstubAllGlobals())

it('saves a folder, explains a rejected one and can turn export off', async () => {
  resetTokenCache()
  const posts: unknown[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (_url: string, init?: RequestInit) => {
      if (!init?.method) return new Response(JSON.stringify({ folder: '', ready: false, error: '' }))
      const body = JSON.parse(String(init.body))
      posts.push(body)
      if (body.folder === 'D:\Downloads\inside')
        return new Response(JSON.stringify({ error: 'Choose a folder outside the download folder.' }), {
          status: 400,
        })
      return new Response(JSON.stringify({ folder: body.folder, ready: !!body.folder, error: '' }))
    }),
  )
  const user = userEvent.setup()
  render(<MediaExportSettings />)
  expect(await screen.findByText('Off. Enter the folder your media server watches.')).toBeInTheDocument()
  const input = screen.getByRole('textbox', { name: 'Media server folder' })
  await user.type(input, 'D:\Downloads\inside')
  await user.click(screen.getByRole('button', { name: 'Save' }))
  expect(await screen.findByText('Choose a folder outside the download folder.')).toBeInTheDocument()
  await user.clear(input)
  await user.type(input, 'D:\Media\YouTube')
  await user.click(screen.getByRole('button', { name: 'Save' }))
  expect(await screen.findByText(/Turn on export for a subscription/)).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Turn off' }))
  await waitFor(() => expect(posts.at(-1)).toEqual({ action: 'folder', folder: '' }))
})

it('stays hidden in clients that may not change it', async () => {
  resetTokenCache()
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(JSON.stringify({ error: 'no' }), { status: 403 })),
  )
  render(<MediaExportSettings />)
  await new Promise((resolve) => setTimeout(resolve, 20))
  expect(screen.queryByText('Media server folder')).not.toBeInTheDocument()
})
