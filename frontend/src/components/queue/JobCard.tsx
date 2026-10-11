import {
  AlertTriangle,
  ChevronDown,
  Film,
  FolderOpen,
  Image as ImageIcon,
  Music,
  Play,
  RotateCcw,
  Trash2,
  X,
} from 'lucide-react'
import { useEffect, useId, useState } from 'react'
import {
  fileUrl,
  getLog,
  jobAction,
  openExternalUrl,
  openFile,
  openFolder,
  repairFile,
  retryWithBrowser,
} from '../../api/client'
import type { ToastFn } from '../../hooks/useToasts'
import { cn, formatDate } from '../../lib/utils'
import { displayFilename, fileKind } from '../../lib/library'
import { errorCopy } from '../../lib/errors'
import { Button } from '../ui/Button'
import { Modal } from '../ui/Modal'
import type { Job, JobStatus } from '../../types/api'
import { useI18n } from '../../i18n'

interface Props {
  onHelp?: () => void
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

export function JobCard({ job, windowMode, onChanged, onToast, onHelp }: Props) {
  const { t } = useI18n()
  const [logOpen, setLogOpen] = useState(false)
  const [log, setLog] = useState<string[]>([])
  const [loginOpen, setLoginOpen] = useState(false)
  const [browser, setBrowser] = useState('')
  const [actionBusy, setActionBusy] = useState(false)
  const logId = useId()
  const active = job.status === 'queued' || job.status === 'running'
  const canceling = job.stage === CANCELING
  const percent = job.status === 'done' ? 100 : Math.max(0, Math.min(100, job.percent))
  const fullBar = job.status !== 'running'
  const [errorTitle, errorHint] = errorCopy(job.error_kind)
  const playable = job.files.filter((file) => file.complete !== false)
  const primary = playable[0]
  const actionLabel = (file: { name: string }) =>
    fileKind(file) === 'image' ? 'View image' : fileKind(file) === 'audio' ? 'Play audio' : 'Play video'
  async function browserRetry() {
    setActionBusy(true)
    try {
      const result = await retryWithBrowser(job.id, browser)
      onToast(t(result.duplicates ? 'This download is already in the queue' : 'Added to the queue again'))
      setLoginOpen(false)
      onChanged()
    } catch (e) {
      report(e)
    } finally {
      setActionBusy(false)
    }
  }
  async function repair() {
    const file = job.files.find((item) => item.complete === false)
    if (!file) return
    setActionBusy(true)
    try {
      await repairFile(file.path)
      onToast(t('Repair added to Queue. Your original files are kept until it succeeds.'))
      onChanged()
    } catch (e) {
      report(e)
    } finally {
      setActionBusy(false)
    }
  }

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
      const result = await jobAction(job.id, action)
      if (result.duplicates) onToast(t('This download is already in the queue'))
      else if (message) onToast(message)
      onChanged()
    } catch (e) {
      onToast(e instanceof Error ? e.message : t('That did not work'), true)
    }
  }

  function formatItemProgress(item: string, running: boolean): string {
    if (!item) return ''

    const [current, total] = item.split('/')

    if (!total) {
      return running ? t('Item {current}', { current }) : t('{count} items', { count: current })
    }

    return running ? t('Item {current}/{total}', { current, total }) : t('{count} items', { count: total })
  }

  const report = (e: unknown) => onToast(e instanceof Error ? e.message : t('Could not open it'), true)
  const meta = [
    job.status === 'running'
      ? job.stage.startsWith('Reconnecting (')
        ? t('Reconnecting ({attempt}/2)', { attempt: job.stage.match(/\((\d+)/)?.[1] || '1' })
        : job.stage
      : '',
    job.status === 'queued' ? t('Waiting in the queue') : '',
    job.stage === 'Last incomplete' ? t('Interrupted last time') : '',
    job.stage === 'Restored queue' ? t('Restored after restart') : '',
    formatItemProgress(job.item, job.status === 'running'),
    job.speed,
    job.eta ? t('{eta} left', { eta: job.eta }) : '',
    !active && job.finished ? formatDate(job.finished) : '',
  ].filter(Boolean)

  return (
    <article
      className="relative overflow-hidden rounded-2xl border border-white/[.07] bg-white/[.02]"
      aria-label={job.title || job.url}
    >
      <div
        role="progressbar"
        aria-label={`${t(LABEL[job.status])} ${job.title || job.url}`}
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
            {job.mode === 'mp3' || job.mode === 'original' ? (
              <Music size={17} />
            ) : job.mode === 'cover' || job.mode === 'image' ? (
              <ImageIcon size={17} />
            ) : (
              <Film size={17} />
            )}
          </div>
          <div className="min-w-0 flex-1">
            <h3 className="truncate text-sm font-medium" title={job.url}>
              {job.title || job.url}
            </h3>
            <p className="mt-0.5 text-xs text-zinc-400">{meta.join(' · ')}</p>
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
              {job.status === 'running' ? `${Math.round(percent)}%` : t(LABEL[job.status])}
            </div>
          </div>
        </div>

        {job.status === 'error' && job.error && (
          <div
            role="alert"
            className="flex gap-2 rounded-xl bg-red-500/[.08] px-3 py-2 text-xs leading-5 text-red-200"
          >
            <AlertTriangle aria-hidden size={14} className="mt-0.5 shrink-0" />
            <div>
              <div className="font-medium">{t(errorTitle)}</div>
              <div className="mt-1 text-red-100/75">{t(errorHint)}</div>
              <div className="mt-2 flex flex-wrap gap-2">
                {onHelp &&
                  ['ffmpeg', 'javascript', 'impersonation_missing', 'app_control'].includes(
                    job.error_kind || '',
                  ) && <Button onClick={onHelp}>{t('Resolve setup issue')}</Button>}
                {['login', 'cookies_expired', 'cookies_locked', 'forbidden'].includes(
                  job.error_kind || '',
                ) && (
                  <Button disabled={actionBusy} onClick={() => setLoginOpen(true)}>
                    {t('Use browser sign-in')}
                  </Button>
                )}
                {['disk_full', 'file_locked', 'file_permission'].includes(job.error_kind || '') && (
                  <Button onClick={() => openFolder().catch(report)}>{t('Open download folder')}</Button>
                )}
                {job.files.some((file) => file.complete === false) && (
                  <Button disabled={actionBusy} onClick={repair}>
                    {t('Repair downloaded files')}
                  </Button>
                )}
                <button className="action-btn" onClick={() => openExternalUrl(job.url).catch(report)}>
                  {t('Open original page')}
                </button>
              </div>
            </div>
          </div>
        )}
        {job.notes.length > 0 && (
          <ul className="grid gap-1 text-xs leading-5 text-amber-200">
            {job.notes.map((note) => (
              <li key={note}>
                {t('Note')}: {note}
              </li>
            ))}
          </ul>
        )}
        {!!job.failed_items?.length && job.status === 'error' && (
          <details className="text-xs text-red-200">
            <summary>{t('{count} failed items', { count: job.failed_items.length })}</summary>
            <ul className="mt-2 grid gap-2">
              {job.failed_items.map((item, index) => (
                <li key={`${item.index}-${item.url}-${index}`}>
                  <p>
                    {item.index ? `${item.index}. ` : ''}
                    {item.title || item.url}
                  </p>
                  <p className="break-all text-zinc-400">{item.error}</p>
                </li>
              ))}
            </ul>
          </details>
        )}

        {job.files.length > 0 && (
          <ul className="grid gap-1">
            {job.files.map((file) => (
              <li key={file.path} className="flex items-center gap-2 text-sm">
                <span
                  className={`min-w-0 flex-1 truncate ${file.complete === false ? 'text-amber-300' : 'text-emerald-300'}`}
                  title={file.name}
                >
                  {displayFilename(file.name)}
                </span>
                {file.complete === false && (
                  <span className="text-xs text-amber-300">{t('Processing incomplete')}</span>
                )}
                {(job.status !== 'done' || file.path !== primary?.path) &&
                  (windowMode ? (
                    <button
                      type="button"
                      className="action-btn"
                      onClick={() => openFile(file.path).catch(report)}
                    >
                      <Play aria-hidden size={13} /> {t(file.complete === false ? 'Open' : actionLabel(file))}
                    </button>
                  ) : (
                    <a className="action-btn" href={fileUrl(file.path)} target="_blank" rel="noreferrer">
                      <Play aria-hidden size={13} /> {t(file.complete === false ? 'Open' : actionLabel(file))}
                    </a>
                  ))}
              </li>
            ))}
          </ul>
        )}

        {job.status === 'done' && primary && (
          <div className="flex flex-wrap items-center gap-2 rounded-xl bg-emerald-500/10 p-3">
            <span className="mr-auto text-sm text-emerald-200">{t('Your download is ready.')}</span>
            {windowMode ? (
              <Button variant="primary" onClick={() => openFile(primary.path).catch(report)}>
                {t(actionLabel(primary))}
              </Button>
            ) : (
              <a
                className="rounded-xl bg-white px-3 py-2 text-sm font-medium text-zinc-950"
                href={fileUrl(primary.path)}
                target="_blank"
                rel="noreferrer"
              >
                {t(actionLabel(primary))}
              </a>
            )}
            <Button onClick={() => openFolder(primary.path).catch(report)}>
              <FolderOpen aria-hidden size={14} />
              {t('Show in folder')}
            </Button>
          </div>
        )}

        <div className="flex flex-wrap items-center justify-between gap-2">
          <button
            type="button"
            className="action-btn"
            aria-expanded={logOpen}
            aria-controls={logId}
            onClick={() => setLogOpen(!logOpen)}
          >
            <ChevronDown aria-hidden size={13} className={logOpen ? 'rotate-180' : ''} /> {t('Log')}
          </button>
          <div className="flex flex-wrap gap-1">
            {active && (
              <button type="button" className="action-btn" disabled={canceling} onClick={() => run('cancel')}>
                <X aria-hidden size={13} /> {canceling ? t('Canceling…') : t('Cancel')}
              </button>
            )}
            {(job.status === 'error' || job.status === 'canceled') && (
              <button
                type="button"
                className="action-btn"
                onClick={() => run('retry', t('Added to the queue again'))}
              >
                <RotateCcw aria-hidden size={13} />{' '}
                {t(job.status === 'error' && job.retry_failed_only ? 'Retry failed items' : 'Retry')}
              </button>
            )}
            {job.status === 'done' && job.files.length > 0 && !primary && (
              <button
                type="button"
                className="action-btn"
                onClick={() => openFolder(job.files[0].path).catch(report)}
              >
                <FolderOpen aria-hidden size={13} /> {t('Show in folder')}
              </button>
            )}
            {!active && (
              <button type="button" className="action-btn" onClick={() => run('remove')}>
                <Trash2 aria-hidden size={13} /> {t('Remove')}
              </button>
            )}
          </div>
        </div>

        {logOpen && (
          <pre
            id={logId}
            className="max-h-56 overflow-auto whitespace-pre-wrap break-all rounded-xl bg-black/40 p-3 font-mono text-xs leading-5 text-zinc-300"
          >
            {job.error && `${job.error}\n`}
            {log.length ? log.join('\n') : t('No log lines yet.')}
          </pre>
        )}
        <Modal
          open={loginOpen}
          title={t('Use browser sign-in')}
          onClose={() => {
            if (!actionBusy) setLoginOpen(false)
          }}
        >
          <div className="grid gap-4 text-sm">
            <p>
              {t(
                'Sign in to the source site in your browser, then select that browser here. Close it completely if reading the session fails.',
              )}
            </p>
            <p className="text-xs text-zinc-400">
              {t(
                'Only after you confirm, the app uses that browser’s sign-in session to access the source site.',
              )}
            </p>
            <Button onClick={() => openExternalUrl(job.url).catch(report)}>{t('Open original page')}</Button>
            <label className="control">
              <span>{t('Browser you signed in with')}</span>
              <select className="field" value={browser} onChange={(e) => setBrowser(e.target.value)}>
                <option value="">{t('Choose a browser')}</option>
                {['edge', 'chrome', 'firefox', 'brave', 'opera', 'vivaldi', 'safari'].map((name) => (
                  <option key={name} value={name}>
                    {name[0].toUpperCase() + name.slice(1)}
                  </option>
                ))}
              </select>
            </label>
            <div className="flex justify-end gap-2">
              <Button disabled={actionBusy} onClick={() => setLoginOpen(false)}>
                {t('Cancel')}
              </Button>
              <Button variant="primary" disabled={!browser || actionBusy} onClick={browserRetry}>
                {t('Use this browser and retry')}
              </Button>
            </div>
          </div>
        </Modal>
      </div>
    </article>
  )
}
