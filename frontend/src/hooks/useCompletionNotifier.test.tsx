import { renderHook } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { useCompletionNotifier } from './useCompletionNotifier'
import type { Job } from '../types/api'
import { notifyDesktop } from '../api/client'

vi.mock('../api/client', () => ({ notifyDesktop: vi.fn(async () => ({ ok: true })) }))

const job = (status: Job['status']) =>
  ({ id: 'one', status, title: 'Example', url: 'https://example.com' }) as Job

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  vi.clearAllMocks()
})

it('keeps in-app announcements but leaves native Windows delivery to Python', () => {
  const announce = vi.fn()
  const Notification = vi.fn()
  Object.assign(Notification, { permission: 'granted' })
  vi.stubGlobal('Notification', Notification)
  vi.spyOn(document, 'hasFocus').mockReturnValue(false)
  const { rerender } = renderHook(
    ({ jobs }) =>
      useCompletionNotifier(jobs, {
        serverNotifies: true,
        nativeManaged: true,
        onAnnounce: announce,
      }),
    { initialProps: { jobs: [job('running')] } },
  )
  rerender({ jobs: [job('done')] })
  rerender({ jobs: [job('done')] })
  expect(announce).toHaveBeenCalledExactlyOnceWith('Download complete: Example', false)
  expect(notifyDesktop).not.toHaveBeenCalled()
  expect(Notification).not.toHaveBeenCalled()
})

it('preserves native notification requests for other desktop platforms', () => {
  vi.spyOn(document, 'hasFocus').mockReturnValue(false)
  const { rerender } = renderHook(
    ({ jobs }) =>
      useCompletionNotifier(jobs, {
        serverNotifies: true,
        onAnnounce: vi.fn(),
      }),
    { initialProps: { jobs: [job('running')] } },
  )
  rerender({ jobs: [job('done')] })
  expect(notifyDesktop).toHaveBeenCalledExactlyOnceWith('Video Grabber', 'Download complete: Example')
})
