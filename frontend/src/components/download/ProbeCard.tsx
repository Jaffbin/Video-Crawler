import { Check, Image as ImageIcon, ListVideo } from 'lucide-react'
import type { DownloadOptions, ProbeResult } from '../../types/api'
import { formatBytes, formatDuration } from '../../lib/utils'
import { useI18n } from '../../i18n'
import { previewSelection } from '../../lib/playlist'

interface Props {
  probe: ProbeResult
  quality: string
  onPickQuality: (quality: string) => void
  options?: DownloadOptions
  selectedItems?: number[] | null
  onPickItems?: (indices: number[]) => void
}

export function ProbeCard({
  probe,
  quality,
  onPickQuality,
  options,
  selectedItems = null,
  onPickItems,
}: Props) {
  const { t } = useI18n()
  if (probe.error) {
    return (
      <div
        role="alert"
        className="rounded-xl border border-red-400/15 bg-red-500/[.06] p-4 text-sm text-red-200"
      >
        {t(probe.error)}
      </div>
    )
  }

  const meta = [probe.uploader, probe.duration ? formatDuration(probe.duration) : '', probe.extractor].filter(
    Boolean,
  )
  const sizeCurrent =
    !options ||
    !probe.selection ||
    (options.mode === probe.selection.mode &&
      (options.mode === 'mp3'
        ? options.abr === probe.selection.abr
        : options.mode === 'original' || options.quality === probe.selection.quality))
  const entries = probe.playlist_entries ?? []
  const checkedIndices =
    selectedItems ??
    previewSelection(
      entries.map((entry) => entry.index),
      options?.items ?? '',
    )

  return (
    <div className="overflow-hidden rounded-2xl border border-white/8 bg-white/[.025]">
      <div className="flex gap-4 p-4">
        {probe.thumbnail ? (
          <img
            src={probe.thumbnail}
            alt=""
            referrerPolicy="no-referrer"
            className="h-20 w-24 shrink-0 rounded-xl object-cover sm:h-24 sm:w-40"
          />
        ) : (
          <div className="grid h-20 w-24 shrink-0 place-items-center rounded-xl bg-white/[.04] sm:h-24 sm:w-40">
            <ImageIcon aria-hidden className="text-zinc-500" />
          </div>
        )}
        <div className="min-w-0 flex-1">
          <div className="mb-1 text-xs uppercase tracking-wider text-zinc-400">
            {t(probe.kind ?? 'media')}
          </div>
          <h3 className="line-clamp-2 text-sm font-medium text-zinc-100">{probe.title || t('Untitled')}</h3>
          {meta.length > 0 && <p className="mt-1 text-xs text-zinc-400">{meta.join(' · ')}</p>}
          {probe.kind === 'video' && (
            <p className="mt-2 text-xs text-emerald-200">
              {sizeCurrent
                ? probe.size?.bytes
                  ? t('Estimated size: {size}', { size: formatBytes(probe.size.bytes) })
                  : t('Size unavailable from this site.')
                : t('Analyze again to update the size estimate.')}
            </p>
          )}
          {(probe.kind === 'cover' || probe.kind === 'image') && (
            <p className="mt-2 text-xs text-emerald-200">
              {probe.image_format || t('Original format')}
              {probe.size?.bytes ? ` · ${formatBytes(probe.size.bytes)}` : ''}
              {probe.kind === 'cover' && !probe.thumbnail
                ? ` · ${t('No cover was reported by this source.')}`
                : ''}
            </p>
          )}
          {probe.kind === 'playlist' && probe.count != null && (
            <p className="mt-1 flex items-center gap-1 text-xs text-zinc-400">
              <ListVideo aria-hidden size={13} />
              {t('{count} playlist items', { count: probe.count })}
            </p>
          )}
        </div>
      </div>

      {entries.length > 0 ? (
        <div className="grid gap-2 border-t border-white/8 px-4 py-3 text-xs">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="font-medium text-zinc-300">{t('Playlist preview')}</span>
            {onPickItems && (
              <div className="flex gap-2">
                <button
                  className="action-btn"
                  onClick={() => onPickItems(entries.map((entry) => entry.index))}
                >
                  {t('Select preview entries')}
                </button>
                <button className="action-btn" onClick={() => onPickItems([])}>
                  {t('Clear selection')}
                </button>
              </div>
            )}
          </div>
          <p className="text-zinc-400">
            {t(
              onPickItems
                ? 'Choose entries here, or use Playlist range for other entries. Selecting here downloads only the checked preview entries.'
                : 'Use one playlist link to select entries.',
            )}
          </p>
          {options?.items && selectedItems === null && (
            <p className="text-amber-200">
              {t('Configured playlist range: {range}', { range: options.items })}
            </p>
          )}
          <ul className="max-h-56 space-y-2 overflow-auto">
            {entries.map((entry) => (
              <li key={entry.index}>
                <label className="flex items-center gap-2 text-zinc-300">
                  <input
                    type="checkbox"
                    disabled={!onPickItems || checkedIndices === undefined}
                    checked={checkedIndices === null || (checkedIndices?.includes(entry.index) ?? false)}
                    onChange={(event) => {
                      const current = checkedIndices ?? entries.map((item) => item.index)
                      onPickItems?.(
                        event.target.checked
                          ? [...current, entry.index].sort((a, b) => a - b)
                          : current.filter((index) => index !== entry.index),
                      )
                    }}
                  />
                  <span className="min-w-0 flex-1 truncate" title={entry.title}>
                    {entry.index}. {entry.title || t('Untitled')}
                  </span>
                  {entry.duration != null && (
                    <span className="text-zinc-500">{formatDuration(entry.duration)}</span>
                  )}
                </label>
              </li>
            ))}
          </ul>
          {(probe.count ?? 0) > entries.length && (
            <p className="text-amber-200">
              {t('Showing the first {count} entries. Use Playlist range for the rest.', {
                count: entries.length,
              })}
            </p>
          )}
          {selectedItems !== null && (
            <p className="text-emerald-200">{t('{count} selected', { count: selectedItems.length })}</p>
          )}
        </div>
      ) : (
        probe.items &&
        probe.items.length > 0 && (
          <div className="border-t border-white/8 px-4 py-3">
            <div className="mb-2 text-xs font-medium uppercase tracking-wider text-zinc-400">
              {t('Playlist preview')}
            </div>

            <ul className="max-h-40 space-y-0.5 overflow-auto text-xs text-zinc-400">
              {probe.items.slice(0, 10).map((title, i) => (
                <li key={`${i}-${title}`} className="truncate">
                  {i + 1}. {title}
                </li>
              ))}
            </ul>

            {probe.items.length > 10 && (
              <p className="mt-2 text-xs text-zinc-500">
                {t('+{count} more items', { count: probe.items.length - 10 })}
              </p>
            )}
          </div>
        )
      )}

      {(!options || options.mode === 'mp4') && probe.heights && probe.heights.length > 0 && (
        <div className="border-t border-white/8 px-4 py-3">
          <div className="mb-2 text-xs font-medium uppercase tracking-wider text-zinc-400">
            {t('Available quality')}
          </div>
          <div className="flex flex-wrap gap-2">
            {probe.heights.slice(0, 8).map((h) => {
              const selected = quality === String(h)
              return (
                <button
                  key={h}
                  type="button"
                  aria-pressed={selected}
                  onClick={() => onPickQuality(String(h))}
                  className={`inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs font-medium transition ${
                    selected ? 'bg-white text-zinc-950' : 'bg-white/[.06] text-zinc-300 hover:bg-white/[.1]'
                  }`}
                >
                  {selected && <Check aria-hidden size={12} />} {h}p
                </button>
              )
            })}
          </div>
        </div>
      )}

      {probe.sources && probe.sources.length > 0 && (
        <div className="border-t border-white/8 px-4 py-3 text-xs text-zinc-400">
          {t('{count} media sources detected{rendered}', {
            count: probe.count ?? probe.sources.length,
            rendered: probe.rendered ? t(' using page rendering.') : '.',
          })}
        </div>
      )}
    </div>
  )
}
