import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { resetTokenCache } from '../../api/client'
import { DEFAULT_OPTIONS } from '../../lib/options'
import { AddSubscriptionForm } from './AddSubscriptionForm'

let requests: { url: string; body: any }[]

beforeEach(() => {
  document.head.insertAdjacentHTML('beforeend', '<meta name="grab-token" content="t">')
  resetTokenCache()
  requests = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      requests.push({ url: String(input), body: init?.body ? JSON.parse(String(init.body)) : undefined })
      return new Response('{}', { status: 200, headers: { 'content-type': 'application/json' } })
    }),
  )
})

afterEach(() => {
  vi.unstubAllGlobals()
  document.querySelector('meta[name="grab-token"]')?.remove()
})

describe('AddSubscriptionForm', () => {
  it('says up front which settings a new subscription will use', () => {
    render(
      <AddSubscriptionForm
        options={{ ...DEFAULT_OPTIONS, mode: 'mp3', abr: 128 }}
        onAdded={() => {}}
        onToast={() => {}}
      />,
    )
    expect(screen.getByText('MP3 · 128 kbps')).toBeInTheDocument()
  })

  it('follows the settings when they change', () => {
    const { rerender } = render(
      <AddSubscriptionForm options={DEFAULT_OPTIONS} onAdded={() => {}} onToast={() => {}} />,
    )
    expect(screen.getByText('MP4 · best quality')).toBeInTheDocument()
    rerender(
      <AddSubscriptionForm
        options={{ ...DEFAULT_OPTIONS, quality: '720' }}
        onAdded={() => {}}
        onToast={() => {}}
      />,
    )
    expect(screen.getByText('MP4 · up to 720p')).toBeInTheDocument()
  })

  it('submits with exactly the settings it displayed, and repeats them in the confirmation', async () => {
    const onToast = vi.fn()
    render(
      <AddSubscriptionForm
        options={{ ...DEFAULT_OPTIONS, quality: '720' }}
        onAdded={() => {}}
        onToast={onToast}
      />,
    )
    await userEvent.type(screen.getByPlaceholderText(/channel or playlist link/i), 'https://example.com/c')
    await userEvent.click(screen.getByRole('button', { name: /add/i }))
    await waitFor(() => expect(requests).toHaveLength(1))
    expect(requests[0].body).toMatchObject({
      url: 'https://example.com/c',
      backfill: 'none',
      options: { quality: '720' },
    })
    await waitFor(() => expect(onToast).toHaveBeenCalledWith(expect.stringContaining('MP4 · up to 720p')))
  })

  it('offers a back-fill count only when back-filling', async () => {
    render(<AddSubscriptionForm options={DEFAULT_OPTIONS} onAdded={() => {}} onToast={() => {}} />)
    expect(screen.queryByLabelText(/how many/i)).toBeNull()
    await userEvent.click(screen.getByRole('radio', { name: /recent batch/i }))
    expect(screen.getByLabelText(/how many/i)).toBeInTheDocument()
  })

  it('submits per-subscription keyword and media filters', async () => {
    render(<AddSubscriptionForm options={DEFAULT_OPTIONS} onAdded={() => {}} onToast={() => {}} />)
    await userEvent.type(screen.getByPlaceholderText(/channel or playlist link/i), 'https://example.com/c')
    await userEvent.type(screen.getByLabelText(/title must contain/i), 'cats, dogs')
    await userEvent.type(screen.getByLabelText(/minimum duration/i), '2')
    await userEvent.click(screen.getByLabelText(/exclude live/i))
    await userEvent.click(screen.getByRole('button', { name: /^add$/i }))
    await waitFor(() => expect(requests).toHaveLength(1))
    expect(requests[0].body.filters).toMatchObject({
      include_keywords: ['cats', 'dogs'],
      exclude_live: true,
      min_duration: 120,
    })
  })

  it('does not submit twice while the first check is still running', async () => {
    let finishRequest!: (response: Response) => void
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        requests.push({ url: String(input), body: init?.body ? JSON.parse(String(init.body)) : undefined })
        return new Promise<Response>((resolve) => {
          finishRequest = resolve
        })
      }),
    )
    render(<AddSubscriptionForm options={DEFAULT_OPTIONS} onAdded={() => {}} onToast={() => {}} />)
    const input = screen.getByPlaceholderText(/channel or playlist link/i)
    await userEvent.type(input, 'https://example.com/c{enter}{enter}')
    expect(requests).toHaveLength(1)
    expect(input).toBeDisabled()
    finishRequest(new Response('{}', { status: 200, headers: { 'content-type': 'application/json' } }))
    await waitFor(() => expect(input).not.toBeDisabled())
  })
})
