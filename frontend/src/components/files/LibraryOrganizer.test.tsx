import { render, screen, within, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { LibraryOrganizer } from './LibraryOrganizer'
import type { LibraryCheck } from '../../types/api'

const api = vi.hoisted(() => ({ get: vi.fn(), action: vi.fn(), recycle: vi.fn(), folder: vi.fn() }))
vi.mock('../../api/client', () => ({
  getLibraryCheck: api.get,
  libraryCheckAction: api.action,
  recycleCheckedDuplicates: api.recycle,
  openFolder: api.folder,
}))

const complete = (): LibraryCheck => ({
  id: 'scan',
  root: 'root',
  status: 'done',
  phase: 'verifying',
  checked: 2,
  total: 2,
  bytes_read: 20,
  error: '',
  result: {
    media: { count: 2, bytes: 20 },
    attachments: { count: 1, bytes: 5 },
    recovery: { count: 1, bytes: 10 },
    duplicates: [
      {
        id: 'group1',
        size: 10,
        files: [
          { path: 'one.mp4', name: 'one.mp4', favorite: true },
          { path: 'two.mp4', name: 'two.mp4', favorite: false },
        ],
      },
    ],
    duplicate_bytes: 10,
    missing: [{ path: 'gone.mp4', title: 'Gone' }],
    unknown: [{ path: 'private', reason: 'unreadable' }],
    incomplete: true,
    reasons: ['unreadable'],
    finished: 100,
  },
})
afterEach(() => vi.resetAllMocks())

it('shows space and findings without any preselection and reviews safe recycling', async () => {
  api.get.mockResolvedValue(complete())
  api.recycle.mockResolvedValue({ processed: ['one.mp4'], failed: [], recovery_ids: ['recovery'] })
  const user = userEvent.setup(),
    recycled = vi.fn()
  render(<LibraryOrganizer root="root" editingBlocked={false} onRecycled={recycled} />)
  expect(api.get).not.toHaveBeenCalled()
  await user.click(screen.getByRole('button', { name: 'Library organizer' }))
  expect(await screen.findByRole('region', { name: 'Space overview' })).toHaveTextContent(
    'Covers and subtitles',
  )
  expect(screen.getByRole('region', { name: 'Missing files' })).toHaveTextContent('gone.mp4')
  expect(screen.getByRole('region', { name: 'Could not confirm' })).toHaveTextContent(
    'Cannot access this path',
  )
  expect(screen.getAllByRole('checkbox').every((item) => !(item as HTMLInputElement).checked)).toBe(true)
  expect(screen.getByRole('button', { name: 'Review recycling' })).toBeDisabled()
  await user.click(screen.getByRole('checkbox', { name: 'Recycle duplicate one.mp4' }))
  expect(screen.getByRole('checkbox', { name: 'Recycle duplicate two.mp4' })).toBeDisabled()
  await user.click(screen.getByRole('button', { name: 'Review recycling' }))
  expect(api.recycle).not.toHaveBeenCalled()
  expect(screen.getByRole('group', { name: 'Confirm duplicate recycling' })).toHaveTextContent(
    'You can undo this.',
  )
  await user.click(screen.getByRole('button', { name: 'Confirm move to Recovery' }))
  await waitFor(() =>
    expect(recycled).toHaveBeenCalledWith({ processed: ['one.mp4'], failed: [], recovery_ids: ['recovery'] }),
  )
  expect(api.recycle).toHaveBeenCalledWith('scan', ['one.mp4'])
})

it('runs and cancels checks while allowing the panel to be closed', async () => {
  api.get.mockResolvedValue({ ...complete(), id: '', status: 'idle', result: null })
  api.action
    .mockResolvedValueOnce({ ...complete(), id: 'new', status: 'running', phase: 'hashing', result: null })
    .mockResolvedValueOnce({ ...complete(), id: 'new', status: 'cancelled', result: null })
  const user = userEvent.setup()
  render(<LibraryOrganizer root="root" editingBlocked={false} onRecycled={vi.fn()} />)
  await user.click(screen.getByRole('button', { name: 'Library organizer' }))
  await waitFor(() => expect(api.get).toHaveBeenCalledTimes(1))
  api.get.mockResolvedValue({ ...complete(), id: 'new', status: 'running', phase: 'hashing', result: null })
  await user.click(screen.getByRole('button', { name: 'Check Library' }))
  expect(await screen.findByText('Reading duplicate candidates…')).toBeInTheDocument()
  expect(
    screen.getByText('You can close this panel; the check continues in the background.'),
  ).toBeInTheDocument()
  api.get.mockResolvedValue({ ...complete(), id: 'new', status: 'cancelled', result: null })
  await user.click(screen.getByRole('button', { name: 'Cancel check' }))
  expect(await screen.findByText('Library check cancelled.')).toBeInTheDocument()
  expect(api.action.mock.calls.map(([action]) => action)).toEqual(['start', 'cancel'])
  await user.click(screen.getByRole('button', { name: 'Close' }))
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
})

it('blocks checks during downloads and keeps failed actions reviewable', async () => {
  api.get.mockResolvedValue(complete())
  api.recycle.mockResolvedValue({
    processed: [],
    failed: [{ item: 'one.mp4', error: 'file locked' }],
    recovery_ids: [],
  })
  const user = userEvent.setup(),
    props = { root: 'root', onRecycled: vi.fn() }
  const view = render(<LibraryOrganizer {...props} editingBlocked />)
  await user.click(screen.getByRole('button', { name: 'Library organizer' }))
  await screen.findByRole('region', { name: 'Space overview' })
  expect(screen.getByRole('button', { name: 'Run a new check' })).toBeDisabled()
  expect(screen.getAllByRole('checkbox').every((item) => (item as HTMLInputElement).disabled)).toBe(true)
  view.rerender(<LibraryOrganizer {...props} editingBlocked={false} />)
  await user.click(screen.getByRole('checkbox', { name: 'Recycle duplicate one.mp4' }))
  await user.click(screen.getByRole('button', { name: 'Review recycling' }))
  await user.click(screen.getByRole('button', { name: 'Confirm move to Recovery' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Some copies could not be recycled')
  expect(screen.getByRole('checkbox', { name: 'Recycle duplicate one.mp4' })).toBeChecked()
  expect(screen.getByText('one.mp4: file locked')).toBeInTheDocument()
})

it('paginates both groups and very large groups rather than mounting the entire scan', async () => {
  const state = complete()
  state.result!.duplicates[0].files = Array.from({ length: 1000 }, (_, index) => ({
    path: `${index}.mp4`,
    name: `${index}.mp4`,
    favorite: false,
  }))
  api.get.mockResolvedValue(state)
  const user = userEvent.setup()
  render(<LibraryOrganizer root="root" editingBlocked={false} onRecycled={vi.fn()} />)
  await user.click(screen.getByRole('button', { name: 'Library organizer' }))
  const group = await screen.findByRole('region', { name: 'Duplicate group group1' })
  expect(within(group).getAllByRole('checkbox')).toHaveLength(20)
  await user.click(within(group).getByRole('button', { name: 'Next' }))
  expect(within(group).getByRole('checkbox', { name: 'Recycle duplicate 20.mp4' })).toBeInTheDocument()
  expect(within(group).queryByRole('checkbox', { name: 'Recycle duplicate 0.mp4' })).not.toBeInTheDocument()
})

it('reports stale results from the backend and does not pretend the action succeeded', async () => {
  api.get.mockResolvedValue(complete())
  api.recycle.mockRejectedValue(new Error('These files changed. Run a new check before recycling.'))
  const user = userEvent.setup(),
    recycled = vi.fn()
  render(<LibraryOrganizer root="root" editingBlocked={false} onRecycled={recycled} />)
  await user.click(screen.getByRole('button', { name: 'Library organizer' }))
  await screen.findByRole('region', { name: 'Space overview' })
  await user.click(screen.getByRole('checkbox', { name: 'Recycle duplicate one.mp4' }))
  await user.click(screen.getByRole('button', { name: 'Review recycling' }))
  await user.click(screen.getByRole('button', { name: 'Confirm move to Recovery' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('These files changed.')
  expect(recycled).not.toHaveBeenCalled()
})
