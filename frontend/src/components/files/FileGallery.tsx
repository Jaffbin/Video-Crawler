import {
  ExternalLink,
  Film,
  FolderOpen,
  Image as ImageIcon,
  Music,
  Pencil,
  Play,
  RefreshCw,
  Search,
  Star,
  ListPlus,
  Trash2,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import {
  batchLibrary,
  repairFile,
  fileUrl,
  getRecoveryFiles,
  openFile,
  openFolder,
  openExternalUrl,
  renameFile,
  restoreFile,
  purgeFile,
  trashFile,
  organizeFiles,
} from '../../api/client'
import type { ToastFn } from '../../hooks/useToasts'
import { formatBytes, formatDate } from '../../lib/utils'
import type { FileItem, RecoveryFile, LibraryScan, LibraryCollection } from '../../types/api'
import { CollectionManager } from './CollectionManager'
import { displayFilename, fileKind, filterLibrary, type LibrarySort } from '../../lib/library'
import { Button } from '../ui/Button'
import { Modal } from '../ui/Modal'
import { useI18n } from '../../i18n'

function ImageThumbnail({ file, onPreview }: { file: FileItem; onPreview: () => void }) {
  const { t } = useI18n()
  const [failed, setFailed] = useState(false)
  return (
    <button
      className="grid size-12 shrink-0 place-items-center overflow-hidden rounded-lg bg-white/5"
      aria-label={t('Preview {name}', { name: file.name })}
      onClick={onPreview}
    >
      {failed ? (
        <ImageIcon aria-hidden size={18} />
      ) : (
        <img
          src={fileUrl(file.path)}
          alt=""
          loading="lazy"
          decoding="async"
          className="size-full object-cover"
          onError={() => setFailed(true)}
        />
      )}
    </button>
  )
}

interface Props {
  files: FileItem[]
  windowMode: boolean
  onRefresh: () => void
  onToast: ToastFn
  editingBlocked?: boolean
  onNewDownload?: () => void
  scan?: LibraryScan
  collections?: LibraryCollection[]
}

export function FileGallery({
  files,
  windowMode,
  onRefresh,
  onToast,
  editingBlocked = false,
  onNewDownload,
  scan,
  collections = [],
}: Props) {
  const { t } = useI18n()
  const [selected, setSelected] = useState<string[]>([])
  const [recoverySelected, setRecoverySelected] = useState<string[]>([])
  const [batchAction, setBatchAction] = useState<'trash' | 'purge' | null>(null)
  const [query, setQuery] = useState('')
  const [source, setSource] = useState('')
  const [format, setFormat] = useState('')
  const [kind, setKind] = useState('')
  const [favoritesOnly, setFavoritesOnly] = useState(false)
  const [collectionFilter, setCollectionFilter] = useState('')
  const [organizing, setOrganizing] = useState<string[] | null>(null)
  const [sort, setSort] = useState<LibrarySort>('newest')
  const [page, setPage] = useState(0)
  const [pageSize, setPageSize] = useState(50)
  const [editing, setEditing] = useState<{ kind: 'rename' | 'trash'; file: FileItem } | null>(null)
  const [name, setName] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [recoveryOpen, setRecoveryOpen] = useState(false)
  const [deleting, setDeleting] = useState<RecoveryFile | null>(null)
  const [recovery, setRecovery] = useState<RecoveryFile[]>([])
  const [picture, setPicture] = useState<FileItem | null>(null)
  const [originalSize, setOriginalSize] = useState(false)
  const [imageFailed, setImageFailed] = useState(false)
  const [dimensions, setDimensions] = useState('')
  useEffect(() => {
    if (collectionFilter && !collections.some((collection) => collection.id === collectionFilter)) {
      setCollectionFilter('')
      setPage(0)
    }
  }, [collections, collectionFilter])
  const shown = useMemo(() => {
    return filterLibrary(files, query, source, format, '', '', sort, kind).filter(
      (file) =>
        (!favoritesOnly || file.favorite) &&
        (!collectionFilter || file.collections?.includes(collectionFilter)),
    )
  }, [files, query, source, format, sort, kind, favoritesOnly, collectionFilter])
  const currentPage = Math.min(page, Math.max(0, Math.ceil(shown.length / pageSize) - 1))
  const visible = shown.slice(currentPage * pageSize, (currentPage + 1) * pageSize)
  const chosen = files.filter((file) => selected.includes(file.path))
  const recoveryChosen = recovery.filter((file) => recoverySelected.includes(file.id))
  async function organize(
    paths: string[],
    patch: { favorite?: boolean; collection_id?: string; remove?: boolean },
  ) {
    setBusy(true)
    setError('')
    const failed: string[] = []
    let changed = 0
    try {
      for (let offset = 0; offset < paths.length; offset += 200) {
        const result = await organizeFiles(paths.slice(offset, offset + 200), patch)
        changed += result.processed.length
        failed.push(...result.failed.map((item) => item.item))
      }
      if (failed.length) {
        setError(t('Some files could not be changed. Refresh Library and try again.'))
        setSelected(failed)
      }
      onToast(
        t('Updated {count} files; {failed} could not be changed.', { count: changed, failed: failed.length }),
        failed.length > 0,
      )
    } catch (e) {
      setError(t(e instanceof Error ? e.message : 'That did not work'))
      report(e)
    } finally {
      if (changed) onRefresh()
      setBusy(false)
    }
  }
  function toggle(value: string, recoveryMode = false) {
    const setter = recoveryMode ? setRecoverySelected : setSelected
    setter((items) => (items.includes(value) ? items.filter((item) => item !== value) : [...items, value]))
  }
  function selectPage() {
    const paths = visible.map((file) => file.path)
    setSelected((items) =>
      paths.every((path) => items.includes(path))
        ? items.filter((item) => !paths.includes(item))
        : [...new Set([...items, ...paths])],
    )
  }
  async function changeMany(action: 'trash' | 'restore' | 'purge') {
    const items = action === 'trash' ? chosen.map((file) => file.path) : recoveryChosen.map((file) => file.id)
    setBusy(true)
    setError('')
    try {
      const result: { processed: string[]; failed: Array<{ item: string; error: string }> } = {
        processed: [],
        failed: [],
      }
      const recoveryIds: string[] = []
      for (let offset = 0; offset < items.length; offset += 200) {
        try {
          const chunk = await batchLibrary(items.slice(offset, offset + 200), action)
          result.processed.push(...chunk.processed)
          result.failed.push(...chunk.failed)
          recoveryIds.push(...(chunk.recovery_ids || []))
        } catch (e) {
          result.failed.push(
            ...items
              .slice(offset)
              .map((item) => ({ item, error: e instanceof Error ? e.message : 'That did not work' })),
          )
          break
        }
      }
      const setter = action === 'trash' ? setSelected : setRecoverySelected
      setter((values) => values.filter((value) => !result.processed.includes(value)))
      if (action !== 'trash')
        setRecovery((values) => values.filter((value) => !result.processed.includes(value.id)))
      onToast(
        t('Updated {count} files; {failed} could not be changed.', {
          count: result.processed.length,
          failed: result.failed.length,
        }),
        result.failed.length > 0,
        recoveryIds.length ? undoAction(recoveryIds) : undefined,
      )
      if (result.failed.length) {
        const reasons = result.failed.slice(0, 5).map((failure) => {
          const path = recovery.find((file) => file.id === failure.item)?.path || failure.item
          const message = failure.error.includes('already exists')
            ? 'A file with this name already exists. Rename it before restoring.'
            : /not found|no longer exists/.test(failure.error)
              ? 'This file is no longer available. Refresh the list.'
              : failure.error.includes('Invalid recovery record')
                ? 'This item’s recovery information is damaged.'
                : 'Close any player using this file and try again. Check available disk space if it still fails.'
          return displayFilename(path.split(/[\\/]/).pop() || path) + ': ' + t(message)
        })
        setError(
          t('Some files could not be changed. They remain selected so you can try again.') +
            ' ' +
            reasons.join(' '),
        )
      } else setBatchAction(null)
      if (result.processed.length) onRefresh()
    } catch (e) {
      setError(t(e instanceof Error ? e.message : 'That did not work'))
    } finally {
      setBusy(false)
    }
  }
  async function requestRepair(file: FileItem) {
    setBusy(true)
    try {
      await repairFile(file.path)
      onToast(t('Repair added to Queue. Your original files are kept until it succeeds.'))
      onRefresh()
    } catch (e) {
      report(e)
    } finally {
      setBusy(false)
    }
  }
  const sources = [...new Set(files.map((file) => file.source || 'unknown'))].sort()
  const formats = [...new Set(files.map((file) => '.' + file.name.split('.').pop()?.toLowerCase()))].sort()
  const report = (e: unknown) => onToast(t(e instanceof Error ? e.message : 'Could not open it'), true)
  function undoAction(ids: string[]) {
    let pending = [...ids]
    return {
      label: 'Undo',
      onClick: async () => {
        while (pending.length) {
          const chunk = pending.slice(0, 200)
          const result = await batchLibrary(chunk, 'restore')
          const before = pending.length
          pending = pending.filter((id) => !result.processed.includes(id))
          if (result.processed.length) onRefresh()
          if (result.failed.length || pending.length === before)
            throw new Error(
              'Could not undo. A file may already exist or be in use. Try again or open Recovery.',
            )
        }
        onToast(t('Files restored'))
      },
    }
  }
  function previewImage(file: FileItem) {
    setPicture(file)
    setOriginalSize(false)
    setImageFailed(false)
    setDimensions('')
  }

  async function editFile() {
    if (!editing) return
    setBusy(true)
    setError('')
    try {
      if (editing.kind === 'rename') {
        await renameFile(editing.file.path, name)
        onToast(t('File renamed'))
      } else {
        const result = await trashFile(editing.file.path)
        onToast(t('File moved to recovery.'), false, undoAction([result.id]))
      }
      setEditing(null)
      onRefresh()
    } catch (e) {
      setError(t(e instanceof Error ? e.message : 'That did not work'))
    } finally {
      setBusy(false)
    }
  }

  async function openRecovery() {
    setRecoveryOpen(true)
    setRecoverySelected([])
    setBatchAction(null)
    setDeleting(null)
    setBusy(true)
    setError('')
    try {
      setRecovery((await getRecoveryFiles()).items)
    } catch (e) {
      setError(t(e instanceof Error ? e.message : 'That did not work'))
    } finally {
      setBusy(false)
    }
  }

  async function removeRecovery() {
    if (!deleting) return
    setBusy(true)
    setError('')
    try {
      await purgeFile(deleting.id)
      setRecovery((items) => items.filter((item) => item.id !== deleting.id))
      setDeleting(null)
      onToast(t('File permanently deleted'))
      onRefresh()
    } catch (e) {
      setError(t(e instanceof Error ? e.message : 'That did not work'))
    } finally {
      setBusy(false)
    }
  }

  async function restore(id: string) {
    setBusy(true)
    setError('')
    try {
      await restoreFile(id)
      setRecovery((items) => items.filter((item) => item.id !== id))
      onToast(t('File restored'))
      onRefresh()
    } catch (e) {
      setError(t(e instanceof Error ? e.message : 'That did not work'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="card grid content-start gap-4" aria-labelledby="files-title">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="eyebrow">{t('Library')}</div>
          <h2 id="files-title" className="mt-1 text-lg font-semibold">
            {t('Downloaded files')}
          </h2>
        </div>
        <div className="flex flex-wrap gap-2">
          <CollectionManager collections={collections} onRefresh={onRefresh} onToast={onToast} />
          <Button variant="ghost" disabled={busy} onClick={openRecovery}>
            {t('Recovery')}
          </Button>
          <Button variant="ghost" onClick={onRefresh}>
            <RefreshCw aria-hidden size={15} /> {t('Refresh')}
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <Button
          aria-pressed={favoritesOnly}
          onClick={() => {
            setFavoritesOnly(!favoritesOnly)
            setPage(0)
          }}
        >
          <Star aria-hidden size={15} className={favoritesOnly ? 'fill-amber-300 text-amber-300' : ''} />{' '}
          {t('Favorites')}
        </Button>
        <label className="control min-w-0 flex-1">
          <span>{t('Collection')}</span>
          <select
            className="field"
            value={collectionFilter}
            onChange={(event) => {
              setCollectionFilter(event.target.value)
              setPage(0)
            }}
          >
            <option value="">{t('All collections')}</option>
            {collections.map((collection) => (
              <option key={collection.id} value={collection.id}>
                {collection.name}
              </option>
            ))}
          </select>
        </label>
      </div>

      {scan && (
        <div role="status" className="grid gap-1 text-xs text-zinc-400">
          <p>
            {t('Scanned {checked} entries; found {count} media files.', {
              checked: scan.checked,
              count: scan.media_count,
            })}
          </p>
          {scan.incomplete && (
            <div className="grid gap-1 text-amber-200">
              <p>{t('The library scan is incomplete. Search and filters cover discovered files only.')}</p>
              {scan.reasons.includes('entry_limit') && (
                <p>{t('Scan limit reached ({limit} entries).', { limit: scan.entry_limit })}</p>
              )}
              {scan.reasons.includes('depth_limit') && (
                <p>{t('Folders beyond {depth} directory levels were skipped.', { depth: scan.max_depth })}</p>
              )}
              {scan.reasons.includes('unreadable') && (
                <p>{t('Some files or folders could not be read. Check permissions and refresh.')}</p>
              )}
            </div>
          )}
        </div>
      )}

      <label className="relative">
        <span className="sr-only">{t('Search files')}</span>
        <Search
          aria-hidden
          size={15}
          className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500"
        />
        <input
          className="field !pl-9"
          type="search"
          placeholder={t('Search files')}
          value={query}
          onChange={(e) => {
            setQuery(e.target.value)
            setPage(0)
          }}
        />
      </label>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <label className="control">
          <span>{t('Media type')}</span>
          <select
            className="field"
            value={kind}
            onChange={(e) => {
              setKind(e.target.value)
              setPage(0)
            }}
          >
            <option value="">{t('All media')}</option>
            <option value="video">{t('Videos')}</option>
            <option value="audio">{t('Audio')}</option>
            <option value="image">{t('Images')}</option>
          </select>
        </label>
        <label className="control">
          <span>{t('Source site')}</span>
          <select
            className="field"
            value={source}
            onChange={(e) => {
              setSource(e.target.value)
              setPage(0)
            }}
          >
            <option value="">{t('All sources')}</option>
            {sources.map((site) => (
              <option key={site} value={site}>
                {site === 'unknown' ? t('Unknown source') : site}
              </option>
            ))}
          </select>
        </label>
        <label className="control">
          <span>{t('Format')}</span>
          <select
            className="field"
            value={format}
            onChange={(e) => {
              setFormat(e.target.value)
              setPage(0)
            }}
          >
            <option value="">{t('All formats')}</option>
            {formats.map((extension) => (
              <option key={extension} value={extension}>
                {extension.slice(1).toUpperCase()}
              </option>
            ))}
          </select>
        </label>
        <label className="control">
          <span>{t('Sort files')}</span>
          <select
            className="field"
            value={sort}
            onChange={(e) => {
              setSort(e.target.value as LibrarySort)
              setPage(0)
            }}
          >
            <option value="newest">{t('Newest first')}</option>
            <option value="oldest">{t('Oldest first')}</option>
            <option value="name">{t('Name')}</option>
            <option value="largest">{t('Largest first')}</option>
          </select>
        </label>
      </div>
      <div className="flex items-center justify-between text-xs text-zinc-400">
        <span>{t('{count} files', { count: shown.length })}</span>
        {(query || source || format || kind || favoritesOnly || collectionFilter) && (
          <button
            className="action-btn"
            onClick={() => {
              setQuery('')
              setSource('')
              setFormat('')
              setKind('')
              setFavoritesOnly(false)
              setCollectionFilter('')
              setPage(0)
            }}
          >
            {t('Reset filters')}
          </button>
        )}
      </div>
      {shown.length > 0 && (
        <div
          className="flex flex-wrap items-center gap-2 text-xs"
          role="group"
          aria-label={t('Library selection')}
        >
          <Button disabled={busy || editingBlocked} onClick={selectPage}>
            {t(
              visible.every((file) => selected.includes(file.path))
                ? 'Deselect this page'
                : 'Select this page',
            )}
          </Button>
          <span>
            {t('{count} selected', { count: chosen.length })} ·{' '}
            {formatBytes(chosen.reduce((sum, file) => sum + file.size, 0))}
          </span>
          {chosen.length > 0 && (
            <>
              <Button
                disabled={busy}
                onClick={() =>
                  organize(
                    chosen.map((file) => file.path),
                    { favorite: true },
                  )
                }
              >
                {t('Favorite selected')}
              </Button>
              <Button
                disabled={busy}
                onClick={() =>
                  organize(
                    chosen.map((file) => file.path),
                    { favorite: false },
                  )
                }
              >
                {t('Unfavorite selected')}
              </Button>
              <Button
                disabled={busy}
                onClick={() => {
                  setOrganizing(chosen.map((file) => file.path))
                  setError('')
                }}
              >
                {t('Organize selected collections')}
              </Button>
              <Button
                disabled={busy || editingBlocked}
                onClick={() => {
                  setError('')
                  setBatchAction('trash')
                }}
              >
                {t('Move selected to recovery')}
              </Button>
              <Button disabled={busy} onClick={() => setSelected([])}>
                {t('Clear selection')}
              </Button>
            </>
          )}
        </div>
      )}
      {editingBlocked && (
        <p className="text-xs text-amber-200">
          {t('File editing is available when running downloads finish.')}
        </p>
      )}
      {error && !editing && !recoveryOpen && !organizing && !batchAction && (
        <p role="alert" className="text-sm text-red-300">
          {error}
        </p>
      )}

      {files.length === 0 ? (
        <div className="grid justify-items-center gap-3 rounded-xl bg-white/[.025] px-4 py-8 text-center text-sm text-zinc-400">
          <p>{t('No completed files yet.')}</p>
          <p className="text-xs">{t('Finished downloads appear here with their source and file details.')}</p>
          {onNewDownload && <Button onClick={onNewDownload}>{t('Paste a link')}</Button>}
        </div>
      ) : shown.length === 0 ? (
        <p className="rounded-xl bg-white/[.025] px-4 py-8 text-center text-sm text-zinc-400">
          {t('No files match your search.')}
        </p>
      ) : (
        <ul className="grid gap-1">
          {visible.map((f) => (
            <li
              key={f.path}
              className="flex flex-wrap items-center gap-3 rounded-xl px-2 py-3 hover:bg-white/[.03]"
            >
              {fileKind(f) === 'image' ? (
                <ImageThumbnail file={f} onPreview={() => previewImage(f)} />
              ) : (
                <span
                  aria-hidden
                  className="grid size-8 shrink-0 place-items-center rounded-lg bg-white/[.05] text-zinc-400"
                >
                  {fileKind(f) === 'audio' ? <Music size={15} /> : <Film size={15} />}
                </span>
              )}
              <input
                type="checkbox"
                checked={selected.includes(f.path)}
                disabled={busy || editingBlocked}
                aria-label={t('Select {name}', { name: f.name })}
                onChange={() => toggle(f.path)}
              />
              <div className="min-w-0 flex-1 text-sm" title={f.path}>
                <p className="truncate" title={f.name}>
                  {displayFilename(f.name)}
                </p>
                {f.complete === false && (
                  <p className="mt-1 text-xs text-amber-300">
                    {t('Processing incomplete')} ·{' '}
                    {t(
                      f.can_repair
                        ? 'Repair this file using the files already downloaded.'
                        : 'Retry the original task to finish processing.',
                    )}
                  </p>
                )}
                <p className="mt-1 truncate text-xs text-zinc-500">
                  {f.source || t('Unknown source')} · {f.path}
                </p>
              </div>
              <span className="hidden shrink-0 text-xs tabular-nums text-zinc-500 sm:inline">
                {formatBytes(f.size)}
              </span>
              <span className="hidden shrink-0 text-xs text-zinc-500 md:inline">
                {formatDate(f.downloaded ?? f.mtime)}
              </span>
              <div className="flex flex-wrap gap-1">
                <button
                  className="action-btn"
                  disabled={busy}
                  aria-pressed={!!f.favorite}
                  aria-label={t(f.favorite ? 'Unfavorite {name}' : 'Favorite {name}', { name: f.name })}
                  onClick={() => organize([f.path], { favorite: !f.favorite })}
                >
                  <Star aria-hidden size={13} className={f.favorite ? 'fill-amber-300 text-amber-300' : ''} />
                </button>
                <button
                  className="action-btn"
                  disabled={busy}
                  aria-label={t('Manage collections for {name}', { name: f.name })}
                  onClick={() => {
                    setOrganizing([f.path])
                    setError('')
                  }}
                >
                  <ListPlus aria-hidden size={13} />
                </button>
                {f.complete === false && f.can_repair && (
                  <Button disabled={busy || editingBlocked} onClick={() => requestRepair(f)}>
                    {t('Repair')}
                  </Button>
                )}
                {fileKind(f) === 'image' ? (
                  <button className="action-btn" onClick={() => previewImage(f)}>
                    <ImageIcon aria-hidden size={13} /> {t('Preview image')}
                  </button>
                ) : windowMode ? (
                  <button type="button" className="action-btn" onClick={() => openFile(f.path).catch(report)}>
                    <Play aria-hidden size={13} />{' '}
                    {t(f.complete === false ? 'Open' : fileKind(f) === 'audio' ? 'Play audio' : 'Play video')}
                  </button>
                ) : (
                  <a className="action-btn" href={fileUrl(f.path)} target="_blank" rel="noreferrer">
                    <Play aria-hidden size={13} />{' '}
                    {t(f.complete === false ? 'Open' : fileKind(f) === 'audio' ? 'Play audio' : 'Play video')}
                  </a>
                )}
                <a className="action-btn" href={fileUrl(f.path)} download={f.name}>
                  {t('Download')}
                </a>

                <button
                  type="button"
                  className="action-btn"
                  onClick={() => openFolder(f.path).catch(report)}
                  aria-label={t('Show {name} in folder', { name: f.name })}
                >
                  <FolderOpen aria-hidden size={13} />
                  {t('Show in folder')}
                </button>
                {f.source_url && windowMode ? (
                  <button
                    className="action-btn"
                    aria-label={t('Open original page')}
                    onClick={() => openExternalUrl(f.source_url!).catch(report)}
                  >
                    <ExternalLink aria-hidden size={13} />
                  </button>
                ) : (
                  f.source_url && (
                    <a
                      className="action-btn"
                      href={f.source_url}
                      target="_blank"
                      rel="noreferrer"
                      aria-label={t('Open original page')}
                    >
                      <ExternalLink aria-hidden size={13} />
                    </a>
                  )
                )}
                <button
                  className="action-btn"
                  disabled={busy || editingBlocked}
                  aria-label={t('Rename {name}', { name: f.name })}
                  onClick={() => {
                    setError('')
                    setName(f.name)
                    setEditing({ kind: 'rename', file: f })
                  }}
                >
                  <Pencil aria-hidden size={13} />
                </button>
                <button
                  className="action-btn"
                  disabled={busy || editingBlocked}
                  aria-label={t('Move {name} to recovery', { name: f.name })}
                  onClick={() => {
                    setError('')
                    setEditing({ kind: 'trash', file: f })
                  }}
                >
                  <Trash2 aria-hidden size={13} />
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
      {shown.length > 0 && (
        <div
          className="flex flex-wrap items-center justify-end gap-3 text-xs"
          role="group"
          aria-label={t('Library pagination')}
        >
          <label className="flex items-center gap-2">
            {t('Files per page')}
            <select
              className="field !w-auto"
              value={pageSize}
              onChange={(e) => {
                setPageSize(Number(e.target.value))
                setPage(0)
              }}
            >
              {[25, 50, 100].map((size) => (
                <option key={size} value={size}>
                  {size}
                </option>
              ))}
            </select>
          </label>
          <span>
            {t('Showing {from}–{to} of {count}', {
              from: currentPage * pageSize + 1,
              to: Math.min((currentPage + 1) * pageSize, shown.length),
              count: shown.length,
            })}
          </span>
          <Button disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}>
            {t('Previous')}
          </Button>
          <span>
            {currentPage + 1} / {Math.ceil(shown.length / pageSize)}
          </span>
          <Button
            disabled={(currentPage + 1) * pageSize >= shown.length}
            onClick={() => setPage(currentPage + 1)}
          >
            {t('Next')}
          </Button>
        </div>
      )}
      <Modal
        open={organizing !== null}
        title={t('Organize collections')}
        onClose={() => {
          if (!busy) setOrganizing(null)
        }}
      >
        <div className="grid gap-3">
          <p className="text-sm">{t('{count} selected', { count: organizing?.length ?? 0 })}</p>
          <p className="text-xs text-zinc-400">
            {t('Adding to or removing from a collection keeps the files in their current location.')}
          </p>
          {collections.length === 0 && <p>{t('Create a collection using Manage collections.')}</p>}
          {collections.map((collection) => {
            const members = (organizing ?? []).filter((path) =>
              files.find((file) => file.path === path)?.collections?.includes(collection.id),
            ).length
            return (
              <div key={collection.id} className="flex flex-wrap items-center gap-2">
                <span className="min-w-0 flex-1 break-words">
                  {collection.name} · {members}/{organizing?.length ?? 0}
                </span>
                <Button
                  disabled={busy || members === organizing?.length}
                  onClick={() => organize(organizing ?? [], { collection_id: collection.id })}
                  aria-label={t('Add to {name}', { name: collection.name })}
                >
                  {t('Add')}
                </Button>
                <Button
                  disabled={busy || members === 0}
                  onClick={() => organize(organizing ?? [], { collection_id: collection.id, remove: true })}
                  aria-label={t('Remove from {name}', { name: collection.name })}
                >
                  {t('Remove from collection')}
                </Button>
              </div>
            )
          })}
          {error && (
            <p role="alert" className="text-sm text-red-300">
              {error}
            </p>
          )}
          <Button disabled={busy} onClick={() => setOrganizing(null)}>
            {t('Done')}
          </Button>
        </div>
      </Modal>
      <Modal open={picture !== null} title={t('Image preview')} wide onClose={() => setPicture(null)}>
        {picture && (
          <div className="grid gap-3">
            <p className="break-all text-sm">{picture.name}</p>
            <p className="text-xs text-zinc-400">
              {formatBytes(picture.size)}
              {dimensions && ` · ${dimensions}`}
            </p>
            <div className="max-h-[60vh] overflow-auto rounded-xl bg-black/30">
              {imageFailed ? (
                <p role="alert" className="p-4 text-sm text-amber-200">
                  {t('This image cannot be displayed here. Open the original file instead.')}
                </p>
              ) : (
                <img
                  key={picture.path}
                  src={fileUrl(picture.path)}
                  alt={picture.name}
                  className={originalSize ? 'max-w-none' : 'mx-auto max-h-[60vh] max-w-full object-contain'}
                  onLoad={(e) =>
                    setDimensions(`${e.currentTarget.naturalWidth} × ${e.currentTarget.naturalHeight}`)
                  }
                  onError={() => setImageFailed(true)}
                />
              )}
            </div>
            <div className="flex flex-wrap gap-2">
              <Button disabled={imageFailed} onClick={() => setOriginalSize(!originalSize)}>
                {t(originalSize ? 'Fit to window' : 'Original size')}
              </Button>
              <a className="action-btn" href={fileUrl(picture.path)} download={picture.name}>
                {t('Download')}
              </a>
              <Button onClick={() => openFile(picture.path).catch(report)}>{t('Open')}</Button>
              <Button onClick={() => openFolder(picture.path).catch(report)}>{t('Show in folder')}</Button>
              {picture.source_url &&
                (windowMode ? (
                  <Button onClick={() => openExternalUrl(picture.source_url!).catch(report)}>
                    {t('Open original page')}
                  </Button>
                ) : (
                  <a className="action-btn" href={picture.source_url} target="_blank" rel="noreferrer">
                    {t('Open original page')}
                  </a>
                ))}
            </div>
          </div>
        )}
      </Modal>
      <Modal
        open={editing !== null}
        title={t(editing?.kind === 'rename' ? 'Rename file' : 'Move to recovery')}
        onClose={() => {
          if (!busy) setEditing(null)
        }}
      >
        {editing && (
          <div className="grid gap-4">
            <p className="break-all text-sm text-zinc-300">{editing.file.path}</p>
            <p className="text-xs text-zinc-400">
              {t('Matching subtitles and cover files are managed together with this file.')}
            </p>
            {editing.kind === 'rename' ? (
              <label className="control">
                <span>{t('Filename')}</span>
                <input className="field" value={name} onChange={(e) => setName(e.target.value)} />
                <span>{t('Keep the original file extension.')}</span>
              </label>
            ) : (
              <p className="text-sm text-zinc-400">
                {t('The file is moved to a recovery folder. You can restore it from Library > Recovery.')}
              </p>
            )}
            {error && (
              <p role="alert" className="text-sm text-red-300">
                {error}
              </p>
            )}
            <div className="flex justify-end gap-2">
              <Button disabled={busy} onClick={() => setEditing(null)}>
                {t('Cancel')}
              </Button>
              <Button
                variant="primary"
                disabled={
                  busy ||
                  editingBlocked ||
                  (editing.kind === 'rename' && (!name.trim() || name === editing.file.name))
                }
                onClick={editFile}
              >
                {t(editing.kind === 'rename' ? 'Save' : 'Move to recovery')}
              </Button>
            </div>
          </div>
        )}
      </Modal>
      <Modal
        open={batchAction === 'trash'}
        title={t('Move selected to recovery')}
        onClose={() => {
          if (!busy) setBatchAction(null)
        }}
      >
        <div className="grid gap-3">
          <p>
            {t('Move {count} files and their matching subtitles and covers to Recovery?', {
              count: chosen.length,
            })}
          </p>
          <p className="text-sm text-zinc-400">
            {t('You can restore them later.')} ·{' '}
            {formatBytes(chosen.reduce((sum, file) => sum + file.size, 0))}
          </p>
          {error && (
            <p role="alert" className="text-sm text-red-300">
              {error}
            </p>
          )}
          <div className="flex justify-end gap-2">
            <Button disabled={busy} onClick={() => setBatchAction(null)}>
              {t('Cancel')}
            </Button>
            <Button
              disabled={busy || editingBlocked || chosen.length === 0}
              onClick={() => changeMany('trash')}
            >
              {t('Confirm move')}
            </Button>
          </div>
        </div>
      </Modal>
      <Modal
        open={recoveryOpen}
        title={t('Recovery')}
        onClose={() => {
          if (!busy) {
            setRecoveryOpen(false)
            setBatchAction(null)
            setDeleting(null)
            setError('')
          }
        }}
      >
        <div className="grid gap-3">
          <p className="text-sm text-zinc-400">
            {t('Recovery files stay on disk until restored or permanently deleted.')}
          </p>
          {error && (
            <p role="alert" className="text-sm text-red-300">
              {error}
            </p>
          )}
          {!deleting && batchAction !== 'purge' && recovery.length > 0 && (
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <Button
                disabled={busy || editingBlocked}
                onClick={() =>
                  setRecoverySelected(
                    recoveryChosen.length === recovery.length ? [] : recovery.map((file) => file.id),
                  )
                }
              >
                {t(recoveryChosen.length === recovery.length ? 'Clear selection' : 'Select all')}
              </Button>
              <span>
                {t('{count} selected', { count: recoveryChosen.length })} ·{' '}
                {formatBytes(recoveryChosen.reduce((sum, file) => sum + (file.size || 0), 0))}
              </span>
              <Button
                disabled={busy || editingBlocked || !recoveryChosen.length}
                onClick={() => changeMany('restore')}
              >
                {t('Restore selected')}
              </Button>
              <Button
                disabled={busy || editingBlocked || !recoveryChosen.length}
                onClick={() => {
                  setError('')
                  setBatchAction('purge')
                }}
              >
                {t('Delete selected permanently')}
              </Button>
            </div>
          )}
          {batchAction === 'purge' && (
            <div className="grid gap-3">
              <p>
                {t(
                  'Permanently delete {count} files and their matching subtitles and covers? This cannot be undone.',
                  { count: recoveryChosen.length },
                )}
              </p>
              <p>
                {t('Space to free')} ·{' '}
                {formatBytes(recoveryChosen.reduce((sum, file) => sum + (file.size || 0), 0))}
              </p>
              <div className="flex justify-end gap-2">
                <Button
                  disabled={busy}
                  onClick={() => {
                    setBatchAction(null)
                    setError('')
                  }}
                >
                  {t('Cancel')}
                </Button>
                <Button
                  disabled={busy || editingBlocked || !recoveryChosen.length}
                  onClick={() => changeMany('purge')}
                >
                  {t('Confirm permanent deletion')}
                </Button>
              </div>
            </div>
          )}
          {deleting && (
            <div className="grid gap-3">
              <p className="break-all text-sm">{deleting.path}</p>
              <p className="text-sm text-red-300">
                {t(
                  'Permanently delete this file and its matching subtitles and covers? This cannot be undone.',
                )}
              </p>
              <div className="flex justify-end gap-2">
                <Button
                  disabled={busy}
                  onClick={() => {
                    setDeleting(null)
                    setError('')
                  }}
                >
                  {t('Cancel')}
                </Button>
                <Button disabled={busy || editingBlocked} onClick={removeRecovery}>
                  {t('Confirm permanent deletion')}
                </Button>
              </div>
            </div>
          )}
          {busy && <p role="status">{t('Loading…')}</p>}
          {!busy && recovery.length === 0 && (
            <p className="text-sm text-zinc-400">{t('No recovery files.')}</p>
          )}
          {!deleting &&
            batchAction !== 'purge' &&
            recovery.map((item) => (
              <div key={item.id} className="flex items-center gap-3 rounded-xl bg-white/[.025] p-3">
                <input
                  type="checkbox"
                  checked={recoverySelected.includes(item.id)}
                  disabled={busy || editingBlocked}
                  aria-label={t('Select {name}', { name: item.path })}
                  onChange={() => toggle(item.id, true)}
                />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm" title={item.path}>
                    {displayFilename(item.path.split(/[\\/]/).pop() || item.path)}
                  </p>
                  <p className="text-xs text-zinc-500">{formatDate(item.removed)}</p>
                </div>
                <Button disabled={busy || editingBlocked} onClick={() => restore(item.id)}>
                  {t('Restore')}
                </Button>
                <Button
                  disabled={busy || editingBlocked}
                  onClick={() => {
                    setError('')
                    setDeleting(item)
                  }}
                >
                  <Trash2 aria-hidden size={14} /> {t('Delete permanently')}
                </Button>
              </div>
            ))}
        </div>
      </Modal>
    </section>
  )
}
