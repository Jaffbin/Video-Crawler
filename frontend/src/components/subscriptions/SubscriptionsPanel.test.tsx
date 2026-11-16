import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { resetTokenCache } from '../../api/client'
import { DEFAULT_OPTIONS } from '../../lib/options'
import { SubscriptionsPanel } from './SubscriptionsPanel'

afterEach(() => vi.unstubAllGlobals())

it('saves how often subscriptions are checked', async () => {
  resetTokenCache()
  const posts: Array<{ url: string; body: unknown }> = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      posts.push({ url, body: JSON.parse(String(init?.body)) })
      return new Response(JSON.stringify({ interval_seconds: 21600 }))
    }),
  )
  const changed = vi.fn()
  const toast = vi.fn()
  const user = userEvent.setup()
  render(
    <SubscriptionsPanel
      options={DEFAULT_OPTIONS}
      subscriptions={[]}
      intervalSeconds={3600}
      onChanged={changed}
      onToast={toast}
    />,
  )
  const select = screen.getByLabelText('Check for new videos every')
  expect(select).toHaveValue('60')
  expect(screen.getAllByRole('option').map((option) => option.textContent)).toEqual([
    '30 min',
    '1 h',
    '2 h',
    '6 h',
    '12 h',
    '24 h',
  ])
  await user.selectOptions(select, '360')
  await waitFor(() => expect(changed).toHaveBeenCalledOnce())
  expect(posts).toEqual([{ url: '/api/subscriptions/settings', body: { interval_minutes: 360 } }])
  expect(toast).toHaveBeenCalledWith('Check frequency saved')
})

it('keeps a value set on the command line selectable', () => {
  render(
    <SubscriptionsPanel
      options={DEFAULT_OPTIONS}
      subscriptions={[]}
      intervalSeconds={300}
      onChanged={vi.fn()}
      onToast={vi.fn()}
    />,
  )
  expect(screen.getByLabelText('Check for new videos every')).toHaveValue('5')
})
