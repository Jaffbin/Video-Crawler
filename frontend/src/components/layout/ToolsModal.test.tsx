import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { ToolsModal } from './ToolsModal'

it('keeps independent guide, language and close settings out of Settings and help', async () => {
  const doctor = vi.fn()
  const close = vi.fn()
  const user = userEvent.setup()
  render(
    <ToolsModal
      open
      onClose={close}
      onDoctor={doctor}
      onUpdate={vi.fn()}
      onOpenFolder={vi.fn()}
      environmentAttention
      updateAttention={false}
    />,
  )
  expect(screen.queryByRole('combobox', { name: 'Language' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Getting started' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Close behavior' })).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Diagnostics Needs attention' }))
  expect(doctor).toHaveBeenCalledOnce()
  await user.keyboard('{Escape}')
  expect(close).toHaveBeenCalledOnce()
})
