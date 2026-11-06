import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { ImportFiles } from './ImportFiles'
import { importLibraryFile } from '../../api/client'

vi.mock('../../api/client', () => ({
  importLibraryFile: vi.fn(async () => ({ path: 'imports/clip.mp4', duplicate: false })),
}))
afterEach(() => vi.clearAllMocks())

it('imports only after selection and confirmation and retains failed files for retry', async () => {
  const toast = vi.fn(),
    refresh = vi.fn()
  const user = userEvent.setup()
  render(<ImportFiles onToast={toast} onRefresh={refresh} />)
  await user.click(screen.getByRole('button', { name: 'Import local files' }))
  expect(screen.getByText(/Your original files stay/)).toBeInTheDocument()
  const input = screen.getByLabelText('Local media files')
  await user.upload(input, [new File(['video'], 'clip.mp4'), new File(['audio'], 'sound.mp3')])
  expect(importLibraryFile).not.toHaveBeenCalled()
  vi.mocked(importLibraryFile)
    .mockResolvedValueOnce({ path: 'imports/clip.mp4', duplicate: true })
    .mockRejectedValueOnce(new Error('file conflict'))
  await user.click(screen.getByRole('button', { name: 'Import selected files' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('file conflict')
  expect(screen.getByText(/^1 selected/)).toBeInTheDocument()
  expect(toast).toHaveBeenCalledWith('Imported 0 files; skipped 1 duplicates; 1 remaining.', true)
  expect(refresh).toHaveBeenCalledOnce()
})

it('stops the upload and does not start remaining files', async () => {
  vi.mocked(importLibraryFile).mockImplementationOnce(
    (_file, signal) =>
      new Promise((_resolve, reject) =>
        signal.addEventListener('abort', () => reject(new DOMException('canceled', 'AbortError'))),
      ),
  )
  const user = userEvent.setup(),
    toast = vi.fn()
  render(<ImportFiles onToast={toast} onRefresh={vi.fn()} />)
  await user.click(screen.getByRole('button', { name: 'Import local files' }))
  await user.upload(screen.getByLabelText('Local media files'), [
    new File(['video'], 'clip.mp4'),
    new File(['audio'], 'sound.mp3'),
  ])
  await user.click(screen.getByRole('button', { name: 'Import selected files' }))
  await user.click(screen.getByRole('button', { name: 'Stop import' }))
  await waitFor(() => expect(screen.getByRole('button', { name: 'Import selected files' })).toBeEnabled())
  expect(importLibraryFile).toHaveBeenCalledOnce()
  expect(toast).toHaveBeenCalledWith('Import stopped. Completed files remain in Library.')
})
