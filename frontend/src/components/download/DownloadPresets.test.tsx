import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, it, vi } from 'vitest'
import { DownloadPresets } from './DownloadPresets'
import { DEFAULT_OPTIONS } from '../../lib/options'
import { PRESETS_KEY, readPresets } from '../../lib/presets'

beforeEach(() => localStorage.clear())

it('applies a built-in preset without submitting a download or copying connection settings', async () => {
  const apply = vi.fn(),
    user = userEvent.setup()
  render(
    <DownloadPresets
      options={{ ...DEFAULT_OPTIONS, proxy: 'private', items: '1,2' }}
      onApply={apply}
      disabled={false}
    />,
  )
  await user.selectOptions(screen.getByRole('combobox', { name: 'Download preset' }), 'mp3')
  expect(apply).toHaveBeenCalledWith(expect.objectContaining({ mode: 'mp3', abr: 320 }))
  expect(apply.mock.calls[0][0]).not.toHaveProperty('proxy')
  expect(apply.mock.calls[0][0]).not.toHaveProperty('items')
  expect(screen.queryByRole('button', { name: 'Start download' })).not.toBeInTheDocument()
})

it('saves, renames and confirms deletion of a custom preset; rejects duplicate names', async () => {
  const user = userEvent.setup()
  render(
    <DownloadPresets options={{ ...DEFAULT_OPTIONS, proxy: 'secret' }} onApply={vi.fn()} disabled={false} />,
  )
  await user.click(screen.getByRole('button', { name: 'Save current as preset' }))
  await user.type(screen.getByRole('textbox', { name: 'Preset name' }), 'Mine')
  await user.click(screen.getByRole('button', { name: 'Save' }))
  expect(readPresets()[0].name).toBe('Mine')
  expect(localStorage.getItem(PRESETS_KEY)).not.toContain('secret')
  await user.click(screen.getByRole('button', { name: 'Save current as preset' }))
  await user.type(screen.getByRole('textbox', { name: 'Preset name' }), 'mine')
  await user.click(screen.getByRole('button', { name: 'Save' }))
  expect(screen.getByRole('alert')).toHaveTextContent('already exists')
  await user.click(screen.getByRole('button', { name: 'Cancel' }))
  await user.click(screen.getByRole('button', { name: 'Rename preset' }))
  await user.clear(screen.getByRole('textbox', { name: 'Preset name' }))
  await user.type(screen.getByRole('textbox', { name: 'Preset name' }), 'Renamed')
  await user.click(screen.getByRole('button', { name: 'Save' }))
  expect(readPresets()[0].name).toBe('Renamed')
  await user.click(screen.getByRole('button', { name: 'Delete preset' }))
  expect(readPresets()).toHaveLength(1)
  await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Delete preset' }))
  expect(readPresets()).toHaveLength(0)
})
