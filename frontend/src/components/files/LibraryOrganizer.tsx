import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { getLibraryCheck, libraryCheckAction, openFolder, recycleCheckedDuplicates } from '../../api/client'
import { useI18n } from '../../i18n'
import { formatBytes, formatDate } from '../../lib/utils'
import type { LibraryBatchResult, LibraryCheck } from '../../types/api'
import { Button } from '../ui/Button'
import { Modal } from '../ui/Modal'

function Pages({
  count,
  size,
  page,
  setPage,
}: {
  count: number
  size: number
  page: number
  setPage: (value: number) => void
}) {
  const { t } = useI18n()
  if (count <= size) return null
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      <Button disabled={page === 0} onClick={() => setPage(page - 1)}>
        {t('Previous')}
      </Button>
      <span>
        {page + 1} / {Math.ceil(count / size)}
      </span>
      <Button disabled={(page + 1) * size >= count} onClick={() => setPage(page + 1)}>
        {t('Next')}
      </Button>
    </div>
  )
}

function Findings({
  items,
  title,
  children,
}: {
  items: Array<{ path: string; title?: string; reason?: string }>
  title: string
  children?: ReactNode
}) {
  const { t } = useI18n()
  const [page, setPage] = useState(0)
  const current = Math.min(page, Math.max(0, Math.ceil(items.length / 20) - 1))
  const reasons: Record<string, string> = {
    unreadable: 'Cannot access this path',
    linked: 'Linked path skipped',
    incomplete: 'Inventory incomplete; availability unknown',
    changed: 'File changed or was not fully checked',
    shared: 'Same file referenced more than once',
    incomplete_file: 'Processing incomplete',
    recovery_record: 'This path has a Recovery record. Review Recovery before organizing it.',
  }
  return (
    <section className="grid min-w-0 gap-2 rounded-xl border border-white/10 p-3" aria-label={title}>
      <h3 className="font-semibold">
        {title} · {items.length}
      </h3>
      {children}
      {!items.length && <p className="text-sm text-zinc-400">{t('No findings in this check.')}</p>}
      <ul className="grid gap-2 text-sm">
        {items.slice(current * 20, (current + 1) * 20).map((item) => (
          <li className="min-w-0 break-words rounded-lg bg-white/5 p-2" key={item.path}>
            <p className="break-all">{item.path}</p>
            {item.reason && (
              <p className="text-xs text-zinc-400">{t(reasons[item.reason] || reasons.changed)}</p>
            )}
          </li>
        ))}
      </ul>
      <Pages count={items.length} size={20} page={current} setPage={setPage} />
    </section>
  )
}

function DuplicateGroup({
  group,
  selected,
  disabled,
  onToggle,
  onError,
}: {
  group: NonNullable<LibraryCheck['result']>['duplicates'][number]
  selected: Set<string>
  disabled: boolean
  onToggle: (path: string) => void
  onError: (error: unknown) => void
}) {
  const { t } = useI18n()
  const [page, setPage] = useState(0)
  const selectedCount = group.files.filter((file) => selected.has(file.path)).length
  return (
    <section
      className="grid min-w-0 gap-2 rounded-xl border border-white/10 p-3"
      aria-label={t('Duplicate group {id}', { id: group.id.slice(0, 6) })}
    >
      <h4 className="text-sm font-semibold">
        {t('{count} identical files', { count: group.files.length })} · {formatBytes(group.size)}
      </h4>
      <p className="text-xs text-zinc-400">
        {t('{count} copies will remain in Library', { count: group.files.length - selectedCount })}
      </p>
      {group.files.slice(page * 20, (page + 1) * 20).map((file) => (
        <div className="flex min-w-0 flex-wrap items-center gap-2 rounded-lg bg-white/5 p-2" key={file.path}>
          <label className="flex min-w-0 flex-1 items-start gap-2 text-sm">
            <input
              className="mt-1 shrink-0"
              type="checkbox"
              aria-label={t('Recycle duplicate {path}', { path: file.path })}
              checked={selected.has(file.path)}
              disabled={
                disabled ||
                (!selected.has(file.path) &&
                  (selectedCount >= group.files.length - 1 || selected.size >= 200))
              }
              onChange={() => onToggle(file.path)}
            />
            <span className="min-w-0 break-all">
              {file.path}
              {file.favorite && <span className="ml-2 text-xs text-amber-300">{t('Favorites')}</span>}
            </span>
          </label>
          <Button disabled={disabled} onClick={() => openFolder(file.path).catch(onError)}>
            {t('Show in folder')}
          </Button>
        </div>
      ))}
      <Pages count={group.files.length} size={20} page={page} setPage={setPage} />
    </section>
  )
}

