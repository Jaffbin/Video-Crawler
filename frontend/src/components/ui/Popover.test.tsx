import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { useState } from 'react'
import { Popover, placePopover } from './Popover'

afterEach(() => vi.restoreAllMocks())

function Example({ actions = false }: { actions?: boolean }) {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null)
  const [command, setCommand] = useState(false)
  return (
    <div data-testid="layout">
      <button onClick={(event) => setAnchor(anchor ? null : event.currentTarget)}>Open</button>
      <button>Outside</button>
      {command && <p>Command completed</p>}
      {anchor && (
        <Popover
          id="example"
          label="Options"
          anchor={anchor}
          onClose={() => setAnchor(null)}
          actions={actions}
        >
          {actions ? (
            <>
              <button onClick={() => setCommand(true)}>First action</button>
              <button disabled>Unavailable</button>
              <a href="#last">Last action</a>
            </>
          ) : (
            <>
              <label>
                Choice
                <select>
                  <option>One</option>
                  <option>Two</option>
                </select>
              </label>
              <button>Last control</button>
            </>
          )}
        </Popover>
      )}
    </div>
  )
}

it('renders outside the layout, focuses a control and dismisses with Escape', async () => {
  const user = userEvent.setup()
  render(<Example />)
  const trigger = screen.getByRole('button', { name: 'Open' })
  await user.click(trigger)
  const panel = screen.getByRole('dialog', { name: 'Options' })
  expect(panel.parentElement).toBe(document.body)
  expect(screen.getByTestId('layout')).not.toContainElement(panel)
  expect(screen.getByRole('combobox')).toHaveFocus()
  await user.selectOptions(screen.getByRole('combobox'), 'Two')
  expect(panel).toBeInTheDocument()
  await user.keyboard('{Escape}')
  expect(panel).not.toBeInTheDocument()
  expect(trigger).toHaveFocus()
})

it('keeps inner scrolling open but dismisses when the page scrolls or is clicked outside', async () => {
  const user = userEvent.setup()
  render(<Example />)
  const trigger = screen.getByRole('button', { name: 'Open' })
  await user.click(trigger)
  fireEvent.scroll(screen.getByRole('dialog'))
  expect(screen.getByRole('dialog')).toBeInTheDocument()
  fireEvent.scroll(window)
  expect(screen.getByRole('dialog')).toBeInTheDocument()
  vi.spyOn(trigger, 'getBoundingClientRect').mockReturnValue({
    left: 0,
    top: -50,
    bottom: -10,
    width: 100,
    height: 40,
  } as DOMRect)
  fireEvent.scroll(window)
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  await user.click(trigger)
  await user.click(screen.getByRole('button', { name: 'Outside' }))
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Outside' })).toHaveFocus()
})

it('supports action keyboard navigation and closes after a command', async () => {
  const user = userEvent.setup()
  render(<Example actions />)
  const trigger = screen.getByRole('button', { name: 'Open' })
  await user.click(trigger)
  expect(screen.getByRole('button', { name: 'First action' })).toHaveFocus()
  await user.keyboard('{ArrowDown}')
  expect(screen.getByRole('link', { name: 'Last action' })).toHaveFocus()
  await user.keyboard('{Home}')
  expect(screen.getByRole('button', { name: 'First action' })).toHaveFocus()
  await user.keyboard('{End}{ArrowDown}')
  expect(screen.getByRole('button', { name: 'First action' })).toHaveFocus()
  await user.click(screen.getByRole('button', { name: 'First action' }))
  expect(screen.getByText('Command completed')).toBeInTheDocument()
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(trigger).toHaveFocus()
})

it('allows Shift+Tab to leave the first control through the trigger', async () => {
  const user = userEvent.setup()
  render(<Example />)
  const trigger = screen.getByRole('button', { name: 'Open' })
  await user.click(trigger)
  within(screen.getByRole('dialog')).getByRole('button', { name: 'Close' }).focus()
  await user.keyboard('{Shift>}{Tab}{/Shift}')
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(trigger).toHaveFocus()
})

it('dismisses with Escape even when focus has fallen back to the document body', async () => {
  const user = userEvent.setup()
  render(<Example />)
  const trigger = screen.getByRole('button', { name: 'Open' })
  await user.click(trigger)
  screen.getByRole('combobox').blur()
  expect(screen.getByRole('dialog')).toBeInTheDocument()
  await user.keyboard('{Escape}')
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(trigger).toHaveFocus()
})

it('flips above bottom-edge triggers and stays inside the right viewport edge', () => {
  const anchor = { left: 280, top: 530, bottom: 570 } as DOMRect
  const position = placePopover(anchor, 260, 220, 320, 600)
  expect(position.left).toBeGreaterThanOrEqual(12)
  expect(position.left + 260).toBeLessThanOrEqual(308)
  expect(position.top + 220).toBeLessThan(anchor.top)
  expect(position.maxHeight).toBeLessThanOrEqual(576)
})

it('uses the viewport height when neither side of the trigger has enough room', () => {
  const anchor = { left: 20, top: 100, bottom: 140 } as DOMRect
  const position = placePopover(anchor, 260, 500, 400, 300)
  expect(position.top).toBe(12)
  expect(position.maxHeight).toBe(276)
  expect(position.top + position.maxHeight).toBeLessThanOrEqual(288)
})
