import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { CloseBehavior } from './CloseBehavior'

afterEach(() => {
  delete window.pywebview
  vi.useRealTimers()
})

function bridge(trayReady = true) {
  const api = {
    close_settings: vi.fn().mockResolvedValue({ behavior: 'ask', tray_ready: trayReady }),
    close_action: vi.fn().mockResolvedValue(undefined),
    set_close_behavior: vi.fn().mockResolvedValue(undefined),
  }
  window.pywebview = { api }
  return api
}

it('asks before closing, remembers only background, and can cancel', async () => {
  const api = bridge()
  const user = userEvent.setup()
  render(<CloseBehavior settingsOpen={false} onCloseSettings={vi.fn()} />)
  const closeRequest = new Event('grab-close-request', { cancelable: true })
  act(() => window.dispatchEvent(closeRequest))
  expect(closeRequest.defaultPrevented).toBe(true)
  await user.click(screen.getByRole('button', { name: 'Cancel' }))
  expect(api.close_action).toHaveBeenCalledWith('cancel', false)
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  act(() => window.dispatchEvent(new Event('grab-close-request')))
  await user.click(screen.getByRole('checkbox', { name: 'Always run in background' }))
  await user.click(screen.getByRole('button', { name: 'Run in background' }))
  expect(api.close_action).toHaveBeenLastCalledWith('background', true)
  act(() => window.dispatchEvent(new Event('grab-close-request')))
  expect(screen.getByRole('checkbox')).not.toBeChecked()
  await user.click(screen.getByRole('checkbox'))
  await user.click(screen.getByRole('button', { name: 'Exit app' }))
  expect(api.close_action).toHaveBeenLastCalledWith('exit', false)
})

it('can reset the saved preference and reports a failed save', async () => {
  const api = bridge()
  api.close_settings.mockResolvedValue({ behavior: 'background', tray_ready: true })
  const close = vi.fn()
  const user = userEvent.setup()
  render(<CloseBehavior settingsOpen onCloseSettings={close} />)
  await waitFor(() => expect(screen.getByRole('combobox')).toHaveValue('background'))
  await user.selectOptions(screen.getByRole('combobox'), 'ask')
  api.set_close_behavior.mockRejectedValueOnce(new Error('disk full'))
  await user.click(screen.getByRole('button', { name: 'Save' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Could not change close behavior.')
  expect(close).not.toHaveBeenCalled()
  await user.click(screen.getByRole('button', { name: 'Save' }))
  expect(api.set_close_behavior).toHaveBeenLastCalledWith('ask')
  expect(close).toHaveBeenCalledOnce()
})

it('offers direct exit and explains that unfinished tasks still require confirmation', async () => {
  const api = bridge()
  const user = userEvent.setup()
  render(<CloseBehavior settingsOpen onCloseSettings={vi.fn()} />)
  await user.selectOptions(screen.getByRole('combobox'), 'exit')
  expect(
    screen.getByText('Unfinished downloads still require confirmation, including paused waiting tasks.'),
  ).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Save' }))
  expect(api.set_close_behavior).toHaveBeenCalledWith('exit')
})

it('shows the current unfinished count and updates it as tasks finish', async () => {
  const api = bridge()
  api.close_settings.mockResolvedValue({ behavior: 'ask', tray_ready: true, pending_downloads: 3 })
  const { rerender } = render(
    <CloseBehavior pendingDownloads={2} settingsOpen={false} onCloseSettings={vi.fn()} />,
  )
  act(() => window.dispatchEvent(new Event('grab-close-request')))
  expect(await screen.findByText('Unfinished downloads: 3')).toBeInTheDocument()
  rerender(<CloseBehavior pendingDownloads={1} settingsOpen={false} onCloseSettings={vi.fn()} />)
  expect(screen.getByRole('status')).toHaveTextContent('Unfinished downloads: 1')
  rerender(<CloseBehavior pendingDownloads={0} settingsOpen={false} onCloseSettings={vi.fn()} />)
  expect(screen.getByRole('status')).toHaveTextContent('No unfinished downloads.')
})

it('refreshes the native count while open and stops polling after unmount', async () => {
  vi.useFakeTimers()
  const api = bridge()
  api.close_settings.mockResolvedValue({ behavior: 'ask', tray_ready: true, pending_downloads: 3 })
  const { unmount } = render(<CloseBehavior settingsOpen={false} onCloseSettings={vi.fn()} />)
  await act(async () => {
    window.dispatchEvent(new Event('grab-close-request'))
  })
  expect(screen.getByRole('status')).toHaveTextContent('Unfinished downloads: 3')
  api.close_settings.mockResolvedValue({ behavior: 'ask', tray_ready: true, pending_downloads: 1 })
  await act(() => vi.advanceTimersByTimeAsync(1000))
  expect(screen.getByRole('status')).toHaveTextContent('Unfinished downloads: 1')
  unmount()
  const calls = api.close_settings.mock.calls.length
  await act(() => vi.advanceTimersByTimeAsync(2000))
  expect(api.close_settings).toHaveBeenCalledTimes(calls)
})

it('keeps the prompt open when background fails and disables background without a tray', async () => {
  const api = bridge()
  const user = userEvent.setup()
  const { unmount } = render(<CloseBehavior settingsOpen={false} onCloseSettings={vi.fn()} />)
  act(() => window.dispatchEvent(new Event('grab-close-request')))
  await waitFor(() => expect(screen.getByRole('button', { name: 'Run in background' })).toBeEnabled())
  api.close_action.mockRejectedValueOnce(new Error('tray failed'))
  await user.click(screen.getByRole('button', { name: 'Run in background' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('tray failed')
  expect(screen.getByRole('dialog')).toBeInTheDocument()
  unmount()
  bridge(false)
  render(<CloseBehavior settingsOpen={false} onCloseSettings={vi.fn()} />)
  act(() => window.dispatchEvent(new Event('grab-close-request')))
  expect(screen.getByRole('button', { name: 'Run in background' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Exit app' })).toBeEnabled()
})
