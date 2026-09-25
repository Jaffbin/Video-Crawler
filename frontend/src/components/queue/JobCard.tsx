import { AlertTriangle, ChevronDown, Film, FolderOpen, Music, Play, RotateCcw, Trash2, X } from 'lucide-react'
import { useEffect, useId, useState } from 'react'
import { fileUrl, getLog, jobAction, openFile, openFolder } from '../../api/client'
import type { ToastFn } from '../../hooks/useToasts'
import { cn, formatDate } from '../../lib/utils'
import type { Job, JobStatus } from '../../types/api'

interface Props {
  job: Job
  /** In the desktop window a link to /files cannot open a player, so files are opened by the backend. */
  windowMode: boolean
  onChanged: () => void
  onToast: ToastFn
}

const BAR: Record<JobStatus, string> = {
  queued: 'bg-zinc-500/40',
  running: 'bg-sky-400/70',
  done: 'bg-emerald-400/70',
  error: 'bg-red-400/60',
  canceled: 'bg-zinc-500/40',
}

const LABEL: Record<JobStatus, string> = {
  queued: 'Queued',
  running: 'Downloading',
  done: 'Done',
  error: 'Failed',
  canceled: 'Canceled',
}

const CANCELING = 'Canceling…'

export function JobCard({ job, windowMode, onChanged, onToast }: Props) {
  const [logOpen, setLogOpen] = useState(false)
  const [log, setLog] = useState<string[]>([])
  const logId = useId()
  const active = job.status === 'queued' || job.status === 'running'
  const canceling = job.stage === CANCELING
  const percent = job.status === 'done' ? 100 : Math.max(0, Math.min(100, job.percent))
  const fullBar = job.status !== 'running'

  useEffect(() => {
    if (!logOpen) return
    let stop = false
    const load = async () => {
      try {
        const { lines } = await getLog(job.id)
        if (!stop) setLog(lines)
      } catch {
        /* the log is a convenience */
      }
    }
    void load()
    if (job.status !== 'running' && job.status !== 'queued') return
    const timer = window.setInterval(load, 1500)
    return () => {
      stop = true
      window.clearInterval(timer)
    }
  }, [logOpen, job.id])

  async function run(action: 'cancel' | 'retry' | 'remove', message?: string) {
    try {
      await jobAction(job.id, action)
      if (message) onToast(message)
      onChanged()
    } catch (e) {
      onToast(e instanceof Error ? e.message : 'That did not work', true)
    }
  }

  function formatItemProgress(item: string, running: boolean): string {
    if (!item) return ''

    const [current, total] = item.split('/')

    if (!total) {
      return running ? `Item ${current}` : `${current} items`
    }

    return running
      ? `Item ${current}/${total}`
      : `${total} items`
  }

  const report = (e: unknown) => onToast(e instanceof Error ? e.message : 'Could not open it', true)
  const meta = [
    job.status === 'running' ? job.stage : '',
    job.status === 'queued' ? 'Waiting in the queue' : '',
    job.stage === 'Last incomplete' ? 'Interrupted last time' : '',
    formatItemProgress(job.item, job.status === 'running'),
    job.speed,
    job.eta ? `${job.eta} left` : '',
    !active && job.finished ? formatDate(job.finished) : '',
  ].filter(Boolean)

  return (
    <article
      className="relative overflow-hidden rounded-2xl border border-white/[.07] bg-white/[.02]"
      aria-label={job.title || job.url}
    >
      <div
        role="progressbar"
        aria-label={`${LABEL[job.status]} ${job.title || job.url}`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(percent)}
        className={cn(
          'absolute inset-y-0 left-0 opacity-[.13] transition-[width] duration-700',
          BAR[job.status],
        )}
        style={{ width: `${fullBar ? 100 : percent}%` }}
      />
      <div className="relative grid gap-3 p-4">
        <div className="flex items-start gap-3">
          <div
            aria-hidden
            className="mt-0.5 grid size-9 shrink-0 place-items-center rounded-xl bg-white/[.06] text-zinc-300"
          >
            {job.mode === 'mp3' ? <Music size={17} /> : <Film size={17} />}
          </div>
          <div className="min-w-0 flex-1">
            <h3 className="truncate text-sm font-medium" title={job.url}>
              {job.title || job.url}
            </h3>
            <p className="mt-0.5 text-xs text-zinc-400">{meta.join('   ')}</p>
          </div>
          <div className="text-right">
            <div
              className={cn(
                'text-xl font-semibold tabular-nums',
                job.status === 'done' && 'text-emerald-300',
                job.status === 'error' && 'text-red-300',
                (job.status === 'queued' || job.status === 'canceled') && 'text-sm text-zinc-400',
              )}
            >
              {job.status === 'running' ? `${Math.round(percent)}%` : LABEL[job.status]}
            </div>
          </div>
        </div>

        {job.status === 'error' && job.error && (
          <p
            role="alert"
            className="flex gap-2 rounded-xl bg-red-500/[.08] px-3 py-2 text-xs leading-5 text-red-200"
          >
            <AlertTriangle aria-hidden size={14} className="mt-0.5 shrink-0" />
            {job.error}
          </p>
        )}
        {job.notes.length > 0 && (
          <ul className="grid gap-1 text-xs leading-5 text-amber-200">
            {job.notes.map((note) => (
              <li key={note}>Note: {note}</li>
            ))}
          </ul>
        )}

        {job.files.length > 0 && (
          <ul className="grid gap-1">
            {job.files.map((file) => (
              <li key={file.path} className="flex items-center gap-2 text-sm">
                <span className="min-w-0 flex-1 truncate text-emerald-300" title={file.name}>
                  {file.name}
                </span>
                {windowMode ? (
                  <button
                    type="button"
                    className="action-btn"
                    onClick={() => openFile(file.path).catch(report)}
                  >
                    <Play aria-hidden size={13} /> Open
                  </button>
                ) : (
                  <a className="action-btn" href={fileUrl(file.path)} target="_blank" rel="noreferrer">
                    <Play aria-hidden size={13} /> Play
                  </a>
                )}
              </li>
            ))}
          </ul>
        )}

        <div className="flex flex-wrap items-center justify-between gap-2">
          <button
            type="button"
            className="action-btn"
            aria-expanded={logOpen}
            aria-controls={logId}
            onClick={() => setLogOpen(!logOpen)}
          >
            <ChevronDown aria-hidden size={13} className={logOpen ? 'rotate-180' : ''} /> Log
          </button>
          <div className="flex flex-wrap gap-1">
            {active && (
              <button type="button" className="action-btn" disabled={canceling} onClick={() => run('cancel')}>
                <X aria-hidden size={13} /> {canceling ? 'Canceling…' : 'Cancel'}
              </button>
            )}
            {(job.status === 'error' || job.status === 'canceled') && (
              <button
                type="button"
                className="action-btn"
                onClick={() => run('retry', 'Added to the queue again')}
              >
                <RotateCcw aria-hidden size={13} /> Retry
              </button>
            )}
            {job.status === 'done' && job.files.length > 0 && (
              <button
                type="button"
                className="action-btn"
                onClick={() => openFolder(job.files[0].path).catch(report)}
              >
                <FolderOpen aria-hidden size={13} /> Show in folder
              </button>
            )}
            {!active && (
              <button type="button" className="action-btn" onClick={() => run('remove')}>
                <Trash2 aria-hidden size={13} /> Remove
              </button>
            )}
          </div>
        </div>

        {logOpen && (
          <pre
            id={logId}
            className="max-h-56 overflow-auto whitespace-pre-wrap break-all rounded-xl bg-black/40 p-3 font-mono text-xs leading-5 text-zinc-300"
          >
            {log.length ? log.join('\n') : 'No log lines yet.'}
          </pre>
        )}
      </div>
    </article>
  )
}
