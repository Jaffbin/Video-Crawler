import { Search } from 'lucide-react'
import { useMemo, useState } from 'react'
import { clearJobs } from '../../api/client'
import type { ToastFn } from '../../hooks/useToasts'
import type { Job } from '../../types/api'
import { Button } from '../ui/Button'
import { JobCard } from './JobCard'

type Filter = 'all' | 'active' | 'done' | 'failed'

const FILTERS: { value: Filter; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'active', label: 'Active' },
  { value: 'done', label: 'Done' },
  { value: 'failed', label: 'Failed' },
]

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

interface Props {
  jobs: Job[]
  windowMode: boolean
  onChanged: () => void
  onToast: ToastFn
}

export function QueuePanel({ jobs, windowMode, onChanged, onToast }: Props) {
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<Filter>('all')
  const shown = useMemo(
    () => jobs.filter((j) => matchesFilter(j, filter) && matchesSearch(j, query)),
    [jobs, filter, query],
  )
  const finished = jobs.filter(
    (j) => j.status === 'done' || j.status === 'error' || j.status === 'canceled',
  ).length

  async function clear() {
    try {
      await clearJobs()
      onChanged()
    } catch (e) {
      onToast(e instanceof Error ? e.message : 'Could not clear the list', true)
    }
  }

  return (
    <section className="card grid content-start gap-4" aria-labelledby="queue-title">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="eyebrow">Queue</div>
          <h2 id="queue-title" className="mt-1 text-lg font-semibold">
            Downloads
            <span className="ml-2 text-sm font-normal text-zinc-400">
              {jobs.length === shown.length ? `${jobs.length}` : `${shown.length} of ${jobs.length}`}
            </span>
          </h2>
        </div>
        <Button variant="ghost" onClick={clear} disabled={!finished}>
          Clear finished
        </Button>
      </div>

      <div className="flex flex-wrap gap-2">
        <label className="relative min-w-48 flex-1">
          <span className="sr-only">Search downloads</span>
          <Search
            aria-hidden
            size={15}
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500"
          />
          <input
            className="field !pl-9"
            type="search"
            placeholder="Search title or link"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <div className="segmented" role="radiogroup" aria-label="Filter by status">
          {FILTERS.map((f) => (
            <button
              key={f.value}
              type="button"
              role="radio"
              aria-checked={filter === f.value}
              onClick={() => setFilter(f.value)}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {jobs.length === 0 ? (
        <p className="rounded-xl bg-white/[.025] px-4 py-8 text-center text-sm text-zinc-400">
          The queue is empty. Paste a link on the left and press Start download.
        </p>
      ) : shown.length === 0 ? (
        <p className="rounded-xl bg-white/[.025] px-4 py-8 text-center text-sm text-zinc-400">
          No downloads match.
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
