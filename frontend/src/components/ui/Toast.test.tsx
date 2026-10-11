import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { Toasts } from './Toast'
import { useToasts } from '../../hooks/useToasts'

afterEach(() => vi.useRealTimers())

it('keeps undo available after ordinary toasts expire and removes it after success', async () => {
  vi.useFakeTimers()
  const undo = vi.fn(async () => {})
  function Harness() {
    const { toasts, push, remove } = useToasts(100)
    return (
      <>
        <button
          onClick={() => {
            push('Deleted', false, { label: 'Undo', onClick: undo })
            push('Ordinary')
          }}
        >
          Delete
        </button>
        <Toasts items={toasts} onRemove={remove} />
      </>
    )
  }
  render(<Harness />)
  fireEvent.click(screen.getByRole('button', { name: 'Delete' }))
  act(() => vi.advanceTimersByTime(1000))
  expect(screen.queryByText('Ordinary')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Undo' })).toBeEnabled()
  expect(undo).not.toHaveBeenCalled()
  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name: 'Undo' }))
  })
  expect(undo).toHaveBeenCalledOnce()
  expect(screen.queryByText('Deleted')).not.toBeInTheDocument()
})

it('keeps the action after a failed undo and prevents duplicate clicks while restoring', async () => {
  let finish!: () => void
  const undo = vi
    .fn()
    .mockRejectedValueOnce(new Error('File already exists'))
    .mockImplementationOnce(
      () =>
        new Promise<void>((resolve) => {
          finish = resolve
        }),
    )
  const remove = vi.fn()
  render(
    <Toasts
      items={[{ id: 1, message: 'Deleted', error: false, action: { label: 'Undo', onClick: undo } }]}
      onRemove={remove}
    />,
  )
  fireEvent.click(screen.getByRole('button', { name: 'Undo' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('File already exists')
  expect(remove).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Undo' }))
  expect(screen.getByRole('button', { name: 'Restoring…' })).toBeDisabled()
  await act(async () => finish())
  await waitFor(() => expect(remove).toHaveBeenCalledWith(1))
})
