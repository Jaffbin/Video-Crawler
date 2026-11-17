import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { resetTokenCache, type RemoteAccessStatus } from '../../api/client'
import { RemoteAccess } from './RemoteAccess'

afterEach(() => vi.unstubAllGlobals())

function serve(initial: Partial<RemoteAccessStatus> = {}) {
  let state: RemoteAccessStatus = {
    enabled: false,
    running: false,
    error: '',
    bind: 'loopback',
    port: 8766,
    trusted_hosts: [],
    addresses: ['192.168.1.20'],
    urls: [],
    devices: [],
    pairing: null,
    ...initial,
  }
  const posts: Array<Record<string, unknown>> = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (_url: string, init?: RequestInit) => {
      if (init?.method === 'POST') {
        const body = JSON.parse(String(init.body))
        posts.push(body)
        if (body.action === 'enable') state = { ...state, enabled: true, running: true }
        if (body.action === 'disable') state = { ...state, enabled: false, running: false, pairing: null }
        if (body.action === 'new_code') state = { ...state, pairing: { code: 'ABCD-EFGH', expires: 0 } }
        if (body.action === 'cancel_code') state = { ...state, pairing: null }
        if (body.action === 'revoke')
          state = { ...state, devices: state.devices.filter((d) => d.id !== body.device) }
        if (body.action === 'configure') {
          state = {
            ...state,
            bind: body.bind,
            port: body.port,
            trusted_hosts: body.trusted_hosts,
            urls: [
              ...(body.bind === 'loopback' ? [] : [`http://${body.bind}:${body.port}/`]),
              ...body.trusted_hosts.map((h: string) => `https://${h}/`),
            ],
          }
        }
      }
      return new Response(JSON.stringify(state))
    }),
  )
  return posts
}

it('turns remote access on, pairs a phone with a one-time code and cancels it', async () => {
  resetTokenCache()
  const posts = serve()
  const user = userEvent.setup()
  render(<RemoteAccess />)
  expect(await screen.findByText('Off. Phones cannot connect.')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /Pair a phone/ })).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Turn on remote access' }))
  expect(await screen.findByText(/On, for this computer only \(port 8766\)/)).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: /Pair a phone/ }))
  expect(await screen.findByText('ABCD-EFGH')).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Cancel' }))
  await waitFor(() => expect(screen.queryByText('ABCD-EFGH')).not.toBeInTheDocument())
  expect(posts.map((p) => p.action)).toEqual(['enable', 'new_code', 'cancel_code'])
})

it('warns about plain HTTP on the home network and saves the connection settings', async () => {
  resetTokenCache()
  const posts = serve({ enabled: true, running: true })
  const user = userEvent.setup()
  render(<RemoteAccess />)
  const where = await screen.findByLabelText('Where phones connect')
  expect(screen.queryByText(/not encrypted/)).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled()
  await user.selectOptions(where, '192.168.1.20')
  await user.type(screen.getByLabelText('Host names that may connect (optional)'), 'box.tailnet.ts.net')
  await user.click(screen.getByRole('button', { name: 'Save' }))
  expect(await screen.findByText('Saved.')).toBeInTheDocument()
  expect(posts.at(-1)).toEqual({
    action: 'configure',
    bind: '192.168.1.20',
    port: 8766,
    trusted_hosts: ['box.tailnet.ts.net'],
  })
  expect(
    screen.getByText(/http:\/\/192\.168\.1\.20:8766\/, https:\/\/box\.tailnet\.ts\.net\//),
  ).toBeInTheDocument()
  expect(screen.getByText(/not encrypted/)).toBeInTheDocument()
})

it('lists paired phones and removes one', async () => {
  resetTokenCache()
  const posts = serve({
    enabled: true,
    running: true,
    devices: [{ id: 'aaaaaaaa', name: 'Pixel', created: 1, last_seen: 1 }],
  })
  const user = userEvent.setup()
  render(<RemoteAccess />)
  expect(await screen.findByText('Pixel')).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Remove Pixel' }))
  await waitFor(() => expect(screen.queryByText('Pixel')).not.toBeInTheDocument())
  expect(posts).toEqual([{ action: 'revoke', device: 'aaaaaaaa' }])
})

it('explains why the listener could not start', async () => {
  resetTokenCache()
  serve({ enabled: true, running: false, error: 'port_busy' })
  render(<RemoteAccess />)
  expect(
    await screen.findByText('Could not start: port 8766 is in use. Choose another port.'),
  ).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /Pair a phone/ })).not.toBeInTheDocument()
})

it('stays hidden when this client may not manage remote access', async () => {
  resetTokenCache()
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(JSON.stringify({ error: 'no' }), { status: 403 })),
  )
  const { container } = render(<RemoteAccess />)
  await new Promise((resolve) => setTimeout(resolve, 20))
  expect(container).toBeEmptyDOMElement()
})
