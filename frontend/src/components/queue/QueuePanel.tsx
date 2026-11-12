import { ArrowDown, ArrowUp, Pause, Play, Search } from 'lucide-react'
import { useMemo, useState } from 'react'
import { batchJobs, clearJobs, moveJob, pauseQueue } from '../../api/client'
import type { ToastFn } from '../../hooks/useToasts'
import type { Job } from '../../types/api'
import { Button } from '../ui/Button'
import { JobCard } from './JobCard'
import { useI18n } from '../../i18n'
import { SelectionScope } from '../ui/SelectionScope'

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

export function orderJobs(jobs: Job[], pending: string[]): Job[] {
  const positions = new Map(pending.map((id, index) => [id, index]))
  const rank = (job: Job) => (job.status === 'running' ? 0 : job.status === 'queued' ? 1 : 2)
  return [...jobs].sort(
    (a, b) =>
      rank(a) - rank(b) ||
      (a.status === 'queued'
        ? (positions.get(a.id) ?? Number.MAX_SAFE_INTEGER) - (positions.get(b.id) ?? Number.MAX_SAFE_INTEGER)
        : b.created - a.created),
  )
}

interface Props {
  onHelp?: () => void
  jobs: Job[]
  windowMode: boolean
  onChanged: () => void
  onToast: ToastFn
  queuePaused?: boolean
  queueOrder?: string[]
  onNewDownload?: () => void
}

