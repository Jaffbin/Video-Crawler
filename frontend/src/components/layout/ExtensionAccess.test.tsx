import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { resetTokenCache } from '../../api/client'
import { ExtensionAccess } from './ExtensionAccess'

afterEach(() => vi.unstubAllGlobals())

it('shows the current setting, saves a change and explains it behind a question mark', async () => {
  resetTokenCache()
  const requests: Array<{ url: string; body?: unknown }> = []
  let enabled = false
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      requests.push({ url, body: init?.body ? JSON.parse(String(init.body)) : undefined })
      if (init?.method === 'POST') enabled = JSON.parse(String(init.body)).extension
      return new Response(JSON.stringify({ extension: enabled }))
    }),
  )
  const user = userEvent.setup()
  render(<ExtensionAccess />)
  const box = await screen.findByRole('checkbox', { name: 'Allow the Chrome extension to connect' })
  expect(box).not.toBeChecked()
  expect(screen.queryByRole('note')).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: /what is this\?/i }))
  expect(screen.getByRole('note')).toHaveTextContent(/Leave this off if you do not use it/)
  await user.click(box)
  await waitFor(() => expect(box).toBeChecked())
  expect(requests.at(-1)).toEqual({ url: '/api/access', body: { extension: true } })
})

it('stays hidden when the app does not answer', async () => {
  resetTokenCache()
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => Promise.reject(new Error('offline'))),
  )
  render(<ExtensionAccess />)
  await new Promise((resolve) => setTimeout(resolve, 20))
  expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
})
