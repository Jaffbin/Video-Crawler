import { Check, Image as ImageIcon, ListVideo } from 'lucide-react'
import type { ProbeResult } from '../../types/api'
import { formatDuration } from '../../lib/utils'

interface Props {
  probe: ProbeResult
  quality: string
  onPickQuality: (quality: string) => void
}

export function ProbeCard({ probe, quality, onPickQuality }: Props) {
  if (probe.error) {
    return (
      <div
        role="alert"
        className="rounded-xl border border-red-400/15 bg-red-500/[.06] p-4 text-sm text-red-200"
      >
        {probe.error}
      </div>
    )
  }

  const meta = [probe.uploader, probe.duration ? formatDuration(probe.duration) : '', probe.extractor].filter(
    Boolean,
  )

  return (
    <div className="overflow-hidden rounded-2xl border border-white/8 bg-white/[.025]">
      <div className="flex gap-4 p-4">
        {probe.thumbnail ? (
          <img
            src={probe.thumbnail}
            alt=""
            referrerPolicy="no-referrer"
            className="h-24 w-40 shrink-0 rounded-xl object-cover"
          />
        ) : (
          <div className="grid h-24 w-40 shrink-0 place-items-center rounded-xl bg-white/[.04]">
            <ImageIcon aria-hidden className="text-zinc-500" />
          </div>
        )}
        <div className="min-w-0 flex-1">
          <div className="mb-1 text-xs uppercase tracking-wider text-zinc-400">{probe.kind ?? 'media'}</div>
          <h3 className="line-clamp-2 text-sm font-medium text-zinc-100">{probe.title || 'Untitled'}</h3>
          {meta.length > 0 && <p className="mt-1 text-xs text-zinc-400">{meta.join('   ')}</p>}
          {probe.kind === 'playlist' && probe.count != null && (
            <p className="mt-1 flex items-center gap-1 text-xs text-zinc-400">
              <ListVideo aria-hidden size={13} />
              {probe.count} items. Use “Playlist range” in Advanced settings to download only some.
            </p>
          )}
        </div>
      </div>

      {probe.items && probe.items.length > 0 && (
        <ul className="space-y-0.5 border-t border-white/8 px-4 py-3 text-xs text-zinc-400">
          {probe.items.map((title, i) => (
            <li key={`${i}-${title}`} className="truncate">
              {i + 1}. {title}
            </li>
          ))}
        </ul>
      )}

      {probe.heights && probe.heights.length > 0 && (
        <div className="border-t border-white/8 px-4 py-3">
          <div className="mb-2 text-xs font-medium uppercase tracking-wider text-zinc-400">
            Available quality
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
                    selected ? 'bg-white text-black' : 'bg-white/[.06] text-zinc-300 hover:bg-white/[.1]'
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
          <p>
            {probe.count ?? probe.sources.length} media source
            {(probe.count ?? probe.sources.length) > 1 ? 's' : ''} found
            {probe.rendered ? ' by rendering the page in a headless browser' : ' in the page source'}. They
            are tried one by one.
          </p>
          <ul className="mt-2 space-y-0.5 font-mono">
            {probe.sources.slice(0, 5).map((s) => (
              <li key={s} className="truncate" title={s}>
                {s}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