export function QueuePanel({
  onHelp,
  jobs,
  windowMode,
  onChanged,
  onToast,
  queuePaused = false,
  queueOrder = [],
  onNewDownload,
}: Props) {
  const { t } = useI18n()
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<Filter>('all')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [busy, setBusy] = useState(false)
  const shown = useMemo(
    () => orderJobs(jobs, queueOrder).filter((j) => matchesFilter(j, filter) && matchesSearch(j, query)),
    [jobs, queueOrder, filter, query],
  )
  const selectedJobs = jobs.filter((job) => selected.has(job.id))
  const allShownSelected = shown.length > 0 && shown.every((job) => selected.has(job.id))

  async function control(action: () => Promise<unknown>) {
    setBusy(true)
    try {
      await action()
      onChanged()
    } catch (e) {
      onToast(e instanceof Error ? e.message : t('That did not work'), true)
    } finally {
      setBusy(false)
    }
  }

  async function runBatch(action: 'cancel' | 'retry' | 'remove') {
    await control(async () => {
      const result = await batchJobs(
        selectedJobs.map((job) => job.id),
        action,
      )
      onToast(
        t('Updated {count} tasks; skipped {skipped}.', {
          count: result.processed.length,
          skipped: result.skipped.length,
        }),
      )
      setSelected(new Set())
    })
  }
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
    <section
      className="queue-panel card grid min-w-0 grid-cols-1 content-start gap-4"
      aria-labelledby="queue-title"
    >
      <div className="panel-toolbar">
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
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <Button disabled={busy} onClick={() => control(() => pauseQueue(!queuePaused))}>
              {queuePaused ? <Play aria-hidden size={14} /> : <Pause aria-hidden size={14} />}
              {t(queuePaused ? 'Resume queue' : 'Pause queue')}
            </Button>
            {successRate !== null && (
              <div
                className="rounded-xl bg-emerald-500/[.08] px-3 py-1.5 text-xs text-emerald-200"
                title={t('Calculated from completed and failed downloads; canceled jobs are excluded.')}
              >
                {t('Success rate')}: <strong>{successRate}%</strong> ({succeeded}/{measured})
              </div>
            )}
            <Button onClick={clear} disabled={!finished}>
              {t('Clear finished')}
            </Button>
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          <label className="relative min-w-0 flex-1 basis-48">
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
      </div>
      {queuePaused && (
        <p role="status" className="rounded-xl bg-amber-500/10 p-3 text-xs text-amber-200">
          {t('Queue paused. Running downloads continue; waiting tasks start when you resume.')}
        </p>
      )}

      {(shown.length > 0 || selectedJobs.length > 0) && (
        <div className="flex flex-wrap items-center gap-3 rounded-xl bg-white/[.025] px-3 py-2 text-xs">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              disabled={!shown.length || busy}
              checked={allShownSelected}
              onChange={() =>
                setSelected((previous) => {
                  const next = new Set(previous)
                  for (const job of shown) allShownSelected ? next.delete(job.id) : next.add(job.id)
                  return next
                })
              }
            />
            {t('Select visible')}
          </label>
          <span className="text-zinc-400">{t('{count} selected', { count: selectedJobs.length })}</span>
          <SelectionScope
            items={selectedJobs.map((job) => ({ key: job.id, label: job.title || job.url }))}
            visible={shown.map((job) => job.id)}
            disabled={busy}
            onClear={() => setSelected(new Set())}
            onRemove={(id) => setSelected((previous) => new Set([...previous].filter((item) => item !== id)))}
          />
          <Button
            disabled={busy || !selectedJobs.some((job) => ['queued', 'running'].includes(job.status))}
            onClick={() => runBatch('cancel')}
          >
            {t('Cancel selected')}
          </Button>
          <Button
            disabled={busy || !selectedJobs.some((job) => ['error', 'canceled'].includes(job.status))}
            onClick={() => runBatch('retry')}
          >
            {t('Retry selected')}
          </Button>
          <Button
            disabled={busy || !selectedJobs.some((job) => ['done', 'error', 'canceled'].includes(job.status))}
            onClick={() => runBatch('remove')}
          >
            {t('Remove selected')}
          </Button>
        </div>
      )}

      {jobs.length === 0 ? (
        <div className="grid justify-items-center gap-3 rounded-xl bg-white/[.025] px-4 py-8 text-center text-sm text-zinc-400">
          <p>{t('The queue is empty. Open New download to add a link.')}</p>
          {onNewDownload && <Button onClick={onNewDownload}>{t('Paste a link')}</Button>}
        </div>
      ) : shown.length === 0 ? (
        <p className="rounded-xl bg-white/[.025] px-4 py-8 text-center text-sm text-zinc-400">
          {t('No downloads match.')}
        </p>
      ) : (
        <div className="grid min-w-0 grid-cols-1 gap-3">
          {shown.map((job) => (
            <div key={job.id} className="flex min-w-0 items-start gap-2">
              <input
                type="checkbox"
                className="mt-5 shrink-0"
                checked={selected.has(job.id)}
                aria-label={t('Select {name}', { name: job.title || job.url })}
                onChange={() =>
                  setSelected((previous) => {
                    const next = new Set(previous)
                    next.has(job.id) ? next.delete(job.id) : next.add(job.id)
                    return next
                  })
                }
              />
              <div className="grid min-w-0 flex-1 grid-cols-1 gap-1">
                {job.status === 'queued' && (
                  <div className="flex items-center gap-2 text-xs text-zinc-400">
                    <span className="min-w-0 flex-1">
                      {t('Waiting position: {count}', { count: queueOrder.indexOf(job.id) + 1 })}
                    </span>
                    <button
                      className="action-btn"
                      disabled={busy || queueOrder.indexOf(job.id) <= 0}
                      aria-label={t('Move up')}
                      onClick={() => control(() => moveJob(job.id, 'up'))}
                    >
                      <ArrowUp size={14} />
                    </button>
                    <button
                      className="action-btn"
                      disabled={
                        busy ||
                        queueOrder.indexOf(job.id) < 0 ||
                        queueOrder.indexOf(job.id) >= queueOrder.length - 1
                      }
                      aria-label={t('Move down')}
                      onClick={() => control(() => moveJob(job.id, 'down'))}
                    >
                      <ArrowDown size={14} />
                    </button>
                  </div>
                )}
                <JobCard
                  job={job}
                  windowMode={windowMode}
                  onChanged={onChanged}
                  onToast={onToast}
                  onHelp={onHelp}
                />
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
