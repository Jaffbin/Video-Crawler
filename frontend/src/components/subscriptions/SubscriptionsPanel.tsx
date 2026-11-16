import { useState } from 'react'
import { saveSubscriptionInterval } from '../../api/client'
import type { ToastFn } from '../../hooks/useToasts'
import type { DownloadOptions, Subscription } from '../../types/api'
import { AddSubscriptionForm } from './AddSubscriptionForm'
import { SubscriptionCard } from './SubscriptionCard'
import { useI18n } from '../../i18n'

interface Props {
  options: DownloadOptions
  subscriptions: Subscription[]
  intervalSeconds: number
  intervalChoices?: number[]
  onChanged: () => void
  onToast: ToastFn
}

export function SubscriptionsPanel({
  options,
  subscriptions = [],
  intervalSeconds,
  intervalChoices = [30, 60, 120, 360, 720, 1440],
  onChanged,
  onToast,
}: Props) {
  const { t } = useI18n()
  const [saving, setSaving] = useState(false)
  const minutes = Math.round(intervalSeconds / 60)
  const choices = intervalChoices.includes(minutes)
    ? intervalChoices
    : [...intervalChoices, minutes].sort((a, b) => a - b)

  async function changeInterval(value: number) {
    setSaving(true)
    try {
      await saveSubscriptionInterval(value)
      onChanged()
      onToast(t('Check frequency saved'))
    } catch (error) {
      onToast(t(error instanceof Error ? error.message : 'That did not work'), true)
    } finally {
      setSaving(false)
    }
  }
  return (
    <section className="card grid content-start gap-4" aria-labelledby="subs-title">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h2 id="subs-title" className="text-lg font-semibold">
          {t('Auto-download')}
          {subscriptions.length > 0 && (
            <span className="ml-2 text-sm font-normal text-zinc-400">{subscriptions.length}</span>
          )}
        </h2>
        <label className="control min-w-0 basis-44">
          <span>{t('Check for new videos every')}</span>
          <select
            className="field"
            value={minutes}
            disabled={saving}
            onChange={(event) => void changeInterval(Number(event.target.value))}
          >
            {choices.map((choice) => (
              <option key={choice} value={choice}>
                {choice < 60 ? t('{count} min', { count: choice }) : t('{count} h', { count: choice / 60 })}
              </option>
            ))}
          </select>
        </label>
      </div>

      <AddSubscriptionForm options={options} onAdded={onChanged} onToast={onToast} />

      {subscriptions.length === 0 ? (
        <p className="rounded-xl bg-white/[.025] px-4 py-6 text-center text-sm text-zinc-400">
          {t(
            'No subscriptions yet. Add a channel or playlist link above to have new videos download automatically.',
          )}
        </p>
      ) : (
        <ul className="grid gap-3">
          {subscriptions.map((sub) => (
            <SubscriptionCard key={sub.id} sub={sub} onChanged={onChanged} onToast={onToast} />
          ))}
        </ul>
      )}
    </section>
  )
}
