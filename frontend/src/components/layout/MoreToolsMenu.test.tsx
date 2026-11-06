import { useState } from 'react'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { MoreToolsMenu } from './MoreToolsMenu'

function Menu({ onSetup, onCloseBehavior }: { onSetup: () => void; onCloseBehavior?: () => void }) {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null)
  return (
    <>
      <button onClick={(event) => setAnchor(event.currentTarget)}>More tools</button>
      {anchor && (
        <MoreToolsMenu
          anchor={anchor}
          onClose={() => setAnchor(null)}
          onSetup={onSetup}
          onCloseBehavior={onCloseBehavior}
        />
      )}
    </>
  )
}

it('opens each independent action, dismisses the menu, and supports Escape', async () => {
  const setup = vi.fn(),
    close = vi.fn()
  const user = userEvent.setup()
  render(<Menu onSetup={setup} onCloseBehavior={close} />)
  const trigger = screen.getByRole('button', { name: 'More tools' })
  await user.click(trigger)
  const menu = screen.getByRole('dialog', { name: 'More tools' })
  expect(within(menu).getByRole('button', { name: 'Getting started' })).toHaveFocus()
  await user.keyboard('{ArrowDown}{Enter}')
  expect(close).toHaveBeenCalledOnce()
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  await user.click(trigger)
  await user.click(screen.getByRole('button', { name: 'Getting started' }))
  expect(setup).toHaveBeenCalledOnce()
  await user.click(trigger)
  await user.keyboard('{Escape}')
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(trigger).toHaveFocus()
})

it('omits desktop-only close behavior in browser mode', async () => {
  render(<Menu onSetup={vi.fn()} />)
  await userEvent.click(screen.getByRole('button', { name: 'More tools' }))
  expect(screen.queryByRole('button', { name: 'Close behavior' })).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Getting started' })).toBeInTheDocument()
})
