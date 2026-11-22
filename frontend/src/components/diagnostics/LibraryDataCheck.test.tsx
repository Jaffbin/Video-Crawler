import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { resetTokenCache, type LibraryIntegrity } from '../../api/client'
import { LibraryDataCheck } from './LibraryDataCheck'

afterEach(() => vi.unstubAllGlobals())

const healthy: LibraryIntegrity = {
  database: 'ok',
  mirror: 'ok',
  in_sync: true,
  records: 12,
  action: '',
  detail: '',
}

function serve(first: LibraryIntegrity) {
  const posts: string[] = []
  let current = first
  vi.stubGlobal(
    'fetch',
    vi.fn(async (_url: string, init?: RequestInit) => {
      if (init?.method === 'POST') {
        posts.push(JSON.parse(String(init.body)).action)
        current = healthy
      }
      return new Response(JSON.stringify(current))
    }),
  )
  return posts
}

it('reports a healthy library and offers no repair', async () => {
  resetTokenCache()
  serve(healthy)
  render(<LibraryDataCheck />)
  await userEvent.click(screen.getByRole('button', { name: 'Check library data' }))
  expect(
    await screen.findByText('Library data is healthy: 12 items, and the database matches its saved copy.'),
  ).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /Rebuild|Rewrite/ })).not.toBeInTheDocument()
})

it('asks before rebuilding a damaged database, then reports the result', async () => {
  resetTokenCache()
  const posts = serve({ ...healthy, database: 'damaged', in_sync: null, action: 'rebuild_database' })
  const onRepaired = vi.fn()
  const user = userEvent.setup()
  render(<LibraryDataCheck onRepaired={onRepaired} />)
  await user.click(screen.getByRole('button', { name: 'Check library data' }))
  expect(await screen.findByText(/The library database is damaged/)).toHaveTextContent('12 items')
  await user.click(screen.getByRole('button', { name: 'Rebuild the database' }))
  expect(posts).toEqual([])
  await user.click(screen.getByRole('button', { name: 'Cancel' }))
  await user.click(screen.getByRole('button', { name: 'Rebuild the database' }))
  await user.click(screen.getByRole('button', { name: 'Rebuild now' }))
  expect(await screen.findByText(/Library data is healthy/)).toBeInTheDocument()
  expect(posts).toEqual(['rebuild_database'])
  expect(onRepaired).toHaveBeenCalledOnce()
})

it('rewrites an outdated copy in one click', async () => {
  resetTokenCache()
  const posts = serve({ ...healthy, in_sync: false, action: 'rewrite_mirror' })
  const user = userEvent.setup()
  render(<LibraryDataCheck />)
  await user.click(screen.getByRole('button', { name: 'Check library data' }))
  await user.click(await screen.findByRole('button', { name: 'Rewrite the saved copy' }))
  expect(await screen.findByText(/Library data is healthy/)).toBeInTheDocument()
  expect(posts).toEqual(['rewrite_mirror'])
})

it('changes nothing when both copies are damaged', async () => {
  resetTokenCache()
  serve({ ...healthy, database: 'damaged', mirror: 'damaged', in_sync: null, action: '' })
  render(<LibraryDataCheck />)
  await userEvent.click(screen.getByRole('button', { name: 'Check library data' }))
  expect(await screen.findByText(/both damaged\. Nothing was changed/)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /Rebuild|Rewrite/ })).not.toBeInTheDocument()
})
