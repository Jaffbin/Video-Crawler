import { render, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { Sidebar } from './Sidebar'

it('orders independent tools with Close behavior last and opens the guide directly', async () => {
  const setup = vi.fn()
  const close = vi.fn()
  const { container } = render(
    <Sidebar
      view="library"
      version="1"
      online
      activeJobs={0}
      failedJobs={0}
      fileCount={0}
      updateAttention={false}
      environmentAttention={false}
      onNavigate={vi.fn()}
      onTools={vi.fn()}
      onSetup={setup}
      onOpenFolder={vi.fn()}
      onLanguage={vi.fn()}
      onCloseBehavior={close}
    />,
  )
  const tools = within(container.querySelector('.sidebar-tools') as HTMLElement)
  expect(tools.getAllByRole('button').map((button) => button.textContent)).toEqual([
    'Getting started',
    'Open folder',
    'Language',
    'Settings and help',
    'Close behavior',
  ])
  await userEvent.click(tools.getByRole('button', { name: 'Getting started' }))
  expect(setup).toHaveBeenCalledOnce()
  await userEvent.click(tools.getByRole('button', { name: 'Close behavior' }))
  expect(close).toHaveBeenCalledOnce()
})
