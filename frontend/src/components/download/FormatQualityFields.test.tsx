import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { FormatQualityFields } from './FormatQualityFields'

const video = { mode: 'mp4' as const, quality: 'best', abr: 192 }
const optionValues = (select: HTMLElement) =>
  [...select.querySelectorAll('option')].map((o) => o.getAttribute('value'))

describe('FormatQualityFields', () => {
  it('offers the usual resolutions when nothing was analyzed (what a subscription uses)', () => {
    render(<FormatQualityFields options={video} onChange={() => {}} />)
    const select = screen.getByLabelText(/maximum video quality/i)
    expect(optionValues(select)).toEqual(['best', '2160', '1440', '1080', '720', '480', '360'])
    expect(screen.queryByText(/analyze the link/i)).toBeNull()
  })

  it('offers only the detected resolutions after analyzing, and says how many', () => {
    render(
      <FormatQualityFields
        options={video}
        onChange={() => {}}
        analyzed
        availableHeights={[1080, 720]}
        showAnalyzeHint
      />,
    )
    expect(optionValues(screen.getByLabelText(/maximum video quality/i))).toEqual(['best', '1080', '720'])
    expect(screen.getByText('2 resolutions detected')).toBeInTheDocument()
  })

  it('shows the analyze hint only where analyzing is possible', () => {
    const { rerender } = render(<FormatQualityFields options={video} onChange={() => {}} showAnalyzeHint />)
    expect(screen.getByText(/analyze the link/i)).toBeInTheDocument()
    rerender(<FormatQualityFields options={video} onChange={() => {}} />)
    expect(screen.queryByText(/analyze the link/i)).toBeNull()
  })

  it('keeps a saved quality selectable even if the analyzed video does not offer it', () => {
    render(
      <FormatQualityFields
        options={{ ...video, quality: '1440' }}
        onChange={() => {}}
        analyzed
        availableHeights={[720]}
      />,
    )
    const select = screen.getByLabelText(/maximum video quality/i) as HTMLSelectElement
    expect(optionValues(select)).toContain('1440')
    expect(select.value).toBe('1440')
  })

  it('switches to a bitrate picker for MP3', () => {
    render(<FormatQualityFields options={{ ...video, mode: 'mp3' }} onChange={() => {}} />)
    expect(screen.queryByLabelText(/maximum video quality/i)).toBeNull()
    expect(optionValues(screen.getByLabelText(/output bitrate/i))).toEqual(['320', '256', '192', '128', '96'])
  })

  it('reports changes as partial patches', async () => {
    const onChange = vi.fn()
    render(<FormatQualityFields options={video} onChange={onChange} />)
    await userEvent.click(screen.getByRole('radio', { name: 'MP3 audio' }))
    expect(onChange).toHaveBeenLastCalledWith({ mode: 'mp3' })
    await userEvent.selectOptions(screen.getByLabelText(/maximum video quality/i), '720')
    expect(onChange).toHaveBeenLastCalledWith({ quality: '720' })
  })
})
