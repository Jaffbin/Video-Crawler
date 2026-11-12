import { useId, useRef } from 'react'
import { audioQualityLabel } from '../../lib/options'
import type { DownloadMode, DownloadOptions } from '../../types/api'
import { HelpButton, HelpNote, useHelpTip } from '../ui/HelpTip'
import { Segmented } from '../ui/Segmented'
import { useI18n } from '../../i18n'

interface Props {
  options: Pick<DownloadOptions, 'mode' | 'quality' | 'abr'>
  onChange: (patch: Partial<DownloadOptions>) => void
  /**
   * Resolutions detected by "Analyze link". When omitted, the usual fixed list is offered instead,
   * which is what a saved subscription uses (there is no single video to analyze).
   */
  availableHeights?: number[]
  /** True once a link has been analyzed, even if it reported no resolutions. */
  analyzed?: boolean
  /** Show the "Analyze the link..." hint. Only "New download" can analyze, so the subscription editor leaves it off. */
  showAnalyzeHint?: boolean
  allowImages?: boolean
}

const FALLBACK_HEIGHTS = [2160, 1440, 1080, 720, 480, 360]

/** Output format plus quality (video) or bitrate (audio). Shared by "New download" and the subscription editor. */
export function FormatQualityFields({
  options,
  onChange,
  availableHeights = [],
  analyzed = false,
  showAnalyzeHint = false,
  allowImages = false,
}: Props) {
  const { t } = useI18n()
  const fieldId = useId()
  const audioTip = useHelpTip()
  const mp3Tip = useHelpTip()
  const qualityTip = useHelpTip()
  const lastAudio = useRef<DownloadMode>('mp3')
  const lastImage = useRef<DownloadMode>('cover')
  if (options.mode === 'mp3' || options.mode === 'original') lastAudio.current = options.mode
  if (options.mode === 'cover' || options.mode === 'image') lastImage.current = options.mode
  const category =
    options.mode === 'mp4'
      ? 'video'
      : options.mode === 'mp3' || options.mode === 'original'
        ? 'audio'
        : 'image'
  const mp3 = options.mode === 'mp3'
  const heights = analyzed ? availableHeights : FALLBACK_HEIGHTS
  // A saved quality that the list does not offer (say 1080 after analyzing a 720p-only video) stays selectable.
  const savedQuality = Number(options.quality)
  const extra = options.quality !== 'best' && Number.isFinite(savedQuality) && !heights.includes(savedQuality)

  return (
    <div className="grid min-w-0 gap-3">
      <div className="control">
        <span>{t('Download type')}</span>
        <Segmented
          wrap
          label={t('Download type')}
          value={category}
          onChange={(value) =>
            onChange({
              mode: value === 'video' ? 'mp4' : value === 'audio' ? lastAudio.current : lastImage.current,
            })
          }
          options={[
            { value: 'video', label: t('Video') },
            { value: 'audio', label: t('Audio') },
            ...(allowImages ? [{ value: 'image' as const, label: t('Images') }] : []),
          ]}
        />
      </div>
      {category !== 'video' && (
        <div className="control">
          <span>{t(category === 'audio' ? 'Audio format' : 'Image source')}</span>
          <Segmented
            wrap
            label={t('Output format')}
            value={options.mode}
            onChange={(mode) => onChange({ mode })}
            options={[
              ...(category === 'audio'
                ? [
                    { value: 'mp3' as const, label: t('MP3 audio') },
                    { value: 'original' as const, label: t('Keep source audio') },
                  ]
                : [
                    { value: 'cover' as const, label: t('Video cover') },
                    { value: 'image' as const, label: t('Direct image') },
                  ]),
            ]}
          />
        </div>
      )}
      {options.mode === 'cover' || options.mode === 'image' ? (
        <p className="self-center text-xs text-zinc-400">
          {t('Save the original image format. No ffmpeg conversion is needed.')}
        </p>
      ) : options.mode === 'original' ? (
        <div className="grid gap-2">
          <div className="flex items-center gap-2">
            <p className="text-sm text-zinc-200">{t('Best available audio · no re-encoding')}</p>
            <HelpButton tip={audioTip} about={t('Keep source audio')} />
          </div>
          <HelpNote tip={audioTip}>
            <p>
              {t(
                'The source determines the format, such as M4A or Opus. Some older players may not support it.',
              )}
            </p>
            <p>
              {t('This preserves the audio offered by the site, not necessarily the original recording.')}
            </p>
          </HelpNote>
        </div>
      ) : mp3 ? (
        <div className="grid gap-2">
          <div className="control">
            <div className="control-label">
              <label htmlFor={`${fieldId}-abr`}>{t('Audio quality')}</label>
              <HelpButton tip={mp3Tip} about={t('Audio quality')} />
            </div>
            <select
              id={`${fieldId}-abr`}
              className="field"
              value={options.abr}
              onChange={(e) => onChange({ abr: Number(e.target.value) })}
            >
              {[320, 192, 128, ...(![320, 192, 128].includes(options.abr) ? [options.abr] : [])].map((b) => (
                <option key={b} value={b}>
                  {t(audioQualityLabel(b))} · {b} kbps
                </option>
              ))}
            </select>
          </div>
          <HelpNote tip={mp3Tip}>
            {t(
              'The best available source audio is used. A higher MP3 bitrate cannot restore details missing from the source.',
            )}
          </HelpNote>
          <details className="text-xs text-zinc-400">
            <summary className="cursor-pointer">{t('Custom bitrate')}</summary>
            <label className="control mt-2">
              <span>{t('Output bitrate')}</span>
              <select
                className="field"
                value={options.abr}
                onChange={(e) => onChange({ abr: Number(e.target.value) })}
              >
                {[320, 256, 192, 128, 96].map((b) => (
                  <option key={b} value={b}>
                    {b} kbps
                  </option>
                ))}
              </select>
            </label>
          </details>
        </div>
      ) : (
        <div className="control">
          <div className="control-label">
            <label htmlFor={`${fieldId}-quality`}>{t('Maximum video quality')}</label>
            {showAnalyzeHint && !analyzed && (
              <HelpButton tip={qualityTip} about={t('Maximum video quality')} />
            )}
          </div>
          <select
            id={`${fieldId}-quality`}
            className="field"
            value={options.quality}
            onChange={(e) => onChange({ quality: e.target.value })}
          >
            <option value="best">{t('Best available')}</option>
            {extra && <option value={options.quality}>{options.quality}p</option>}
            {heights.map((h) => (
              <option key={h} value={String(h)}>
                {h}p
              </option>
            ))}
          </select>
          {analyzed && availableHeights.length > 0 && (
            <span className="text-[11px] text-zinc-500">
              {t('{count} resolutions detected', { count: availableHeights.length })}
            </span>
          )}
          {showAnalyzeHint && !analyzed && (
            <HelpNote tip={qualityTip}>{t('Analyze the link to see available resolutions')}</HelpNote>
          )}
        </div>
      )}
    </div>
  )
}
