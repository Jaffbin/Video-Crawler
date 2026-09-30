import { AlertTriangle, Film, Music, Pencil, RefreshCw, Trash2 } from 'lucide-react'
import { useState } from 'react'
import {
  checkSubscriptionNow,
  previewSubscription,
  removeSubscription,
  updateSubscription,
} from '../../api/client'
import type { ToastFn } from '../../hooks/useToasts'
import { describeOptions } from '../../lib/options'
import { formatDate } from '../../lib/utils'
import type { DownloadOptions, Subscription, SubscriptionPreview } from '../../types/api'
import { useI18n } from '../../i18n'
import { Button } from '../ui/Button'
import { FormatQualityFields } from '../download/FormatQualityFields'
import { normalizeFilters, SubscriptionFiltersFields } from './SubscriptionFiltersFields'

interface Props {
  sub: Subscription
  onChanged: () => void
  onToast: ToastFn
}

function nextCheckLabel(
  sub: Subscription,
  t: (key: string, values?: Record<string, string | number>) => string,
): string {
  if (!sub.enabled) return t('Paused')
  if (sub.checking) return t('Checking now…')
  if (!sub.next_check) return t('Checking soon')
  const ms = sub.next_check * 1000 - Date.now()
  if (ms <= 0) return t('Checking soon')
  const minutes = Math.round(ms / 60000)
  return minutes < 60
    ? t('Next check in ~{count} min', { count: minutes })
    : t('Next check in ~{count} h', { count: Math.round(minutes / 60) })
}

type Draft = { options: Pick<DownloadOptions, 'mode' | 'quality' | 'abr'>; filters: Subscription['filters'] }

const draftOf = (sub: Subscription): Draft => ({
  options: { mode: sub.options.mode, quality: sub.options.quality, abr: sub.options.abr },
  filters: normalizeFilters(sub.filters),
})

