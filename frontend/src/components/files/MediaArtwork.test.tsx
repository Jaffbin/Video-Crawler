import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { MediaArtwork } from './MediaArtwork'

it('prefers the saved website cover over extracting a video frame', () => {
  const { container } = render(
    <MediaArtwork
      file={{ name: 'video.mp4', path: 'video.mp4', size: 1, mtime: 1, thumbnail: 'video.jpg' }}
      onOpen={vi.fn()}
    />,
  )
  expect(container.querySelector('img')).toHaveAttribute('src', expect.stringContaining('video.jpg'))
  expect(container.querySelector('video')).toBeNull()
  expect(screen.getByRole('button')).toHaveAccessibleName('View details for video.mp4')
  fireEvent.error(container.querySelector('img')!)
  expect(container.querySelector('img')).toBeNull()
})
