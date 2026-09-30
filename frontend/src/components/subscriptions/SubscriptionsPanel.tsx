import type { ToastFn } from '../../hooks/useToasts'
import type { DownloadOptions, Subscription } from '../../types/api'
import { AddSubscriptionForm } from './AddSubscriptionForm'
import { SubscriptionCard } from './SubscriptionCard'
import { useI18n } from '../../i18n'

interface Props {
  options: DownloadOptions
  subscriptions: Subscription[]
  intervalSeconds: number
  onChanged: () => void
  onToast: ToastFn
}

export function SubscriptionsPanel({
  options,
  subscriptions = [],
  intervalSeconds,
  onChanged,
  onToast,
}: Props) {
  const { t } = useI18n()
  return (
    <section className="card grid content-start gap-4" aria-labelledby="subs-title">
      <div>
        <div className="eyebrow">{t('Auto-download')}</div>
        <h2 id="subs-title" className="mt-1 text-lg font-semibold">
          {t('Auto-download')}
          <span className="ml-2 text-sm font-normal text-zinc-400">
            {subscriptions.length > 0 &&
              t('{count}, checked every {minutes} min', {
                count: subscriptions.length,
                minutes: Math.round(intervalSeconds / 60),
              })}
          </span>
        </h2>
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
