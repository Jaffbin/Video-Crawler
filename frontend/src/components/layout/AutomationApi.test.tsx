import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { resetTokenCache } from '../../api/client'
import { AutomationApi } from './AutomationApi'

afterEach(() => vi.unstubAllGlobals())

const BASE = 'http://127.0.0.1:8765/api/v1'

function serve() {
  let enabled = false
  let hasToken = false
  const posts: string[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (_url: string, init?: RequestInit) => {
      let token: string | undefined
      if (init?.method === 'POST') {
        const { action } = JSON.parse(String(init.body))
        posts.push(action)
        if (action === 'new_token' || (action === 'enable' && !hasToken)) {
          token = `vg_token_${posts.length}`
          hasToken = true
        }
        if (action !== 'new_token') enabled = action === 'enable'
      }
      return new Response(JSON.stringify({ enabled, has_token: hasToken, base_url: BASE, token }))
    }),
  )
  return posts
}

it('turns the API on and shows the new token once with a copy button', async () => {
  resetTokenCache()
  serve()
  const user = userEvent.setup()
  const writeText = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue()
  render(<AutomationApi />)
  expect(await screen.findByText('Off. Other programs cannot add downloads.')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /Create a new token/ })).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Turn on the API' }))
  expect(await screen.findByText(`On. Address: ${BASE}`)).toBeInTheDocument()
  expect(screen.getByText('vg_token_1')).toBeInTheDocument()
  expect(screen.getByText('Copy this token now. It will not be shown again.')).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Copy token' }))
  expect(writeText).toHaveBeenCalledWith('vg_token_1')
  expect(screen.getByRole('button', { name: 'Copy token' })).toHaveTextContent('Copied')
  await user.click(screen.getByRole('button', { name: 'Turn off the API' }))
  await waitFor(() => expect(screen.queryByText('vg_token_1')).not.toBeInTheDocument())
})

it('asks before replacing a token that programs may be using', async () => {
  resetTokenCache()
  const posts = serve()
  const user = userEvent.setup()
  render(<AutomationApi />)
  await user.click(await screen.findByRole('button', { name: 'Turn on the API' }))
  await user.click(await screen.findByRole('button', { name: /Create a new token/ }))
  expect(screen.getByText(/will stop working until you give them the new one/)).toBeInTheDocument()
  expect(posts).toEqual(['enable'])
  await user.click(screen.getByRole('button', { name: 'Replace token' }))
  expect(await screen.findByText('vg_token_2')).toBeInTheDocument()
  expect(posts).toEqual(['enable', 'new_token'])
})

it('stays hidden when this client may not manage the API', async () => {
  resetTokenCache()
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(JSON.stringify({ error: 'no' }), { status: 403 })),
  )
  render(<AutomationApi />)
  await new Promise((resolve) => setTimeout(resolve, 20))
  expect(screen.queryByText('Automation API')).not.toBeInTheDocument()
})