export function LibraryOrganizer({
  root,
  editingBlocked,
  onRecycled,
}: {
  root: string
  editingBlocked: boolean
  onRecycled: (result: LibraryBatchResult) => void
}) {
  const { t } = useI18n()
  const [open, setOpen] = useState(false)
  const [state, setState] = useState<LibraryCheck | null>(null)
  const [selected, setSelected] = useState<string[]>([])
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [pollError, setPollError] = useState('')
  const [technical, setTechnical] = useState('')
  const [groupPage, setGroupPage] = useState(0)
  const [pollKey, setPollKey] = useState(0)
  const keys = useMemo(() => new Set(selected), [selected])
  const running = state?.status === 'running' || state?.status === 'cancelling'
  const result = state?.result
  const currentPage = Math.min(groupPage, Math.max(0, Math.ceil((result?.duplicates.length || 0) / 5) - 1))
  useEffect(() => {
    if (!open) return
    let stopped = false
    let timer: number | undefined
    const poll = async () => {
      try {
        const value = await getLibraryCheck()
        if (stopped) return
        setState(value)
        setPollError('')
        if (value.status === 'running' || value.status === 'cancelling') timer = window.setTimeout(poll, 1000)
      } catch (error) {
        if (!stopped) {
          setPollError(t(error instanceof Error ? error.message : 'That did not work'))
          timer = window.setTimeout(poll, 2000)
        }
      }
    }
    void poll()
    return () => {
      stopped = true
      window.clearTimeout(timer)
    }
  }, [open, root, pollKey, t])
  useEffect(() => {
    setSelected([])
    setConfirming(false)
    setGroupPage(0)
  }, [state?.id, root])
  async function action(action: 'start' | 'cancel') {
    setBusy(true)
    setError('')
    setTechnical('')
    setConfirming(false)
    try {
      setState(await libraryCheckAction(action))
      setPollKey((value) => value + 1)
    } catch (error) {
      setError(t(error instanceof Error ? error.message : 'That did not work'))
    } finally {
      setBusy(false)
    }
  }
  async function recycle() {
    if (!state) return
    setBusy(true)
    setError('')
    setTechnical('')
    try {
      const response = await recycleCheckedDuplicates(state.id, selected)
      onRecycled(response)
      setConfirming(false)
      if (response.processed.length) {
        setState(null)
        setSelected([])
        setPollKey((value) => value + 1)
      }
      if (response.failed.length) {
        setError(t('Some copies could not be recycled. Close any player using them, then run a new check.'))
        setTechnical(
          response.failed
            .slice(0, 5)
            .map((item) => `${item.item}: ${item.error}`)
            .join('\n'),
        )
      }
    } catch (error) {
      setError(t(error instanceof Error ? error.message : 'That did not work'))
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      <Button
        variant="ghost"
        onClick={() => {
          setOpen(true)
          setError('')
          setTechnical('')
        }}
      >
        {t('Library organizer')}
      </Button>
      <Modal
        open={open}
        title={t('Library organizer')}
        wide
        onClose={() => {
          if (!busy) setOpen(false)
        }}
      >
        <div className="grid min-w-0 gap-4">
          <p className="text-sm text-zinc-400">
            {t(
              'Check identical files, missing records and space usage in this library. Nothing is removed automatically.',
            )}
          </p>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="primary"
              disabled={busy || running || editingBlocked}
              onClick={() => action('start')}
            >
              {t(result ? 'Run a new check' : 'Check Library')}
            </Button>
            {running && (
              <Button disabled={busy || state?.status === 'cancelling'} onClick={() => action('cancel')}>
                {t('Cancel check')}
              </Button>
            )}
          </div>
          {editingBlocked && (
            <p className="text-sm text-amber-300">
              {t('Wait for running downloads to finish before checking Library.')}
            </p>
          )}
          {running && (
            <div role="status" className="grid gap-2 rounded-xl bg-white/5 p-3 text-sm">
              <p>
                {t(
                  state?.status === 'cancelling'
                    ? 'Stopping the library check…'
                    : state?.phase === 'inventory'
                      ? 'Checking folders…'
                      : state?.phase === 'hashing'
                        ? 'Reading duplicate candidates…'
                        : 'Verifying identical content…',
                )}
              </p>
              {state && (
                <p>
                  {state.checked}
                  {state.total ? ` / ${state.total}` : ''}
                  {state.phase === 'hashing' && ` · ${formatBytes(state.bytes_read)}`}
                </p>
              )}
              <p className="text-xs text-zinc-400">
                {t('You can close this panel; the check continues in the background.')}
              </p>
            </div>
          )}
          {state?.status === 'cancelled' && <p role="status">{t('Library check cancelled.')}</p>}
          {(error || pollError || state?.error) && (
            <p role="alert" className="whitespace-pre-wrap break-words text-sm text-red-300">
              {error || pollError || t(state?.error || '')}
            </p>
          )}
          {technical && (
            <details className="text-xs text-zinc-400">
              <summary>{t('Technical details')}</summary>
              <pre className="mt-2 whitespace-pre-wrap break-all">{technical}</pre>
            </details>
          )}
          {result && (
            <>
              <p className="text-xs text-zinc-400">
                {t('Last checked')}: {formatDate(result.finished)}
              </p>
              {result.incomplete && (
                <p className="text-sm text-amber-300">
                  {t(
                    'Some items could not be confirmed. Sizes cover discovered files only; unavailable paths are not treated as missing.',
                  )}
                </p>
              )}
              <section className="grid gap-2 sm:grid-cols-3" aria-label={t('Space overview')}>
                {(['media', 'attachments', 'recovery'] as const).map((key) => (
                  <div className="min-w-0 rounded-xl bg-white/5 p-3" key={key}>
                    <p className="text-sm text-zinc-400">
                      {t(
                        { media: 'Media files', attachments: 'Covers and subtitles', recovery: 'Recovery' }[
                          key
                        ],
                      )}
                    </p>
                    <p className="break-words text-lg font-semibold">{formatBytes(result[key].bytes)}</p>
                    <p className="text-xs text-zinc-400">
                      {t('{count} files', { count: result[key].count })}
                    </p>
                  </div>
                ))}
              </section>
              <p className="text-xs text-zinc-400">
                {t(
                  'These are file-size totals, not exact disk allocation. Moving files to Recovery does not free disk space.',
                )}
              </p>
              <section className="grid min-w-0 gap-3" aria-label={t('Identical files')}>
                <h3 className="font-semibold">
                  {t('Identical files')} · {result.duplicates.length}
                </h3>
                <p className="text-xs text-zinc-400">
                  {t(
                    'Extra main-file copies total {size}. Select copies to recycle; keep at least one per group. Covers, subtitles and annotations stay with each copy.',
                    { size: formatBytes(result.duplicate_bytes) },
                  )}
                </p>
                {!result.duplicates.length && (
                  <p className="text-sm text-zinc-400">{t('No identical files found.')}</p>
                )}
                {result.duplicates.slice(currentPage * 5, (currentPage + 1) * 5).map((group) => (
                  <DuplicateGroup
                    key={group.id}
                    group={group}
                    selected={keys}
                    disabled={busy || editingBlocked}
                    onToggle={(path) => {
                      setConfirming(false)
                      setSelected((items) =>
                        items.includes(path) ? items.filter((item) => item !== path) : [...items, path],
                      )
                    }}
                    onError={(error) =>
                      setError(t(error instanceof Error ? error.message : 'Could not open it'))
                    }
                  />
                ))}
                <Pages count={result.duplicates.length} size={5} page={currentPage} setPage={setGroupPage} />
                {result.duplicates.length > 0 && (
                  <div className="flex flex-wrap items-center gap-2 text-sm">
                    <span>{t('{count} selected', { count: selected.length })} / 200</span>
                    <Button
                      disabled={!selected.length || busy}
                      onClick={() => {
                        setSelected([])
                        setConfirming(false)
                      }}
                    >
                      {t('Clear selection')}
                    </Button>
                    <Button
                      disabled={!selected.length || busy || editingBlocked}
                      onClick={() => setConfirming(true)}
                    >
                      {t('Review recycling')}
                    </Button>
                  </div>
                )}
                {confirming && (
                  <div
                    className="grid gap-2 rounded-xl bg-white/5 p-3"
                    role="group"
                    aria-label={t('Confirm duplicate recycling')}
                  >
                    <p>
                      {t(
                        'Move {count} selected copies and their companions to Recovery? Each group keeps at least one copy. You can undo this.',
                        { count: selected.length },
                      )}
                    </p>
                    <div className="flex flex-wrap gap-2">
                      <Button disabled={busy} onClick={() => setConfirming(false)}>
                        {t('Cancel')}
                      </Button>
                      <Button variant="danger" disabled={busy || editingBlocked} onClick={recycle}>
                        {t('Confirm move to Recovery')}
                      </Button>
                    </div>
                  </div>
                )}
              </section>
              <Findings key={`missing:${state.id}`} title={t('Missing files')} items={result.missing}>
                <p className="text-xs text-zinc-400">
                  {t(
                    'Only previously recorded files can be reported missing. Favorites, tags and notes are kept. Check again after returning files to their original location.',
                  )}
                </p>
              </Findings>
              <Findings key={`unknown:${state.id}`} title={t('Could not confirm')} items={result.unknown} />
            </>
          )}
          {busy && <p role="status">{t('Working…')}</p>}
        </div>
      </Modal>
    </>
  )
}
