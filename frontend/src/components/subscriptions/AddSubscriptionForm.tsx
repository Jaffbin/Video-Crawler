import { Loader2, Plus } from 'lucide-react'
import { useRef, useState } from 'react'
import { addSubscription } from '../../api/client'
import type { ToastFn } from '../../hooks/useToasts'
import { BACKFILL_MAX, DEFAULT_BACKFILL_COUNT, sanitizeBackfillCount } from '../../lib/subscriptions'
import { describeOptions } from '../../lib/options'
import type { BackfillMode, DownloadOptions } from '../../types/api'
import { useI18n } from '../../i18n'
import { Button } from '../ui/Button'
import { Segmented } from '../ui/Segmented'
import { EMPTY_FILTERS, SubscriptionFiltersFields } from './SubscriptionFiltersFields'

interface Props {
  /** The current "New download" settings; a new subscription starts from a copy of these. */
  options: DownloadOptions
  onAdded: () => void
  onToast: ToastFn
}

export function AddSubscriptionForm({ options, onAdded, onToast }: Props) {
  const { t } = useI18n()
  const [url, setUrl] = useState('')
  const [backfill, setBackfill] = useState<BackfillMode>('none')
  const [count, setCount] = useState(DEFAULT_BACKFILL_COUNT)
  const [busy, setBusy] = useState(false)
  const [filters, setFilters] = useState(EMPTY_FILTERS)
  const submitting = useRef(false)

  async function submit() {
    if (submitting.current) return
    const trimmed = url.trim()
    if (!trimmed) return onToast(t('Paste a channel or playlist link first'), true)
    submitting.current = true
    setBusy(true)
    try {
      await addSubscription(trimmed, options, backfill, sanitizeBackfillCount(count), filters)
      setUrl('')
      setFilters(EMPTY_FILTERS)
      onToast(`${t('Subscription added - checking it now')} (${describeOptions(options)})`)
      onAdded()
    } catch (e) {
      onToast(e instanceof Error ? e.message : t('Could not add the subscription'), true)
    } finally {
      submitting.current = false
      setBusy(false)
    }
  }

  return (
    <div className="grid gap-3">
      <div className="grid gap-2 sm:grid-cols-[1fr_auto]">
        <input
          className="field"
          placeholder={t('Channel or playlist link')}
          type="url"
          value={url}
          disabled={busy}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && void submit()}
        />
        <Button variant="primary" onClick={submit} disabled={busy}>
          {busy ? <Loader2 aria-hidden size={16} className="animate-spin" /> : <Plus aria-hidden size={16} />}
          {t('Add')}
        </Button>
      </div>
      <div className="flex flex-wrap items-center gap-3 text-xs text-zinc-400">
        <span>{t('When first added, download:')}</span>
        <Segmented
          label={t('Backfill')}
          value={backfill}
          onChange={setBackfill}
          options={[
            { value: 'none', label: t('Only new videos from now on') },
            { value: 'recent', label: t('Also a recent batch') },
          ]}
        />
        {backfill === 'recent' && (
          <label className="flex items-center gap-2">
            <span>{t('How many')}</span>
            <input
              type="number"
              min={1}
              max={BACKFILL_MAX}
              className="field !w-20 !py-1"
              value={count}
              onChange={(e) => setCount(sanitizeBackfillCount(e.target.value))}
            />
          </label>
        )}
      </div>
      <SubscriptionFiltersFields filters={filters} onChange={setFilters} />
      <p className="rounded-xl bg-white/[.035] px-3 py-2 text-xs text-zinc-300" aria-live="polite">
        {t('New subscriptions will download:')}{' '}
        <span className="font-medium text-zinc-100">{describeOptions(options)}</span>
        <span className="text-zinc-500">
          {' '}
          -{' '}
          {t(
            'taken from your current New download settings. You can change this per subscription after adding it.',
          )}
        </span>
      </p>
    </div>
  )
}
