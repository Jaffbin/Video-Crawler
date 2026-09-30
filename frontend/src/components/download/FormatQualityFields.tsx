import { BITRATES } from '../../lib/options'
import type { DownloadOptions } from '../../types/api'
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
}

const FALLBACK_HEIGHTS = [2160, 1440, 1080, 720, 480, 360]

/** Output format plus quality (video) or bitrate (audio). Shared by "New download" and the subscription editor. */
export function FormatQualityFields({
  options,
  onChange,
  availableHeights = [],
  analyzed = false,
  showAnalyzeHint = false,
}: Props) {
  const { t } = useI18n()
  const mp3 = options.mode === 'mp3'
  const heights = analyzed ? availableHeights : FALLBACK_HEIGHTS
  // A saved quality that the list does not offer (say 1080 after analyzing a 720p-only video) stays selectable.
  const savedQuality = Number(options.quality)
  const extra = options.quality !== 'best' && Number.isFinite(savedQuality) && !heights.includes(savedQuality)

  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <div className="control">
        <span>{t('Format')}</span>
        <Segmented
          label={t('Output format')}
          value={options.mode}
          onChange={(mode) => onChange({ mode })}
          options={[
            { value: 'mp4', label: t('MP4 video') },
            { value: 'mp3', label: t('MP3 audio') },
          ]}
        />
      </div>
      {mp3 ? (
        <label className="control">
          <span>{t('Output bitrate')}</span>
          <select
            className="field"
            value={options.abr}
            onChange={(e) => onChange({ abr: Number(e.target.value) })}
          >
            {BITRATES.map((b) => (
              <option key={b} value={b}>
                {b} kbps
              </option>
            ))}
          </select>
        </label>
      ) : (
        <label className="control">
          <span>{t('Maximum video quality')}</span>
          <select
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
            <span className="text-[11px] text-zinc-500">
              {t('Analyze the link to see available resolutions')}
            </span>
          )}
        </label>
      )}
    </div>
  )
}
