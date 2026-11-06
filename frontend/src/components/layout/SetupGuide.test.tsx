import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { SetupGuide } from './SetupGuide'
import type { DoctorResult } from '../../types/api'

afterEach(() => vi.unstubAllGlobals())
const missing: DoctorResult = {
  checks: [{ id: 'ffmpeg', label: 'ffmpeg', status: 'error', detail: 'Not installed' }],
  report: '',
  net: false,
}

it('shows preparation status and opens diagnostics on request', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(JSON.stringify({ can_install: true, ready: false }))),
  )
  const onDiagnostics = vi.fn()
  render(
    <SetupGuide open doctor={missing} onClose={() => {}} onDiagnostics={onDiagnostics} onStart={() => {}} />,
  )
  expect(screen.getByText('A few download features need preparation.')).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Technical details' }))
  expect(onDiagnostics).toHaveBeenCalledOnce()
})

it('shows readiness without exposing tool names or requiring manual checks', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(JSON.stringify({ can_install: true, ready: true }))),
  )
  render(
    <SetupGuide
      open
      doctor={{ checks: [], report: '', net: false }}
      onClose={() => {}}
      onDiagnostics={() => {}}
      onStart={() => {}}
    />,
  )
  expect(screen.getByText('Ready to download')).toBeInTheDocument()
  expect(screen.queryByText('Component check')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Start downloading' })).toBeEnabled()
})

it('prepares only after the user clicks and keeps failed preparation actionable', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(JSON.stringify({ can_install: true, ready: false }))),
  )
  const prepare = vi.fn(async () => {
    throw new Error('Preparation failed. Check your connection or open technical details.')
  })
  const user = userEvent.setup()
  render(
    <SetupGuide
      open
      doctor={missing}
      onClose={() => {}}
      onDiagnostics={() => {}}
      onStart={() => {}}
      onPrepare={prepare}
    />,
  )
  expect(prepare).not.toHaveBeenCalled()
  await user.click(await screen.findByRole('button', { name: 'Prepare download features' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Preparation failed')
  expect(screen.getByRole('button', { name: 'Try preparation again' })).toBeEnabled()
})

it('explains Windows blocking without suggesting an automatic bypass', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(JSON.stringify({ can_install: false, blocked: true }))),
  )
  const doctor = { ...missing, checks: [{ ...missing.checks[0], detail: 'WinError 4551' }] }
  render(
    <SetupGuide
      open
      doctor={doctor}
      onClose={() => {}}
      onDiagnostics={() => {}}
      onStart={() => {}}
      onPrepare={vi.fn()}
    />,
  )
  expect(screen.getByText('Windows blocked a download feature.')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Prepare download features' })).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Technical details' })).toBeEnabled()
  await waitFor(() => expect(screen.getByRole('button', { name: 'Download images for now' })).toBeEnabled())
})

it.each([
  ['media', 'Preparing video and audio tools…'],
  ['sites', 'Preparing website support…'],
  ['verifying', 'Making sure everything works…'],
])('shows the current preparation stage (%s) and keeps actions disabled', async (stage, label) => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(JSON.stringify({ can_install: true, ready: false }))),
  )
  const close = vi.fn()
  render(
    <SetupGuide
      open
      doctor={missing}
      preparing
      preparationStage={stage}
      onClose={close}
      onDiagnostics={vi.fn()}
      onStart={vi.fn()}
      onPrepare={vi.fn()}
    />,
  )
  expect(screen.getByRole('list', { name: 'Getting started steps' })).toBeInTheDocument()
  expect(screen.getByText(label)).toBeInTheDocument()
  expect(await screen.findByRole('button', { name: 'Preparing…' })).toBeDisabled()
  await userEvent.click(screen.getByRole('button', { name: 'Close' }))
  expect(close).not.toHaveBeenCalled()
})

it('lets users recheck a failed readiness request before installing anything', async () => {
  const fetch = vi
    .fn()
    .mockRejectedValueOnce(new Error('offline'))
    .mockResolvedValue(new Response(JSON.stringify({ can_install: true, ready: false })))
  vi.stubGlobal('fetch', fetch)
  const prepare = vi.fn()
  render(
    <SetupGuide
      open
      doctor={missing}
      onClose={vi.fn()}
      onDiagnostics={vi.fn()}
      onStart={vi.fn()}
      onPrepare={prepare}
    />,
  )
  expect(await screen.findByRole('button', { name: 'Check again' })).toBeEnabled()
  expect(screen.queryByRole('button', { name: 'Prepare download features' })).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Check again' }))
  expect(await screen.findByRole('button', { name: 'Prepare download features' })).toBeEnabled()
  expect(prepare).not.toHaveBeenCalled()
})
