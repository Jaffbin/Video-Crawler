import { useEffect, useState } from 'react'
import { useI18n } from '../../i18n'
import type { SubscriptionFilters } from '../../types/api'

export const EMPTY_FILTERS: SubscriptionFilters = {
  include_keywords: [],
  exclude_keywords: [],
  exclude_live: false,
  exclude_shorts: false,
  min_duration: 0,
  max_duration: 0,
}

export function normalizeFilters(filters?: Partial<SubscriptionFilters>): SubscriptionFilters {
  return { ...EMPTY_FILTERS, ...filters }
}

const splitKeywords = (value: string) =>
  value
    .split(/[,\n]/)
    .map((word) => word.trim())
    .filter(Boolean)
    .slice(0, 20)

function KeywordInput({
  value,
  placeholder,
  onChange,
}: {
  value: string[]
  placeholder: string
  onChange: (value: string[]) => void
}) {
  const [text, setText] = useState(value.join(', '))
  useEffect(() => setText(value.join(', ')), [value])
  return (
    <input
      className="field"
      value={text}
      placeholder={placeholder}
      onChange={(event) => setText(event.target.value)}
      onBlur={() => onChange(splitKeywords(text))}
    />
  )
}

export function SubscriptionFiltersFields({
  filters,
  onChange,
}: {
  filters: SubscriptionFilters
  onChange: (filters: SubscriptionFilters) => void
}) {
  const { t } = useI18n()
  const patch = (change: Partial<SubscriptionFilters>) => onChange({ ...filters, ...change })
  const minutes = (seconds: number) => (seconds ? Math.round(seconds / 60) : '')
  const seconds = (value: string) => Math.max(0, Math.round((Number(value) || 0) * 60))

  return (
    <fieldset className="grid gap-3 rounded-xl border border-white/[.06] p-3">
      <legend className="px-1 text-xs font-medium text-zinc-300">{t('Filters (optional)')}</legend>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="control">
          <span>{t('Title must contain')}</span>
          <KeywordInput
            value={filters.include_keywords}
            placeholder={t('Comma-separated keywords; any match is accepted')}
            onChange={(value) => patch({ include_keywords: value })}
          />
        </label>
        <label className="control">
          <span>{t('Title must not contain')}</span>
          <KeywordInput
            value={filters.exclude_keywords}
            placeholder={t('Comma-separated keywords')}
            onChange={(value) => patch({ exclude_keywords: value })}
          />
        </label>
        <label className="control">
          <span>{t('Minimum duration (minutes)')}</span>
          <input
            className="field"
            type="number"
            min="0"
            max="10080"
            value={minutes(filters.min_duration)}
            onChange={(event) => patch({ min_duration: seconds(event.target.value) })}
          />
        </label>
        <label className="control">
          <span>{t('Maximum duration (minutes)')}</span>
          <input
            className="field"
            type="number"
            min="0"
            max="10080"
            value={minutes(filters.max_duration)}
            onChange={(event) => patch({ max_duration: seconds(event.target.value) })}
          />
        </label>
      </div>
      <div className="flex flex-wrap gap-2">
        <label className="toggle-row">
          <input
            type="checkbox"
            checked={filters.exclude_live}
            onChange={(event) => patch({ exclude_live: event.target.checked })}
          />
          {t('Exclude live videos')}
        </label>
        <label className="toggle-row">
          <input
            type="checkbox"
            checked={filters.exclude_shorts}
            onChange={(event) => patch({ exclude_shorts: event.target.checked })}
          />
          {t('Exclude Shorts')}
        </label>
      </div>
      <p className="text-[11px] text-zinc-500">
        {t('Duration filters apply only when the site reports a duration.')}
      </p>
    </fieldset>
  )
}
