import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { Banners } from './Banners'

const base = {
  online: true,
  ffmpeg: true,
  showYoutubeIssues: false,
  onOpenDiagnostics: vi.fn(),
  onDismissYoutubeIssues: vi.fn(),
}

it('offers a one-click update for a newer yt-dlp and lets it be dismissed', async () => {
  const update = vi.fn()
  const dismiss = vi.fn()
  const user = userEvent.setup()
  render(<Banners {...base} updateVersion="2026.11.01" onUpdate={update} onDismissUpdate={dismiss} />)
  expect(screen.getByText(/yt-dlp 2026\.11\.01 is available/)).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Update now' }))
  await user.click(screen.getByRole('button', { name: 'Dismiss' }))
  expect(update).toHaveBeenCalledOnce()
  expect(dismiss).toHaveBeenCalledOnce()
})

it('asks for a restart after an update without offering to dismiss it', () => {
  render(<Banners {...base} updateNeedsRestart onUpdate={vi.fn()} onDismissUpdate={vi.fn()} />)
  expect(screen.getByText(/Restart the app to use it/)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Open updates' })).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Dismiss' })).not.toBeInTheDocument()
})

it('shows no update banner while offline or when nothing is waiting', () => {
  const { rerender } = render(<Banners {...base} onUpdate={vi.fn()} />)
  expect(screen.queryByText(/yt-dlp/)).not.toBeInTheDocument()
  rerender(<Banners {...base} online={false} updateVersion="2026.11.01" onUpdate={vi.fn()} />)
  expect(screen.queryByText(/is available/)).not.toBeInTheDocument()
})

it('names what YouTube is missing instead of a generic message', () => {
  const { rerender } = render(<Banners {...base} showYoutubeIssues youtubeIssueIds={['js_runtime', 'ejs']} />)
  expect(screen.getByText(/need the Deno helper/)).toBeInTheDocument()
  rerender(<Banners {...base} showYoutubeIssues youtubeIssueIds={['ejs']} />)
  expect(screen.getByText(/one more yt-dlp component/)).toBeInTheDocument()
  rerender(<Banners {...base} showYoutubeIssues youtubeIssueIds={[]} />)
  expect(screen.getByText(/Some site download features need preparation/)).toBeInTheDocument()
})
