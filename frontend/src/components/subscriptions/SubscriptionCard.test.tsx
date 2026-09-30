import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { resetTokenCache } from '../../api/client'
import { DEFAULT_OPTIONS } from '../../lib/options'
import type { Subscription } from '../../types/api'
import { SubscriptionCard } from './SubscriptionCard'

const sub = (over: Partial<Subscription> = {}): Subscription => ({
  id: 'abcd1234',
  url: 'https://example.com/channel',
  title: 'My Channel',
  enabled: true,
  backfill: 'none',
  backfill_count: 5,
  filters: {
    include_keywords: [],
    exclude_keywords: [],
    exclude_live: false,
    exclude_shorts: false,
    min_duration: 0,
    max_duration: 0,
  },
  mode: 'mp4',
  options: { ...DEFAULT_OPTIONS, quality: '1080' },
  created: 1,
  last_checked: 0,
  last_error: '',
  total_queued: 0,
  total_filtered: 0,
  last_found: 0,
  last_queued: 0,
  last_filtered: 0,
  next_check: null,
  checking: false,
  ...over,
})

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

describe('SubscriptionCard', () => {
  it('shows what the subscription downloads', () => {
    render(
      <ul>
        <SubscriptionCard sub={sub()} onChanged={() => {}} onToast={() => {}} />
      </ul>,
    )
    expect(screen.getByText(/Downloads: MP4 · up to 1080p/)).toBeInTheDocument()
  })

  it('keeps Save disabled until something changes', async () => {
    render(
      <ul>
        <SubscriptionCard sub={sub()} onChanged={() => {}} onToast={() => {}} />
      </ul>,
    )
    await userEvent.click(screen.getByRole('button', { name: /edit format/i }))
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled()
    await userEvent.selectOptions(screen.getByLabelText(/maximum video quality/i), '720')
    expect(screen.getByRole('button', { name: 'Save' })).toBeEnabled()
  })

  it('saves the complete settings object with only the edited fields changed', async () => {
    const onToast = vi.fn()
    const onChanged = vi.fn()
    render(
      <ul>
        <SubscriptionCard
          sub={sub({
            options: { ...DEFAULT_OPTIONS, quality: '1080', subs: true, proxy: 'http://127.0.0.1:7890' },
          })}
          onChanged={onChanged}
          onToast={onToast}
        />
      </ul>,
    )
    await userEvent.click(screen.getByRole('button', { name: /edit format/i }))
    await userEvent.click(screen.getByRole('radio', { name: 'MP3 audio' }))
    await userEvent.selectOptions(screen.getByLabelText(/output bitrate/i), '320')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(requests.some((r) => r.url.endsWith('/update'))).toBe(true))
    const { url, body } = requests.find((r) => r.url.endsWith('/update'))!
    expect(url).toBe('/api/subscriptions/abcd1234/update')
    expect(body.options).toMatchObject({ mode: 'mp3', abr: 320, subs: true, proxy: 'http://127.0.0.1:7890' })
    await waitFor(() => expect(onChanged).toHaveBeenCalled())
    expect(onToast).toHaveBeenCalledWith(expect.stringContaining('MP3 · 320 kbps'))
    expect(screen.queryByRole('button', { name: 'Save' })).toBeNull()
  })

  it('does not throw away what is being edited when the list refreshes in the background', async () => {
    const { rerender } = render(
      <ul>
        <SubscriptionCard sub={sub()} onChanged={() => {}} onToast={() => {}} />
      </ul>,
    )
    await userEvent.click(screen.getByRole('button', { name: /edit format/i }))
    await userEvent.selectOptions(screen.getByLabelText(/maximum video quality/i), '480')
    rerender(
      <ul>
        <SubscriptionCard sub={sub({ last_checked: 999 })} onChanged={() => {}} onToast={() => {}} />
      </ul>,
    )
    expect((screen.getByLabelText(/maximum video quality/i) as HTMLSelectElement).value).toBe('480')
  })

  it('cancel closes the editor without saving', async () => {
    render(
      <ul>
        <SubscriptionCard sub={sub()} onChanged={() => {}} onToast={() => {}} />
      </ul>,
    )
    await userEvent.click(screen.getByRole('button', { name: /edit format/i }))
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(requests).toHaveLength(0)
    expect(screen.getByRole('button', { name: /edit format/i })).toBeInTheDocument()
  })

  it('previews draft filters without updating the subscription', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        requests.push({ url: String(input), body: init?.body ? JSON.parse(String(init.body)) : undefined })
        return new Response(
          JSON.stringify({
            title: 'Channel',
            total_candidates: 1,
            would_queue: 0,
            filtered: 1,
            items: [
              {
                id: 'a',
                title: 'Dog video',
                url: 'https://example.com/a',
                duration: 90,
                reason: 'include_keywords',
                eligible: true,
              },
            ],
          }),
          { status: 200, headers: { 'content-type': 'application/json' } },
        )
      }),
    )
    render(
      <ul>
        <SubscriptionCard sub={sub()} onChanged={() => {}} onToast={() => {}} />
      </ul>,
    )
    await userEvent.click(screen.getByRole('button', { name: /edit format/i }))
    await userEvent.type(screen.getByLabelText(/title must contain/i), 'cat')
    await userEvent.click(screen.getByRole('button', { name: /preview filters/i }))
    await waitFor(() => expect(screen.getByText('Dog video')).toBeInTheDocument())
    expect(screen.getByText(/Would queue: 0/)).toBeInTheDocument()
    expect(screen.getByText(/Filtered: 1/)).toBeInTheDocument()
    expect(requests).toHaveLength(1)
    expect(requests[0].url).toBe('/api/subscriptions/abcd1234/preview')
    expect(requests[0].body.filters.include_keywords).toEqual(['cat'])
  })
})
