import { AlertTriangle, Film, Music, Pencil, RefreshCw, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { checkSubscriptionNow, removeSubscription, updateSubscription } from '../../api/client'
import type { ToastFn } from '../../hooks/useToasts'
import { describeOptions } from '../../lib/options'
import { formatDate } from '../../lib/utils'
import type { DownloadOptions, Subscription } from '../../types/api'
import { Button } from '../ui/Button'
import { FormatQualityFields } from '../download/FormatQualityFields'

interface Props {
  sub: Subscription
  onChanged: () => void
  onToast: ToastFn
}

function nextCheckLabel(sub: Subscription): string {
  if (!sub.enabled) return 'Paused'
  if (sub.checking) return 'Checking now…'
  if (!sub.next_check) return 'Checking soon'
  const ms = sub.next_check * 1000 - Date.now()
  if (ms <= 0) return 'Checking soon'
  const minutes = Math.round(ms / 60000)
  return minutes < 60 ? `Next check in ~${minutes} min` : `Next check in ~${Math.round(minutes / 60)} h`
}

type Draft = Pick<DownloadOptions, 'mode' | 'quality' | 'abr'>

const draftOf = (o: DownloadOptions): Draft => ({ mode: o.mode, quality: o.quality, abr: o.abr })

export function SubscriptionCard({ sub, onChanged, onToast }: Props) {
  // The draft is only created when the editor opens, so the background refresh of the list never overwrites what is being typed.
  const [draft, setDraft] = useState<Draft | null>(null)
  const changed = draft !== null && JSON.stringify(draft) !== JSON.stringify(draftOf(sub.options))

  async function save() {
    if (!draft) return
    try {
      await updateSubscription(sub.id, { options: { ...sub.options, ...draft } })
      onToast(
        `Saved: ${describeOptions({ ...sub.options, ...draft })}. Applies to videos queued from now on.`,
      )
      setDraft(null)
      onChanged()
    } catch (e) {
      onToast(e instanceof Error ? e.message : 'Could not save the settings', true)
    }
  }

  async function run(action: () => Promise<unknown>, message?: string) {
    try {
      await action()
      if (message) onToast(message)
      onChanged()
    } catch (e) {
      onToast(e instanceof Error ? e.message : 'That did not work', true)
    }
  }

  return (
    <li className="grid gap-2 rounded-2xl border border-white/[.07] bg-white/[.02] p-4">
      <div className="flex items-start gap-3">
        <div
          aria-hidden
          className="mt-0.5 grid size-9 shrink-0 place-items-center rounded-xl bg-white/[.06] text-zinc-300"
        >
          {sub.mode === 'mp3' ? <Music size={17} /> : <Film size={17} />}
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-sm font-medium" title={sub.url}>
            {sub.title || sub.url}
          </h3>
          <p className="mt-0.5 text-xs text-zinc-400">
            {[
              nextCheckLabel(sub),
              sub.total_queued > 0 &&
                `${sub.total_queued} video${sub.total_queued === 1 ? '' : 's'} queued so far`,
              sub.last_checked > 0 && `last checked ${formatDate(sub.last_checked)}`,
            ]
              .filter(Boolean)
              .join(' · ')}
          </p>
          <p className="mt-1 text-xs text-zinc-300">Downloads: {describeOptions(sub.options)}</p>
        </div>
        <label className="flex items-center gap-2 text-xs text-zinc-400">
          <input
            type="checkbox"
            checked={sub.enabled}
            onChange={(e) => run(() => updateSubscription(sub.id, { enabled: e.target.checked }))}
          />
          Active
        </label>
      </div>

      {sub.last_error && (
        <p
          role="alert"
          className="flex gap-2 rounded-xl bg-red-500/[.08] px-3 py-2 text-xs leading-5 text-red-200"
        >
          <AlertTriangle aria-hidden size={14} className="mt-0.5 shrink-0" />
          {sub.last_error}
        </p>
      )}

      {draft && (
        <div className="grid gap-3 rounded-xl bg-white/[.035] p-3">
          <FormatQualityFields options={draft} onChange={(change) => setDraft({ ...draft, ...change })} />
          <p className="text-xs text-zinc-500">
            Changes apply to videos queued from now on; ones already in the queue keep their settings.
          </p>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setDraft(null)}>
              Cancel
            </Button>
            <Button variant="primary" onClick={save} disabled={!changed}>
              Save
            </Button>
          </div>
        </div>
      )}

      <div className="flex justify-end gap-1">
        {!draft && (
          <button type="button" className="action-btn" onClick={() => setDraft(draftOf(sub.options))}>
            <Pencil aria-hidden size={13} /> Edit format
          </button>
        )}
        <button
          type="button"
          className="action-btn"
          disabled={sub.checking}
          onClick={() => run(() => checkSubscriptionNow(sub.id), 'Checking now')}
        >
          <RefreshCw aria-hidden size={13} className={sub.checking ? 'animate-spin' : ''} /> Check now
        </button>
        <button type="button" className="action-btn" onClick={() => run(() => removeSubscription(sub.id))}>
          <Trash2 aria-hidden size={13} /> Remove
        </button>
      </div>
    </li>
  )
}
