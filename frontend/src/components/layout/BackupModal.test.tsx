import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { BackupModal } from './BackupModal'
import { resetTokenCache } from '../../api/client'

beforeEach(() => {
  localStorage.clear()
  resetTokenCache()
})
afterEach(() => vi.unstubAllGlobals())

it('previews an imported file without restoring until the user chooses to apply it', async () => {
  const calls: string[] = [],
    restored = vi.fn(),
    user = userEvent.setup()
  const review = {
    counts: { files: 1, collections: 2, presets: 1, settings: 3, conflicts: 4 },
    skipped: [{ path: 'missing.mp4', reason: 'missing' }],
    review_token: 'reviewed',
    browser: { theme: 'dark' },
  }
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url, init) => {
      calls.push(String(url))
      expect(JSON.parse(init.body).current).toBeDefined()
      return new Response(JSON.stringify(review))
    }),
  )
  render(<BackupModal open onClose={vi.fn()} onRestored={restored} />)
  const file = new File(['{}'], 'backup.json', { type: 'application/json' })
  Object.defineProperty(file, 'text', { value: async () => '{}' })
  await user.upload(screen.getByLabelText('Backup JSON file'), file)
  expect(await screen.findByRole('region', { name: 'Restore preview' })).toHaveTextContent('missing.mp4')
  expect(calls).toEqual(['/api/backup/preview'])
  await user.click(screen.getByRole('button', { name: 'Restore missing data and merge' }))
  await waitFor(() => expect(restored).toHaveBeenCalledOnce())
  expect(calls).toEqual(['/api/backup/preview', '/api/backup/restore'])
  expect(localStorage.getItem('grab-theme')).toBe('dark')
})

it('rejects invalid JSON and does not leave a stale restore button available', async () => {
  const fetch = vi.fn(),
    user = userEvent.setup()
  vi.stubGlobal('fetch', fetch)
  render(<BackupModal open onClose={vi.fn()} onRestored={vi.fn()} />)
  const file = new File(['bad'], 'broken.json', { type: 'application/json' })
  Object.defineProperty(file, 'text', { value: async () => 'bad' })
  await user.upload(screen.getByLabelText('Backup JSON file'), file)
  expect(await screen.findByRole('alert')).toHaveTextContent('valid JSON')
  expect(fetch).not.toHaveBeenCalled()
  expect(screen.queryByRole('button', { name: 'Restore missing data and merge' })).not.toBeInTheDocument()
})
