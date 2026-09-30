import { Search } from 'lucide-react'
import { useMemo, useState } from 'react'
import { clearJobs } from '../../api/client'
import type { ToastFn } from '../../hooks/useToasts'
import type { Job } from '../../types/api'
import { Button } from '../ui/Button'
import { JobCard } from './JobCard'
import { useI18n } from '../../i18n'

type Filter = 'all' | 'active' | 'done' | 'failed'

const FILTERS: Filter[] = ['all', 'active', 'done', 'failed']

export function matchesFilter(job: Job, filter: Filter): boolean {
  if (filter === 'active') return job.status === 'queued' || job.status === 'running'
  if (filter === 'done') return job.status === 'done'
  if (filter === 'failed') return job.status === 'error' || job.status === 'canceled'
  return true
}

export function matchesSearch(job: Job, query: string): boolean {
  const q = query.trim().toLowerCase()
  return !q || job.title.toLowerCase().includes(q) || job.url.toLowerCase().includes(q)
}

export function successStats(jobs: Job[]) {
  const succeeded = jobs.filter((job) => job.status === 'done').length
  const failed = jobs.filter((job) => job.status === 'error').length
  const measured = succeeded + failed
  return { succeeded, measured, rate: measured ? Math.round((succeeded / measured) * 100) : null }
}

interface Props {
  jobs: Job[]
  windowMode: boolean
  onChanged: () => void
  onToast: ToastFn
}

export function QueuePanel({ jobs, windowMode, onChanged, onToast }: Props) {
  const { t } = useI18n()
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<Filter>('all')
  const shown = useMemo(
    () => jobs.filter((j) => matchesFilter(j, filter) && matchesSearch(j, query)),
    [jobs, filter, query],
  )
  const finished = jobs.filter(
    (j) => j.status === 'done' || j.status === 'error' || j.status === 'canceled',
  ).length
  const { succeeded, measured, rate: successRate } = successStats(jobs)

  async function clear() {
    try {
      await clearJobs()
      onChanged()
    } catch (e) {
      onToast(e instanceof Error ? e.message : t('Could not clear the list'), true)
    }
  }

  return (
    <section className="card grid content-start gap-4" aria-labelledby="queue-title">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="eyebrow">{t('Queue')}</div>
          <h2 id="queue-title" className="mt-1 text-lg font-semibold">
            {t('Downloads')}
            <span className="ml-2 text-sm font-normal text-zinc-400">
              {jobs.length === shown.length ? `${jobs.length}` : `${shown.length} of ${jobs.length}`}
            </span>
          </h2>
        </div>
        <div className="flex items-center gap-2">
          {successRate !== null && (
            <div
              className="rounded-xl bg-emerald-500/[.08] px-3 py-1.5 text-xs text-emerald-200"
              title={t('Calculated from completed and failed downloads; canceled jobs are excluded.')}
            >
              {t('Success rate')}: <strong>{successRate}%</strong> ({succeeded}/{measured})
            </div>
          )}
          <Button variant="ghost" onClick={clear} disabled={!finished}>
            {t('Clear finished')}
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        <label className="relative min-w-48 flex-1">
          <span className="sr-only">{t('Search downloads')}</span>
          <Search
            aria-hidden
            size={15}
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500"
          />
          <input
            className="field !pl-9"
            type="search"
            placeholder={t('Search title or link')}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <div className="segmented" role="radiogroup" aria-label={t('Filter by status')}>
          {FILTERS.map((f) => (
            <button
              key={f}
              type="button"
              role="radio"
              aria-checked={filter === f}
              onClick={() => setFilter(f)}
            >
              {t(f === 'all' ? 'All' : f === 'active' ? 'Active' : f === 'done' ? 'Done' : 'Failed')}
            </button>
          ))}
        </div>
      </div>

      {jobs.length === 0 ? (
        <p className="rounded-xl bg-white/[.025] px-4 py-8 text-center text-sm text-zinc-400">
          {t('The queue is empty. Open New download to add a link.')}
        </p>
      ) : shown.length === 0 ? (
        <p className="rounded-xl bg-white/[.025] px-4 py-8 text-center text-sm text-zinc-400">
          {t('No downloads match.')}
        </p>
      ) : (
        <div className="grid gap-3">
          {shown.map((job) => (
            <JobCard key={job.id} job={job} windowMode={windowMode} onChanged={onChanged} onToast={onToast} />
          ))}
        </div>
      )}
    </section>
  )
}
