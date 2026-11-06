import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { ThemeToggle } from './ThemeToggle'
import { useTheme } from '../../hooks/useTheme'

function Appearance() {
  const { theme, toggleTheme } = useTheme()
  return <ThemeToggle theme={theme} onToggle={toggleTheme} />
}

afterEach(() => {
  delete document.documentElement.dataset.theme
  vi.restoreAllMocks()
})

it('switches the page theme with pointer and keyboard and remembers the choice', async () => {
  const user = userEvent.setup()
  const { unmount } = render(<Appearance />)
  const toggle = screen.getByRole('switch', { name: 'Dark mode' })
  expect(toggle).toBeChecked()
  expect(toggle).toHaveAttribute('title', 'Switch to light mode')
  expect(document.documentElement).toHaveAttribute('data-theme', 'dark')

  await user.click(toggle)
  expect(toggle).not.toBeChecked()
  expect(toggle).toHaveAttribute('title', 'Switch to dark mode')
  expect(document.documentElement).toHaveAttribute('data-theme', 'light')
  expect(localStorage.getItem('grab-theme')).toBe('light')

  unmount()
  render(<Appearance />)
  const restored = screen.getByRole('switch', { name: 'Dark mode' })
  expect(restored).not.toBeChecked()
  restored.focus()
  await user.keyboard(' ')
  expect(restored).toBeChecked()
  await user.keyboard('{Enter}')
  expect(restored).not.toBeChecked()
})

it('falls back to dark for an unrecognized saved value', () => {
  localStorage.setItem('grab-theme', 'unknown')
  render(<Appearance />)
  expect(screen.getByRole('switch', { name: 'Dark mode' })).toBeChecked()
  expect(document.documentElement).toHaveAttribute('data-theme', 'dark')
})

it('still switches when browser storage cannot be read or written', async () => {
  vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
    throw new Error('Storage unavailable')
  })
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
    throw new Error('Storage unavailable')
  })
  render(<Appearance />)
  await userEvent.click(screen.getByRole('switch', { name: 'Dark mode' }))
  expect(document.documentElement).toHaveAttribute('data-theme', 'light')
})

it('keeps its accessible name stable in both states', () => {
  const onToggle = vi.fn()
  const { rerender } = render(<ThemeToggle theme="light" onToggle={onToggle} />)
  expect(screen.getByRole('switch', { name: 'Dark mode' })).not.toBeChecked()
  rerender(<ThemeToggle theme="dark" onToggle={onToggle} />)
  expect(screen.getByRole('switch', { name: 'Dark mode' })).toBeChecked()
  expect(document.querySelectorAll('svg[aria-hidden="true"]')).toHaveLength(3)
})
