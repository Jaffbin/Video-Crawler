import { render, screen } from '@testing-library/react'
import { beforeEach, expect, it } from 'vitest'
import { useNavigation } from './useNavigation'

function View() {
  return <p>{useNavigation().view}</p>
}
beforeEach(() => window.history.replaceState(null, '', '/'))
it('opens Library for a fresh installation', () => {
  render(<View />)
  expect(screen.getByText('library')).toBeInTheDocument()
})
it('preserves the last page and lets a direct link override it', () => {
  localStorage.setItem('video-grabber-view', 'queue')
  const { unmount } = render(<View />)
  expect(screen.getByText('queue')).toBeInTheDocument()
  unmount()
  window.history.replaceState(null, '', '/#/new')
  render(<View />)
  expect(screen.getByText('new')).toBeInTheDocument()
})