export function SubscriptionCard({ sub, onChanged, onToast }: Props) {
  const { t } = useI18n()
  // The draft is only created when the editor opens, so the background refresh of the list never overwrites what is being typed.
  const [draft, setDraft] = useState<Draft | null>(null)
  const [preview, setPreview] = useState<SubscriptionPreview | null>(null)
  const [previewBusy, setPreviewBusy] = useState(false)
  const [previewError, setPreviewError] = useState('')
  const changed = draft !== null && JSON.stringify(draft) !== JSON.stringify(draftOf(sub))
  const errorTitleKey = sub.last_error_kind ? `error.title.${sub.last_error_kind}` : ''
  const subscriptionError =
    errorTitleKey && t(errorTitleKey) !== errorTitleKey ? t(errorTitleKey) : sub.last_error

  async function save() {
    if (!draft) return
    try {
      await updateSubscription(sub.id, {
        options: { ...sub.options, ...draft.options },
        filters: draft.filters,
      })
      onToast(`${t('Settings saved')}: ${describeOptions({ ...sub.options, ...draft.options })}`)
      setDraft(null)
      onChanged()
    } catch (e) {
      onToast(e instanceof Error ? e.message : t('Could not save the settings'), true)
    }
  }

  async function run(action: () => Promise<unknown>, message?: string) {
    try {
      await action()
      if (message) onToast(message)
      onChanged()
    } catch (e) {
      onToast(e instanceof Error ? e.message : t('That did not work'), true)
    }
  }

  async function loadPreview() {
    setPreviewBusy(true)
    setPreviewError('')
    try {
      setPreview(await previewSubscription(sub.id, draft?.filters ?? normalizeFilters(sub.filters)))
    } catch (e) {
      setPreview(null)
      setPreviewError(e instanceof Error ? e.message : t('Could not preview this subscription'))
    } finally {
      setPreviewBusy(false)
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
              nextCheckLabel(sub, t),
              sub.total_queued > 0 && t('{count} queued so far', { count: sub.total_queued }),
              sub.total_filtered > 0 && t('{count} filtered so far', { count: sub.total_filtered }),
              sub.last_checked > 0 && t('last checked {date}', { date: formatDate(sub.last_checked) }),
            ]
              .filter(Boolean)
              .join(' · ')}
          </p>
          <p className="mt-1 text-xs text-zinc-300">
            {t('Downloads: {value}', { value: describeOptions(sub.options) })}
          </p>
          {sub.last_checked > 0 && (
            <p className="mt-1 text-xs text-zinc-400">
              {t('Last check: {found} new, {queued} queued, {filtered} filtered', {
                found: sub.last_found ?? 0,
                queued: sub.last_queued ?? 0,
                filtered: sub.last_filtered ?? 0,
              })}
            </p>
          )}
        </div>
        <label className="flex items-center gap-2 text-xs text-zinc-400">
          <input
            type="checkbox"
            checked={sub.enabled}
            onChange={(e) => run(() => updateSubscription(sub.id, { enabled: e.target.checked }))}
          />
          {t('Active')}
        </label>
      </div>

      {sub.last_error && (
        <p
          role="alert"
          className="flex gap-2 rounded-xl bg-red-500/[.08] px-3 py-2 text-xs leading-5 text-red-200"
        >
          <AlertTriangle aria-hidden size={14} className="mt-0.5 shrink-0" />
          {subscriptionError}
        </p>
      )}

      {draft && (
        <div className="grid gap-3 rounded-xl bg-white/[.035] p-3">
          <FormatQualityFields
            options={draft.options}
            onChange={(change) => setDraft({ ...draft, options: { ...draft.options, ...change } })}
          />
          <SubscriptionFiltersFields
            filters={draft.filters}
            onChange={(filters) => {
              setDraft({ ...draft, filters })
              setPreview(null)
            }}
          />
          <p className="text-xs text-zinc-500">{t('Changes apply to videos queued from now on.')}</p>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setDraft(null)}>
              {t('Cancel')}
            </Button>
            <Button variant="primary" onClick={save} disabled={!changed}>
              {t('Save')}
            </Button>
          </div>
        </div>
      )}

      <div className="flex justify-end gap-1">
        <button type="button" className="action-btn" disabled={previewBusy} onClick={loadPreview}>
          {previewBusy ? t('Loading preview…') : t('Preview filters')}
        </button>
        {!draft && (
          <button type="button" className="action-btn" onClick={() => setDraft(draftOf(sub))}>
            <Pencil aria-hidden size={13} /> {t('Edit format & filters')}
          </button>
        )}
        <button
          type="button"
          className="action-btn"
          disabled={sub.checking}
          onClick={() => run(() => checkSubscriptionNow(sub.id), t('Checking now'))}
        >
          <RefreshCw aria-hidden size={13} className={sub.checking ? 'animate-spin' : ''} /> {t('Check now')}
        </button>
        <button type="button" className="action-btn" onClick={() => run(() => removeSubscription(sub.id))}>
          <Trash2 aria-hidden size={13} /> {t('Remove')}
        </button>
      </div>
      {previewError && (
        <p role="alert" className="text-xs text-red-300">
          {previewError}
        </p>
      )}
      {preview && (
        <div className="rounded-xl border border-white/[.07] p-3 text-xs">
          <p className="mb-2 text-zinc-400">
            {t('Current candidates: {count}', { count: preview.total_candidates })}
            {' · '}
            {t('Would queue: {count}', { count: preview.would_queue })}
            {' · '}
            {t('Filtered: {count}', { count: preview.filtered })}
          </p>
          {preview.items.length === 0 ? (
            <p className="text-zinc-500">{t('No entries found.')}</p>
          ) : (
            <ul className="max-h-56 space-y-1 overflow-auto">
              {preview.items.map((item) => (
                <li key={item.id} className="flex gap-2">
                  <span className={item.eligible && !item.reason ? 'text-emerald-300' : 'text-zinc-500'}>
                    {item.reason
                      ? t(`filter.${item.reason}`)
                      : item.eligible
                        ? t('Would queue')
                        : t('Matches filters')}
                    {!item.eligible && ` · ${t('Already seen or baseline')}`}
                  </span>
                  <span className="min-w-0 flex-1 truncate" title={item.title || item.url}>
                    {item.title || item.url}
                  </span>
                </li>
              ))}
            </ul>
          )}
          <p className="mt-2 text-zinc-500">{t('Preview does not add downloads or mark videos as seen.')}</p>
        </div>
      )}
    </li>
  )
}
