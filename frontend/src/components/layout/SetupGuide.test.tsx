import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { SetupGuide } from './SetupGuide'

it('shows component status and opens diagnostics on request', async () => {
  const onDiagnostics = vi.fn()
  render(
    <SetupGuide
      open
      doctor={{
        checks: [
          { id: 'ffmpeg', label: 'ffmpeg', status: 'error', detail: 'Not installed' },
          { id: 'ytdlp', label: 'yt-dlp', status: 'ok', detail: 'Ready' },
        ],
        report: '',
        net: false,
      }}
      onClose={() => {}}
      onDiagnostics={onDiagnostics}
      onStart={() => {}}
    />,
  )
  expect(screen.getByText('ffmpeg media processing')).toBeInTheDocument()
  expect(screen.getByText('yt-dlp download engine')).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Open Diagnostics' }))
  expect(onDiagnostics).toHaveBeenCalledOnce()
})
